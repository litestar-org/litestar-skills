# Standalone Onefiles with `a-scie/jump` (`scie-jump` v1.13.0)

Build zero-dependency, self-contained executables (`scies`) by combining [`a-scie/jump`](https://github.com/a-scie/jump) (`v1.13.0`), `python-build-standalone`, and `uv`-staged `site-packages` — **without** a Rust toolchain or `cargo-zigbuild`.

## PyApp vs `scie-jump`

| Dimension | PyApp (`ofek/pyapp`) | `scie-jump` (`a-scie/jump`) |
| --- | --- | --- |
| Host build toolchain | Rust (`cargo`) + `zig` / `cargo-zigbuild` on Linux | None — uses prebuilt `scie-jump` release binaries |
| Dependency resolution | Runtime `uv`/`pip` install on first launch (unless pre-populated tarball) | Build-time `uv pip install --target` into `python/` archive |
| Cross-OS assembly | Requires host OS toolchain or cross-linker per target | Single host assembles Linux, macOS, and Windows scies via `--scie-jump` |
| Extraction cache | `~/.<app>/runtime` (`PYAPP_INSTALL_DIR_<PROJECT_NAME>`) | Deterministic NCE/CAS (`~/.cache/nce` or `scie.lift.base`, `SCIE_BASE`) |
| Self-management CLI | Built-in `self update`, `self remove`, `self restore` | Launcher-only (`SCIE=inspect` / `SCIE_BASE`); upgrades replace the binary |
| Binary patchability | Compile-time `src/app.rs` patches + `PYAPP_*` env vars | Declarative `lift.json` manifest appended to the stub |

Choose **`scie-jump`** when you want fast, Rust-free builds, pre-staged `site-packages` with zero first-run installs, and cross-platform assembly from one build script. Choose **PyApp** when end users rely on `self update` / `self remove`, `PYAPP_INSTALL_DIR_<PROJECT_NAME>`, or custom compiled-in launcher logic.

## Target Matrix (`v1.13.0` + `python-build-standalone`)

| Target | `a-scie/jump` `v1.13.0` Asset | PBS Target Triple | `uv --python-platform` | Archive Format |
| --- | --- | --- | --- | --- |
| Linux x86_64 | `scie-jump-linux-x86_64` | `x86_64-unknown-linux-gnu` | `x86_64-manylinux_2_17` | `.tar.gz` |
| Linux aarch64 | `scie-jump-linux-aarch64` | `aarch64-unknown-linux-gnu` | `aarch64-manylinux_2_17` | `.tar.gz` |
| macOS Apple Silicon | `scie-jump-macos-aarch64` | `aarch64-apple-darwin` | `aarch64-apple-darwin` | `.tar.gz` |
| macOS Intel | `scie-jump-macos-x86_64` | `x86_64-apple-darwin` | `x86_64-apple-darwin` | `.tar.gz` |
| Windows x86_64 | `scie-jump-windows-x86_64.exe` | `x86_64-pc-windows-msvc` | `x86_64-pc-windows-msvc` | `.zip` |

Download URLs follow:

- `scie-jump`: `https://github.com/a-scie/jump/releases/download/v1.13.0/<asset>` (and `<asset>.sha256`)
- `python-build-standalone`: `https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.13.18+20261026-<pbs-triple>-install_only_stripped.tar.gz`

Always verify downloaded `scie-jump` binaries and `python-build-standalone` tarballs against pinned SHA-256 checksums before extraction or assembly.

## End-to-End Generic Pipeline

### Step 1: Build the wheel and export locked requirements

Build the self-contained wheel first, then export runtime-only requirements from `uv.lock` without the project entry (the wheel provides the project itself):

```bash
uv build --wheel --clear
uv export \
  --format requirements.txt \
  --color never \
  --no-annotate \
  --frozen \
  --no-dev \
  --no-editable \
  --no-hashes \
  --no-header \
  --no-emit-project \
  -o dist/.scratch/requirements.txt
```

(`uv export` also accepts `--no-color` as a legacy alias for `--color never`; use `--frozen` in air-gapped or CI release jobs so `uv.lock` is never re-resolved.)

### Step 2: Safely extract `python-build-standalone`

Extract `install_only_stripped.tar.gz` using `tarfile` with `filter="data"` (Python 3.12+) or explicit path-traversal validation:

```python
import hashlib
from pathlib import Path
import tarfile


def verify_sha256(path: Path, expected_hex: str) -> None:
    """Verify file integrity against an expected SHA-256 digest."""
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_hex.lower():
        msg = f"SHA-256 mismatch for {path.name}: expected {expected_hex}, got {actual}"
        raise ValueError(msg)


def safe_extract_tar(archive: Path, dest: Path) -> None:
    """Extract a tar.gz archive safely with path traversal filtering."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest, filter="data")
```

This creates `<dest>/python/` (`python/bin/python3` on POSIX, `python/python.exe` on Windows).

### Step 3: Stage dependencies and wheel into `site-packages`

Install the exported `requirements.txt` and built wheel directly into the extracted runtime's `site-packages` directory:

- POSIX `site-packages`: `<staging>/python/lib/python3.13/site-packages`
- Windows `site-packages`: `<staging>/python/Lib/site-packages`

When staging for the **same host OS/architecture** as the build runner, point `--python` at the extracted interpreter and pass `--compile-bytecode`:

```bash
uv pip install \
  --target dist/.scratch/staging/python/lib/python3.13/site-packages \
  --python dist/.scratch/staging/python/bin/python3 \
  --compile-bytecode \
  --reinstall \
  -r dist/.scratch/requirements.txt \
  dist/my_app-*.whl
```

When staging **cross-platform** from Linux or macOS, replace `--python` / `--compile-bytecode` with `--python-platform` and `--python-version` (and add `--offline` in air-gapped environments with a warm `uv` cache):

```bash
uv pip install \
  --target dist/.scratch/staging/python/Lib/site-packages \
  --python-platform x86_64-pc-windows-msvc \
  --python-version 3.13 \
  --reinstall \
  -r dist/.scratch/requirements.txt \
  dist/my_app-*.whl
```

Then pack `<staging>/python/` into `dist/.scratch/python-dist.tar.gz` (POSIX, preserving executable bits on `python/bin/*`) or `dist/.scratch/python-dist.zip` (Windows).

### Step 4: Render `lift.json` and assemble the scie

Create `dist/.scratch/lift.json` referencing the packed archive (`key: "python-dist"`) and defining the default boot command `""`:

```json
{
  "scie": {
    "jump": {
      "size": 1731520,
      "version": "1.13.0"
    },
    "lift": {
      "name": "my-app",
      "description": "Self-contained my-app executable",
      "load_dotenv": false,
      "base": "{scie.env.SCIE_BASE}",
      "files": [
        {
          "name": "python-dist.tar.gz",
          "key": "python-dist",
          "size": 52428800,
          "hash": "<sha256-of-python-dist.tar.gz>",
          "type": "tar.gz"
        }
      ],
      "boot": {
        "commands": {
          "": {
            "exe": "{python-dist}/python/bin/python3",
            "args": ["-s", "-m", "my_app"],
            "env": {
              "=PYTHONNOUSERSITE": "1",
              "=PYTHONPATH": "",
              "SSL_CERT_FILE": "{python-dist}/python/lib/python3.13/site-packages/certifi/cacert.pem"
            }
          }
        }
      }
    }
  }
}
```

Platform adjustments for Windows targets (`type: "zip"`):

- `"name": "python-dist.zip"` and `"type": "zip"`
- `"exe": "{python-dist}/python/python.exe"`
- `"SSL_CERT_FILE": "{python-dist}/python/Lib/site-packages/certifi/cacert.pem"`

Notes on manifest fields:

- `"load_dotenv": false` prevents `scie-jump` from implicitly loading arbitrary `.env` files in the user's current working directory before Python boots; omit `"base"` (or let `SCIE_BASE` / `{scie.user.cache_dir}/nce` handle defaults) when standard NCE cache layout is desired.
- Prefixing `"=PYTHONNOUSERSITE": "1"` and `"=PYTHONPATH": ""` uses `scie-jump`'s `=` override operator so host user-site packages or `PYTHONPATH` never leak into the isolated runtime.
- Setting `SSL_CERT_FILE` to bundled `certifi/cacert.pem` ensures outbound TLS calls (`httpx`, `urllib`, OAuth) succeed inside minimal containers or hosts without system CA stores.

Assemble the final binary with the **host** `scie-jump` binary, passing `--scie-jump` to embed the **target** OS/architecture stub, then emit a `.sha256` sidecar:

```bash
# Same-host assembly writes ./my-app in the manifest directory (or current directory)
./bin/scie-jump-linux-x86_64 \
  --scie-jump ./bin/scie-jump-windows-x86_64.exe \
  dist/.scratch/lift.json

sha256sum dist/my-app-windows-x86_64.exe > dist/my-app-windows-x86_64.exe.sha256
```

Make POSIX output binaries executable (`chmod +x dist/my-app-*`) and clean up `dist/.scratch/` after publishing.

## Guardrails

- **Verify `certifi` is a runtime dependency** if you set `SSL_CERT_FILE` to `site-packages/certifi/cacert.pem`; otherwise Python TLS verification fails with missing-file errors.
- **Cross-staging requires binary wheels for the target platform.** Pure-Python and manylinux/macOS/Windows wheels on PyPI resolve cleanly with `--python-platform`; packages that require local source compilation (sdists without matching wheels) must build on a native runner or pre-populated wheelhouse.
- **Pass `-s` alongside `=PYTHONNOUSERSITE: "1"`** so user site-packages never shadow bundled versions.
- **Remove scratch files and NCE test caches on CI runners.** Testing `./dist/my-app --help` populates `~/.cache/nce` (`$SCIE_BASE`); prune `dist/.scratch` and cache dirs before downstream Docker builds.
