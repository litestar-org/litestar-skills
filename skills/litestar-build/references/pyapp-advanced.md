# PyApp — Advanced (offline, custom install dir, portable glibc)

An advanced PyApp pattern: a custom bundler that pre-installs all dependencies into a `python-build-standalone` archive, patches PyApp's Rust source to override the default install directory, and uses `cargo-zigbuild` for glibc 2.17 compatibility.

Result: a ~500 MB onefile that runs on CentOS 7, with no PyPI calls on first launch, installing to `~/.<app>/runtime/` by default.

## Architecture

```text
                                             ┌─────────────────────────┐
                        ┌───────────────────▶│  python-dist.tar.gz     │
                        │                    │  (Python + deps, ~400MB)│
                        │                    └────────────┬────────────┘
┌───────────┐    ┌──────┴────────┐                        │
│ uv build  │───▶│ bundler.py    │                        │ PYAPP_DISTRIBUTION_PATH
│ --wheel   │    │               │                        │ PYAPP_SKIP_INSTALL=true
└─────┬─────┘    │ 1. download   │                        ▼
      │          │    PBS        │               ┌──────────────────┐
      │          │ 2. uv pip     │               │  PyApp (Rust)    │
      │          │    install    │               │                  │
      │          │    --target   │◀──────────────┤ patched app.rs   │
      └─────────▶│ 3. patch      │   --pyapp-dir │                  │
                 │    app.rs     │               │ cargo zigbuild   │
                 │ 4. tar.gz     │               └─────────┬────────┘
                 └───────────────┘                         │
                                                           ▼
                                               ┌──────────────────────┐
                                               │  dist/<app>  (500MB) │
                                               │  single executable   │
                                               └──────────────────────┘
```

Three things make this different from simple hatch-binary:

1. **`PYAPP_DISTRIBUTION_EMBED=true` + `PYAPP_SKIP_INSTALL=true` with a pre-built tarball.** PyApp just extracts — no `uv pip install` at first-run time.
2. **Patched `src/app.rs`** for the install directory.
3. **`cargo zigbuild --target X.2.17`** for glibc 2.17 baseline.

## The bundler

`tools/bundler.py` is a single-file PEP 723 script (runs with `uv run`, with `rich-click`, `rich`, and `tomli; python_version < '3.11'` declared in its `/// script` header):

```python
"""Bundle Python dependencies into a standalone distribution for PyApp."""
```

### Target mapping

`DEFAULT_PLATFORMS` maps Rust target triples to `uv --python-platform` values (not PEP 425 wheel tags), using `manylinux_2_28` when native wheels such as `duckdb` require glibc 2.28+:

```python
DEFAULT_URLS: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "aarch64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "x86_64-apple-darwin": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-apple-darwin-install_only_stripped.tar.gz",
    "aarch64-apple-darwin": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-aarch64-apple-darwin-install_only_stripped.tar.gz",
    "x86_64-pc-windows-msvc": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
}

DEFAULT_PLATFORMS: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "x86_64-manylinux_2_28",
    "aarch64-unknown-linux-gnu": "aarch64-manylinux_2_28",
    "x86_64-apple-darwin": "x86_64-apple-darwin",
    "aarch64-apple-darwin": "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc": "x86_64-pc-windows-msvc",
}
```

`install_only_stripped` variants are debug-stripped and ~30 MB smaller than full distributions. Good for binaries.

### Build flow

```python
def build_bundle(
    url: str,
    cache_dir: Path,
    extract_dir: Path,
    target: str,
    python_version: str,
    requirements_path: Path,
    resolved_platform: str,
    resolved_python_version: str,
    pyapp_dir: Path | None,
    resolved_install_dir: Path,
    resolved_output: Path,
) -> None:
    """Download a python-build-standalone archive, pre-install wheels into site-packages, optionally patch PyApp's install dir, and repack as python-dist.tar.gz."""
    archive_path = download_pbs(url, cache_dir)
    extract_archive(archive_path, extract_dir)
    python_root = resolve_python_root(extract_dir)
    site_packages = find_site_packages(python_root, target, python_version)

    install_requirements(
        requirements_path=requirements_path,
        site_packages=site_packages,
        platform=resolved_platform,
        python_version=resolved_python_version,
    )

    if pyapp_dir:
        patch_pyapp_install_dir(pyapp_dir, resolved_install_dir)

    with tarfile.open(resolved_output, "w:gz") as tar:
        tar.add(python_root, arcname="python")
```

