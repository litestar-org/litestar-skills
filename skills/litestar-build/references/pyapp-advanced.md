# PyApp — Advanced (offline, custom install dir, portable glibc)

The DMA accelerator pattern: a custom bundler that pre-installs all dependencies into a `python-build-standalone` archive, patches PyApp's Rust source to override the default install directory, and uses `cargo-zigbuild` for glibc 2.17 compatibility.

Result: a ~500 MB onefile that runs on CentOS 7, with no PyPI calls on first launch, installing to `~/.dma/runtime/` by default.

Reference: `/home/cody/code/g/dma/accelerator/tools/bundler.py` + `/home/cody/code/g/dma/accelerator/tools/scripts/build-onefile-package.sh`.

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

`tools/bundler.py` is a single-file script (runs with `uv run`, has its own deps pinned in the shebang header):

```python
# /home/cody/code/g/dma/accelerator/tools/bundler.py:1-8
#!/usr/bin/env python3
# /// script
# dependencies = [
#   "rich-click",
#   "rich",
#   "tomli; python_version < '3.11'",
# ]
# ///
"""Bundle Python dependencies into a standalone distribution for PyApp."""
```

### Target mapping

```python
# tools/bundler.py:45-62
DEFAULT_URLS: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "aarch64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "x86_64-apple-darwin":       "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-apple-darwin-install_only_stripped.tar.gz",
    "aarch64-apple-darwin":      "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-aarch64-apple-darwin-install_only_stripped.tar.gz",
    "x86_64-pc-windows-msvc":    "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.13.13%2B20260414-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
}

# uv --python-platform values (NOT PEP 425 wheel tags)
# manylinux_2_28 required because duckdb only provides wheels for glibc 2.28+
DEFAULT_PLATFORMS: dict[str, str] = {
    "x86_64-unknown-linux-gnu":  "x86_64-manylinux_2_28",
    "aarch64-unknown-linux-gnu": "aarch64-manylinux_2_28",
    "x86_64-apple-darwin":       "x86_64-apple-darwin",
    "aarch64-apple-darwin":      "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc":    "x86_64-pc-windows-msvc",
}
```

`install_only_stripped` variants are debug-stripped and ~30 MB smaller than full distributions. Good for binaries.

### Build flow

```python
# tools/bundler.py:599-738 (abbreviated)
def build_bundle(...):
    # 1. Download python-build-standalone archive to cache
    archive_path = download_pbs(url, cache_dir)

    # 2. Extract to a temp work dir
    extract_archive(archive_path, extract_dir)
    python_root = resolve_python_root(extract_dir)        # e.g. extract_dir/python

    # 3. Locate the site-packages inside the extracted Python
    site_packages = find_site_packages(python_root, target, python_version)

    # 4. uv pip install the app's requirements into that site-packages
    install_requirements(
        requirements_path=requirements_path,
        site_packages=site_packages,
        platform=resolved_platform,          # e.g. x86_64-manylinux_2_28
        python_version=resolved_python_version,
        ...
    )

    # 5. Optionally patch PyApp's Rust source for the custom install dir
    if pyapp_dir:
        patch_pyapp_install_dir(pyapp_dir, resolved_install_dir)

    # 6. Repack as python-dist.tar.gz
    with tarfile.open(resolved_output, "w:gz") as tar:
        tar.add(python_root, arcname="python")
```

Step 4 is why the onefile is offline-capable: every dep is already unpacked into the Python distribution. PyApp at first run just extracts the tarball; no network.

### The install-dir patch (the clever bit)

PyApp's default install dir at runtime is `platform_dirs().data_local_dir().join(project_name).join(distribution_id).join(project_version)`:

- Linux: `~/.local/share/<app>/<hash>/<version>/`
- macOS: `~/Library/Application Support/<app>/<hash>/<version>/`

accelerator wants `~/.dma/runtime/` instead. It patches `src/app.rs` **before** `cargo build`:

