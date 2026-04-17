# Upgrading — Python, PyApp, python-build-standalone

Advanced PyApp setups reference the Python version and the PyApp version in **multiple** files. Upgrading means a careful sweep through all of them, or the build breaks in subtle ways (a PyApp binary that bundles one Python version but runs Rust code expecting another).

## Upgrade: Python major.minor (e.g., 3.13 → 3.14)

### Simple flavor (hatch-binary)

Two files:

```toml
# pyproject.toml
[project]
requires-python = ">=3.11"                # bump if dropping old versions

[tool.hatch.build.targets.binary]
python-version = "3.14"                   # ← bump
```

```yaml
# .github/workflows/release.yml
- run: uv python install 3.14             # ← bump
```

Done.

### Advanced flavor (custom bundler)

Five files. The list below references accelerator paths — adapt to your layout.

**1. `pyproject.toml`:**

```toml
[project]
requires-python = ">=3.11"

[tool.hatch.build.targets.binary]
python-version = "3.14"                   # ← bump
```

**2. `tools/scripts/build-onefile-package.sh`:**

```bash
export PYAPP_PYTHON_VERSION="3.14"        # ← bump
```

**3. `.github/workflows/release.yml`:**

```yaml
env:
  PYAPP_PYTHON_VERSION: "3.14"            # ← bump
  STABLE_PYTHON_VERSION: "3.14"           # ← bump
```

**4. `.github/workflows/ci.yml`:**

```yaml
env:
  STABLE_PYTHON_VERSION: "3.14"           # ← bump

strategy:
  matrix:
    python-version: ["3.12", "3.13", "3.14"]    # ← add new, drop oldest if appropriate
```

**5. `tools/bundler.py`:**

```python
DEFAULT_PYTHON_VERSION = "3.14"           # ← bump

# Update PBS URLs for the new patch version. Get the latest release tag from:
# https://github.com/astral-sh/python-build-standalone/releases
# Then substitute cpython-3.14.X into each URL.
DEFAULT_URLS: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/20260414/cpython-3.14.1%2B20260414-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    # ... same for other targets ...
}
```

**6. Composite action default (`.github/actions/setup-python/action.yml`):**

```yaml
inputs:
  python-version:
    default: "3.14"                       # ← bump
```

### Verification (Python bump)

```bash
# Clean rebuild
make clean
make build-onefile

# Binary reports the new Python
./dist/<app> --help
./dist/<app> python --version             # should show 3.14.X (if your CLI exposes this)

# CI matrix runs green on the new version
```

## Upgrade: PyApp version (e.g., 0.29.0 → 0.30.0)

Before upgrading, **read the PyApp CHANGELOG**: <https://github.com/ofek/pyapp/releases>. Breaking changes in 0.x are common.

### Simple flavor

One file:

```toml
# pyproject.toml
[tool.hatch.build.targets.binary]
pyapp-version = "0.30.0"                  # ← bump
```

### Advanced flavor

Three files:

**1. `pyproject.toml`:**

```toml
[tool.hatch.build.targets.binary]
pyapp-version = "0.30.0"                  # ← bump (even if not using hatch-binary, keeps metadata consistent)
```

**2. `tools/scripts/build-onefile-package.sh`:**

```bash
export PYAPP_VERSION="v0.30.0"            # ← bump
```

**3. `.github/workflows/release.yml`:**

```yaml
env:
  PYAPP_VERSION: v0.30.0                  # ← bump
```

### Verification (PyApp bump)

After bumping:

1. **Check the install-dir patch still applies.** The regex in `patch_pyapp_install_dir()` matches the PyApp source. Upstream refactors break it:

   ```python
   # tools/bundler.py:431-453
   pattern = re.compile(
       r"platform_dirs\(\)\s*\.data_local_dir\(\)\s*"
       r"\.join\(project_name\(\)\)\s*"
       r"\.join\(distribution_id\(\)\)\s*"
       r"\.join\(project_version\(\)\)"
   )
   ```

   Test:

   ```bash
   git clone --depth 1 --branch v0.30.0 https://github.com/ofek/pyapp /tmp/pyapp-new
   grep -E "platform_dirs\(\)" /tmp/pyapp-new/src/app.rs
   ```

   If the pattern doesn't match, update the regex. The replacement expression (`render_install_dir_expression`) usually doesn't need changes — PyApp's `directories::BaseDirs` dependency is stable.

2. **Check the Cargo.toml `sed` patch for static linking.** If PyApp changes its dependency names or moves the `[dependencies]` section, the `sed` invocations break:

   ```bash
   sed -i 's/bzip2 = "\([^"]*\)"/bzip2 = { version = "\1", features = ["static"] }/' Cargo.toml
   sed -i '/\[dependencies\]/a bzip2-sys = { version = "*", features = ["static"] }' Cargo.toml
   ```

3. **Rebuild and smoke-test.** Offline test in particular — the biggest PyApp regressions touch tarball extraction.

## Upgrade: python-build-standalone (PBS) release tag

PBS ships a new stripped-install archive every month or so. You don't have to match the latest — pick a release that covers the Python patch versions you want.