Step 4 is why the onefile is offline-capable: every dep is already unpacked into the Python distribution. PyApp at first run just extracts the tarball; no network.

### The install-dir patch (the clever bit)

In PyApp `v0.29.0`, `src/app.rs` resolves the installation directory inside `initialize()` as `platform_dirs().data_local_dir().join(project_name()).join(distribution_id()).join(project_version())` (with a built-in runtime override via `PYAPP_INSTALL_DIR_<PROJECT_NAME>`, where `<PROJECT_NAME>` is the uppercased `PYAPP_PROJECT_NAME` with `-` replaced by `_`; note that there is no separate `storage_dir()` or `project_dirs()` helper function in `src/app.rs`):

- Linux: `~/.local/share/<app>/<hash>/<version>/`
- macOS: `~/Library/Application Support/<app>/<hash>/<version>/`

When you want a custom **compiled-in default** directory such as `~/.<app>/runtime/` (so end-users do not have to export `PYAPP_INSTALL_DIR_<PROJECT_NAME>` on every invocation or `self remove`/`self restore` command), patch `src/app.rs` **before** `cargo build`:

```python
import contextlib
from pathlib import Path
import re


def rust_string_literal(value: str) -> str:
    """Format a Python string as an escaped Rust string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_install_dir_expression(install_dir: Path) -> str:
    """Render a Rust PathBuf expression that resolves relative to home_dir() when under $HOME."""
    install_dir = install_dir.expanduser().resolve()
    home_dir = Path.home().resolve()
    with contextlib.suppress(ValueError):
        relative = install_dir.relative_to(home_dir)
        expression = 'directories::BaseDirs::new().expect("could not find base directories").home_dir()'
        for part in relative.parts:
            expression += f".join({rust_string_literal(part)})"
        return expression
    return f"std::path::PathBuf::from({rust_string_literal(str(install_dir))})"


def patch_pyapp_install_dir(pyapp_dir: Path, install_dir: Path) -> None:
    """Patch PyApp src/app.rs to use a custom default installation directory."""
    app_rs = pyapp_dir / "src" / "app.rs"
    content = app_rs.read_text(encoding="utf-8")
    pattern = re.compile(
        r"platform_dirs\(\)\s*\.data_local_dir\(\)\s*"
        r"\.join\(project_name\(\)\)\s*"
        r"\.join\(distribution_id\(\)\)\s*"
        r"\.join\(project_version\(\)\)"
    )
    replacement = render_install_dir_expression(install_dir)
    updated = pattern.sub(replacement, content, count=1)
    app_rs.write_text(updated, encoding="utf-8")
```