```python
# tools/bundler.py:431-453
def patch_pyapp_install_dir(pyapp_dir: Path, install_dir: Path) -> None:
    """Patch PyApp to use a custom default installation directory."""
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

The replacement Rust expression is generated to **stay relocatable** — if the target install dir is under `$HOME`, it resolves `home_dir()` at runtime:

```python
# tools/bundler.py:417-428
def render_install_dir_expression(install_dir: Path) -> str:
    install_dir = install_dir.expanduser().resolve()
    home_dir = Path.home().resolve()
    with contextlib.suppress(ValueError):
        relative = install_dir.relative_to(home_dir)
        expression = 'directories::BaseDirs::new().expect("could not find base directories").home_dir()'
        for part in relative.parts:
            expression += f".join({rust_string_literal(part)})"
        return expression
    return f"std::path::PathBuf::from({rust_string_literal(str(install_dir))})"
```

For `--install-root ~/.dma --project-name runtime`, the rendered Rust becomes:

```rust
directories::BaseDirs::new().expect("could not find base directories").home_dir().join(".dma").join("runtime")
```

That means:

- `/home/alice/<app>` binary → installs to `/home/alice/.dma/runtime/`
- `/home/bob/<app>` binary → installs to `/home/bob/.dma/runtime/`
- Same binary, different user — works.

For absolute paths (e.g. `--install-root /opt/dma`), the expression is a hardcoded `PathBuf::from("/opt/dma/runtime")` — not relocatable, but that's what the operator asked for.

## The build script

`tools/scripts/build-onefile-package.sh` orchestrates everything:

```bash
#!/usr/bin/env bash
# tools/scripts/build-onefile-package.sh (abbreviated)
set -euo pipefail

current_version=$(uv run python -c "from dma.__metadata__ import __version__; print(__version__)")

# Static linking for libc extras (no libbz2/liblzma on target systems)
export BZIP2_SYS_STATIC="1"
export LZMA_API_STATIC="1"

# PyApp build-time env
export PYAPP_VERSION="v0.29.0"
export PYAPP_DIR="dist/.scratch"
export PYAPP_PROJECT_PATH="$(realpath dist/dma-${current_version}-py3-none-any.whl)"
export PYAPP_PROJECT_NAME="dma"
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
uv build --wheel

# 4. Export requirements so bundler.py knows what to install
uv export --frozen --no-dev --no-editable --no-hashes --no-header --no-emit-project --extra cloudrun > dist/requirements.txt
echo "$(realpath dist/dma-${current_version}-py3-none-any.whl)" >> dist/requirements.txt

# 5. Bundle Python + deps → dist/python-dist.tar.gz, and patch PyApp src/app.rs
uv run tools/bundler.py build \
  --requirements dist/requirements.txt \
  --output dist/python-dist.tar.gz \
  --pyapp-dir ${PYAPP_DIR} \
  --install-root "~/.dma" \
  --project-name "runtime"

# 6. Post-bundler env: point PyApp at the pre-built tarball, skip install
export PYAPP_DISTRIBUTION_PATH="$(realpath dist/python-dist.tar.gz)"
export PYAPP_DISTRIBUTION_EMBED="true"
export PYAPP_DISTRIBUTION_PYTHON_PATH="python/bin/python3"
export PYAPP_SKIP_INSTALL="true"
export PYAPP_ALLOW_UPDATES="true"
unset PYAPP_PROJECT_DEPENDENCY_FILE

# 7. Build the binary (Linux: zigbuild with glibc 2.17 baseline)
cd ${PYAPP_DIR}
if command -v cargo-zigbuild &> /dev/null && [ "$(uname -s)" = "Linux" ]; then
    BASE_TARGET="x86_64-unknown-linux-gnu"
    cargo zigbuild --release --target ${BASE_TARGET}.2.17
    cp target/${BASE_TARGET}.2.17/release/pyapp ../../dist/dma
else
    cargo build --release
    cp target/release/pyapp ../../dist/dma