Get the release list: <https://github.com/astral-sh/python-build-standalone/releases>.

Update **one** location:

```python
# tools/bundler.py:45-62
DEFAULT_URLS: dict[str, str] = {
    "x86_64-unknown-linux-gnu":  "https://github.com/astral-sh/python-build-standalone/releases/download/<NEW_RELEASE_TAG>/cpython-<VERSION>%2B<NEW_RELEASE_TAG>-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "aarch64-unknown-linux-gnu": "https://github.com/astral-sh/python-build-standalone/releases/download/<NEW_RELEASE_TAG>/cpython-<VERSION>%2B<NEW_RELEASE_TAG>-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
    "x86_64-apple-darwin":       "...",
    "aarch64-apple-darwin":      "...",
    "x86_64-pc-windows-msvc":    "...",
}
```

Also clear the cache before rebuilding — old archives stay in `.cache/bundler/` until you prune:

```bash
uv run tools/bundler.py manage cache --clear
```

Then `make build-onefile` fetches the new archive.

## Change the PyApp install location

The install root is set via `bundler.py --install-root`. Pick somewhere under `$HOME` to keep the binary relocatable across users.

Edit **one** file:

```bash
# tools/scripts/build-onefile-package.sh
uv run tools/bundler.py build \
  --requirements dist/requirements.txt \
  --output dist/python-dist.tar.gz \
  --pyapp-dir ${PYAPP_DIR} \
  --install-root "~/.myapp" \              # ← change here
  --project-name "runtime"
```

`~/.myapp/runtime/` is where the binary will extract and run from. `--install-root` accepts any path:

- `~/.myapp` → `~/.myapp/runtime/` (relocatable across users via `BaseDirs::home_dir()` at runtime)
- `/opt/myapp` → `/opt/myapp/runtime/` (hardcoded PathBuf, absolute, requires sudo on first run)
- `/usr/local/lib/myapp` → same as above

The logic that generates the Rust expression from `--install-root` is in `bundler.py:417-428`. See [pyapp-advanced.md](pyapp-advanced.md) for details.

**Also consider updating your app's own runtime defaults** if they reference the old install location:

```python
# src/py/dma/cli/commands/manage.py (accelerator)
default="~/.dma"                          # ← update to match --install-root
```

## Add a new target platform

The long version is in [pyapp-advanced.md](pyapp-advanced.md). The short version is:

**1. `tools/bundler.py` — add URL and platform mappings:**

```python
DEFAULT_URLS: dict[str, str] = {
    ...
    "aarch64-pc-windows-msvc": "https://github.com/astral-sh/python-build-standalone/releases/download/<TAG>/cpython-<VERSION>%2B<TAG>-aarch64-pc-windows-msvc-install_only_stripped.tar.gz",
}

DEFAULT_PLATFORMS: dict[str, str] = {
    ...
    "aarch64-pc-windows-msvc": "aarch64-pc-windows-msvc",
}
```

**2. `.github/workflows/release.yml` — add matrix entry:**

```yaml
matrix:
  job:
    - target: aarch64-pc-windows-msvc
      os: windows-11-arm
      artifact: app-aarch64-windows-msvc
```

**3. Adjust the build command if the platform needs it.** Windows doesn't use `cargo-zigbuild`:

```yaml
- name: Build PyApp onefile (Windows)
  if: contains(matrix.job.target, 'windows')
  working-directory: ${{ env.PYAPP_REPO }}
  env:
    PYAPP_PROJECT_PATH: ${{ github.workspace }}\dist\app-${{ steps.version.outputs.VERSION }}-py3-none-any.whl
    PYAPP_DISTRIBUTION_PATH: ${{ github.workspace }}\dist\python-dist-${{ matrix.job.target }}.tar.gz
    PYAPP_DISTRIBUTION_EMBED: "true"
    PYAPP_DISTRIBUTION_PYTHON_PATH: python\python.exe
    PYAPP_SKIP_INSTALL: "true"
  run: cargo build --release --target ${{ matrix.job.target }}
```

## The sync-point matrix

For an advanced setup, here's the full map. Any version bump touches the marked files:

| File | Python ver | PyApp ver | PBS URL | Install dir |
| --- | :---: | :---: | :---: | :---: |
| `pyproject.toml` | ✓ | ✓ | — | — |
| `tools/scripts/build-onefile-package.sh` | ✓ | ✓ | — | ✓ |
| `tools/bundler.py` | ✓ | — | ✓ | — |
| `.github/workflows/release.yml` | ✓ | ✓ | — | — |
| `.github/workflows/ci.yml` | ✓ | — | — | — |
| `.github/actions/setup-python/action.yml` | ✓ | — | — | — |
| App runtime defaults (e.g. CLI `--install-dir`) | — | — | — | ✓ |

Routine: do the edit, run `make clean && make build-onefile`, verify with the checklist in [pyapp-advanced.md](pyapp-advanced.md) § Verification.

## Downgrade / rollback

If an upgrade breaks, the simplest rollback is `git revert` of the bump commit. The regex patches, the bundler CLI, and the workflow jobs are all in-tree — reverting the PR flips everything atomically.

Keep PRs small (one version bump per PR) to make this work.