The replacement Rust expression is generated to **stay relocatable** — if the target install dir is under `$HOME`, it resolves `home_dir()` at runtime. (If you instead want to keep PyApp's `<project>/<distribution_id>/<version>` suffix under a custom root directory, replace only the `platform_dirs().data_local_dir()` base prefix and preserve the `.join(...)` suffix.)

For `--install-root ~/.<app> --project-name runtime`, the rendered Rust becomes:

```rust
directories::BaseDirs::new().expect("could not find base directories").home_dir().join(".<app>").join("runtime")
```

That means:

- `/path/to/alice/<app>` binary → installs to `/path/to/alice/.<app>/runtime/`
- `/path/to/bob/<app>` binary → installs to `/path/to/bob/.<app>/runtime/`
- Same binary, different user — works.

For absolute paths (e.g. `--install-root /opt/<app>`), the expression is a hardcoded `PathBuf::from("/opt/<app>/runtime")` — not relocatable, but that's what the operator asked for.

## The build script

`tools/scripts/build-onefile-package.sh` orchestrates everything:

```bash
#!/usr/bin/env bash
# tools/scripts/build-onefile-package.sh (abbreviated)
set -euo pipefail

# Ensure uv tools (cargo-zigbuild) and cargo are on PATH in non-interactive shells
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

current_version=$(uv run python -c "from app.__metadata__ import __version__; print(__version__)")

# Static linking for libc extras (no libbz2/liblzma on target systems)
export BZIP2_SYS_STATIC="1"
export LZMA_API_STATIC="1"

# PyApp build-time env
export PYAPP_VERSION="v0.29.0"
export PYAPP_DIR="dist/.scratch"
export PYAPP_PROJECT_PATH="$(realpath dist/app-${current_version}-py3-none-any.whl)"
export PYAPP_PROJECT_NAME="app"
export PYAPP_PROJECT_VERSION="${current_version}"
export PYAPP_PYTHON_VERSION="3.13"
export PYAPP_PROJECT_FEATURES="cloudrun"
export PYAPP_DISTRIBUTION_VARIANT_CPU="v1"
export PYAPP_UV_ENABLED="true"
export PYAPP_FULL_ISOLATION="true"
export PYAPP_DISTRIBUTION_EMBED="true"

# 1. Clone PyApp at pinned version
git clone --quiet --depth 1 --branch "$PYAPP_VERSION" https://github.com/ofek/pyapp ${PYAPP_DIR}

# 2. Patch PyApp Cargo.toml for static libbz2 / liblzma
sed -i 's/bzip2 = "\([^"]*\)"/bzip2 = { version = "\1", features = ["static"] }/' ${PYAPP_DIR}/Cargo.toml
sed -i '/\[dependencies\]/a bzip2-sys = { version = "*", features = ["static"] }' ${PYAPP_DIR}/Cargo.toml

# 3. Build the wheel
uv build --wheel --clear

# 4. Export requirements so bundler.py knows what to install
uv export --frozen --no-dev --no-editable --no-hashes --no-header --no-emit-project --extra cloudrun > dist/requirements.txt
echo "$(realpath dist/app-${current_version}-py3-none-any.whl)" >> dist/requirements.txt

# 5. Bundle Python + deps → dist/python-dist.tar.gz, and patch PyApp src/app.rs
uv run tools/bundler.py build \
  --requirements dist/requirements.txt \
  --output dist/python-dist.tar.gz \
  --pyapp-dir ${PYAPP_DIR} \
  --install-root "~/.<app>" \
  --project-name "runtime"

# 6. Post-bundler env: point PyApp at the pre-built tarball, skip install
export PYAPP_DISTRIBUTION_PATH="$(realpath dist/python-dist.tar.gz)"
export PYAPP_DISTRIBUTION_EMBED="true"
export PYAPP_DISTRIBUTION_PYTHON_PATH="python/bin/python3"
export PYAPP_SKIP_INSTALL="true"
export PYAPP_ALLOW_UPDATES="true"
unset PYAPP_PROJECT_DEPENDENCY_FILE

# 7. Build the binary (Linux: require cargo-zigbuild with glibc 2.17 baseline)
cd ${PYAPP_DIR}
if [ "$(uname -s)" = "Linux" ]; then
    if ! command -v cargo-zigbuild &> /dev/null; then
        echo "Error: cargo-zigbuild not found on PATH ($PATH); refusing to fall back to host glibc." >&2
        exit 1
    fi
    BASE_TARGET="x86_64-unknown-linux-gnu"
    cargo zigbuild --release --target ${BASE_TARGET}.2.17
    cp target/${BASE_TARGET}.2.17/release/pyapp ../../dist/app
else
    cargo build --release
    cp target/release/pyapp ../../dist/app
fi
cd ../..
chmod +x dist/app

# 8. Clean up intermediate scratch (~1.2 GB) and bundle tarball (~280 MB)
rm -rf "${PYAPP_DIR}" dist/python-dist.tar.gz
```

In PyApp `v0.29.0`, `Cargo.toml` sets `bzip2 = "0.6.0"` (which uses the pure-Rust `libbz2-rs-sys` backend by default, making `static = ["bzip2-sys?/static"]` a no-op) and has no `xz`/`lzma` dependency. Keeping `BZIP2_SYS_STATIC=1`, `LZMA_API_STATIC=1`, and the `sed` patch is a harmless belt-and-suspenders guard that remains essential when pinning older `PYAPP_VERSION` tags. (If rewriting `Cargo.toml` in Python with `re.MULTILINE`, match end-of-line with `[ \t]*$` rather than `\s*$` so `\s*` does not consume the newline and join the next line.)

## PyApp env var catalog

Everything the advanced build sets:

| Var | Value | When read | Why |
| --- | --- | --- | --- |
| `PYAPP_VERSION` | `v0.29.0` | Shell (git clone) | PyApp release to compile |
| `PYAPP_PROJECT_PATH` | `dist/*.whl` | cargo build | Wheel to embed in the binary |
| `PYAPP_PROJECT_NAME` | `app` | cargo build | Project identifier (also determines runtime `PYAPP_INSTALL_DIR_<PROJECT_NAME>`) |
| `PYAPP_PROJECT_VERSION` | `1.2.3` | cargo build | Stamped into binary metadata |
| `PYAPP_PYTHON_VERSION` | `3.13` | cargo build | Which PBS archive to match |
| `PYAPP_PROJECT_FEATURES` | `cloudrun` | cargo build | Pass extras to `uv pip install` at first run (ignored when `PYAPP_SKIP_INSTALL=true`) |
| `PYAPP_DISTRIBUTION_VARIANT_CPU` | `v1` | cargo build | CPU baseline (x86-64-v1/v2/v3) |
| `PYAPP_DISTRIBUTION_VARIANT_GIL` | `freethreaded` *(optional)* | cargo build | On Python 3.13+, select the free-threaded (no-GIL) distribution variant |
| `PYAPP_DISTRIBUTION_PATH` | `dist/python-dist.tar.gz` | cargo build | Use pre-built tarball instead of downloading PBS |
| `PYAPP_DISTRIBUTION_EMBED` | `true` | cargo build | Embed the tarball *in* the binary |
| `PYAPP_DISTRIBUTION_PYTHON_PATH` | `python/bin/python3` | cargo build | Path to Python *inside* the tarball |
| `PYAPP_SKIP_INSTALL` | `true` | cargo build | Do not run `uv pip install` on first launch — deps already in tarball |
| `PYAPP_FULL_ISOLATION` | `true` | cargo build | Isolated venv per version, ignore user site-packages |
| `PYAPP_UV_ENABLED` | `true` | cargo build | Use `uv pip` (unused when `SKIP_INSTALL=true`, harmless) |
| `PYAPP_ALLOW_UPDATES` | `true` | cargo build | Enable `<binary> self update` at runtime |
| `PYAPP_INSTALL_DIR_<PROJECT_NAME>` | `/custom/path` *(optional)* | Runtime (binary) | Override the compiled-in default extraction directory (`<PROJECT_NAME>` is uppercased `PYAPP_PROJECT_NAME` with `-` → `_`; keep set for `self remove` / `self restore`) |
| `PYAPP` | `1` *(or binary path)* | Runtime (Python) | Set by the PyApp wrapper inside the spawned Python process (`1`, or executable path when compiled with `PYAPP_PASS_LOCATION=1`) |
| `BZIP2_SYS_STATIC` | `1` | cargo build | Link libbz2 statically |
| `LZMA_API_STATIC` | `1` | cargo build | Link liblzma statically |

**Critical:** `PYAPP_*` configuration variables are **build-time** env vars consumed while compiling PyApp — **except** `PYAPP_INSTALL_DIR_<PROJECT_NAME>`, which the binary reads at runtime to override the extraction directory. Setting `PYAPP_PROJECT_NAME` when running the binary is a no-op; the compiled binary already has the name baked into the Rust source. At runtime, the PyApp wrapper sets `PYAPP=1` (or the executable path when compiled with `PYAPP_PASS_LOCATION=1`) inside the spawned Python environment so application code can detect onefile execution via `os.getenv("PYAPP")`.

## glibc portability with `cargo-zigbuild`

Plain `cargo build --release` on `ubuntu-latest` (Ubuntu 24.04) links against the runner's host glibc (`GLIBC_2.39`). The resulting binary passes `./dist/app --help` on the runner host, then fails inside older distros or Debian Bookworm / distroless containers (`gcr.io/distroless/cc-debian12:nonroot`, `GLIBC_2.36`):

```text
./app: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.39' not found
```

`cargo-zigbuild` wraps Zig's cross-compiler and lets you specify a glibc floor:

```bash
cargo zigbuild --release --target x86_64-unknown-linux-gnu.2.17
```

`.2.17` → CentOS 7 / RHEL 7 / Ubuntu 14.04 era. Works on everything from 2014 onward.

Install in CI (and ensure `$(uv tool dir --bin)` and `$HOME/.cargo/bin` are exported to `$GITHUB_PATH` — `uv tool install cargo-zigbuild` installs into `$HOME/.local/bin`, which is not on `$GITHUB_PATH` by default on many runners, and cached `~/.cargo/bin` skips the Rust setup `PATH` append):

```bash
ZIG_VERSION="0.15.2"
mkdir -p ~/.local/zig
curl -fsSL "https://ziglang.org/download/${ZIG_VERSION}/zig-x86_64-linux-${ZIG_VERSION}.tar.xz" | tar -xJ --strip-components=1 -C ~/.local/zig
uv tool install cargo-zigbuild
echo "$HOME/.local/zig" >> "$GITHUB_PATH"
echo "$(uv tool dir --bin)" >> "$GITHUB_PATH"
echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"
```

## CLI reference: `bundler.py build`

```text
Options:
  --target TEXT              Rust target architecture (x86_64-unknown-linux-gnu, aarch64-apple-darwin, ...)
  --requirements PATH        Path to requirements.txt (must include the app wheel path)
  --output TEXT              Output path for the bundled distribution (.tar.gz)
  --project-dir PATH         Project directory (default: cwd)
  --project-name TEXT        Override project name used in install dir (default: from pyproject.toml)
  --install-root TEXT        Install root (default: ~/.local)
  --cache-dir TEXT           Override cache directory (default: <project>/.cache/bundler)
  --python-url TEXT          Override python-build-standalone URL
  --python-archive PATH      Use a local PBS archive instead of downloading
  --python-version TEXT      Python version for uv wheel selection (default: inferred from URL)
  --platform TEXT            Override uv --python-platform value
  --pyapp-dir PATH           Path to a PyApp checkout to patch install dir
  --index-url TEXT           Custom Python package index URL
  --extra-index-url TEXT     Additional package index URLs (multi)
  --allow-source             Allow source builds when wheels are missing
  --include-deps             Allow uv to resolve deps (omit --no-deps)
  --refresh                  Force re-download of PBS archives
  --keep-temp                Keep temp working dir after completion (for debugging)
```

## Verification

```bash
# 1. Binary is self-contained (no libbz2, no liblzma, no Python runtime deps)
ldd dist/app
# Expected: libc.so.6, libm.so.6, libpthread.so.0, ld-linux-*.so.2, (none)

# 2. First launch creates the install dir, extracts, runs
./dist/app --help
ls -la ~/.<app>/runtime/
# Expected: lib/, bin/, include/, share/

# 3. Second launch is fast (skips extraction)
time ./dist/app --help                 # should be < 200ms

# 4. Network isolation test
docker run --rm --network=none \
  -v $PWD/dist:/opt/dist:ro \
  gcr.io/distroless/cc-debian12:nonroot \
  /opt/dist/app --help
# If this succeeds, the binary is fully offline
```

## Upgrading

See [upgrading.md](upgrading.md) — advanced flavors have 5+ files to touch for any version bump, because the Python version, PyApp version, and PBS URL are all referenced in multiple places.

## When not to do this

- Your app is a short-lived script or a library.
- Users have network access.
- No corporate install-location policy.
- Target glibc ≥ 2.28 is fine.

Stay with [pyapp-simple.md](pyapp-simple.md). Advanced adds ~500 lines of Python and several hundred lines of YAML.