fi
chmod +x ../../dist/dma
```

The `BZIP2_SYS_STATIC=1` and `LZMA_API_STATIC=1` env vars + the `sed` patch are belt-and-suspenders. Either alone would work, but together they guarantee a fully static build even if PyApp changes its Cargo.toml defaults.

## PyApp env var catalog

Everything the advanced build sets:

| Var | Value | When read | Why |
|---|---|---|---|
| `PYAPP_VERSION` | `v0.29.0` | Shell (git clone) | PyApp release to compile |
| `PYAPP_PROJECT_PATH` | `dist/*.whl` | cargo build | Wheel to embed in the binary |
| `PYAPP_PROJECT_NAME` | `dma` | cargo build | Used by the patched `app.rs` |
| `PYAPP_PROJECT_VERSION` | `1.2.3` | cargo build | Stamped into binary metadata |
| `PYAPP_PYTHON_VERSION` | `3.13` | cargo build | Which PBS archive to match |
| `PYAPP_PROJECT_FEATURES` | `cloudrun` | cargo build | Pass extras to `uv pip install` at first run (ignored when `PYAPP_SKIP_INSTALL=true`) |
| `PYAPP_DISTRIBUTION_VARIANT_CPU` | `v1` | cargo build | CPU baseline (x86-64-v1/v2/v3) |
| `PYAPP_DISTRIBUTION_PATH` | `dist/python-dist.tar.gz` | cargo build | Use pre-built tarball instead of downloading PBS |
| `PYAPP_DISTRIBUTION_EMBED` | `true` | cargo build | Embed the tarball *in* the binary |
| `PYAPP_DISTRIBUTION_PYTHON_PATH` | `python/bin/python3` | cargo build | Path to Python *inside* the tarball |
| `PYAPP_SKIP_INSTALL` | `true` | cargo build | Do not run `uv pip install` on first launch — deps already in tarball |
| `PYAPP_FULL_ISOLATION` | `true` | cargo build | Isolated venv per version, ignore user site-packages |
| `PYAPP_UV_ENABLED` | `true` | cargo build | Use `uv pip` (unused when `SKIP_INSTALL=true`, harmless) |
| `PYAPP_ALLOW_UPDATES` | `true` | cargo build | Enable `<binary> self update` at runtime |
| `BZIP2_SYS_STATIC` | `1` | cargo build | Link libbz2 statically |
| `LZMA_API_STATIC` | `1` | cargo build | Link liblzma statically |

**Critical:** these are **build-time** env vars, consumed while compiling PyApp. Setting them when running the binary does nothing. `PYAPP_PROJECT_NAME` at runtime is a no-op; the compiled binary already has the name baked into the Rust source.

## glibc portability with `cargo-zigbuild`

Plain `cargo build --release` on ubuntu-latest links against whatever glibc the runner has (~2.35 on ubuntu-24.04). The resulting binary fails to start on older distros:

```text
./dma: /lib64/libc.so.6: version `GLIBC_2.28' not found
```

`cargo-zigbuild` wraps Zig's cross-compiler and lets you specify a glibc floor:

```bash
cargo zigbuild --release --target x86_64-unknown-linux-gnu.2.17
```

`.2.17` → CentOS 7 / RHEL 7 / Ubuntu 14.04 era. Works on everything from 2014 onward.

Install (one-line in CI):

```bash
ZIG_VERSION="0.15.2"
curl -fsSL "https://ziglang.org/download/${ZIG_VERSION}/zig-x86_64-linux-${ZIG_VERSION}.tar.xz" | tar -xJ --strip-components=1 -C ~/.local/zig
echo "$HOME/.local/zig" >> $GITHUB_PATH
uv tool install cargo-zigbuild
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
ldd dist/dma
# Expected: libc.so.6, libm.so.6, libpthread.so.0, ld-linux-*.so.2, (none)

# 2. First launch creates the install dir, extracts, runs
./dist/dma --help
ls -la ~/.dma/runtime/
# Expected: lib/, bin/, include/, share/

# 3. Second launch is fast (skips extraction)
time ./dist/dma --help                 # should be < 200ms

# 4. Network isolation test
docker run --rm --network=none \
  -v $PWD/dist:/opt/dist:ro \
  gcr.io/distroless/cc-debian12:nonroot \
  /opt/dist/dma --help
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
