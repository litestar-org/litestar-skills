# PyApp — Simple (hatch-binary)

The path of least resistance: let the `hatch` build backend call PyApp for you. Good when end-users have network access to PyPI and you just want a single-file binary.

Used by **[litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia)**.

## Full config

```toml
# pyproject.toml
[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[tool.hatch.build.targets.binary]
pyapp-version = "0.31.0"
python-version = "3.13"
scripts = ["app"]
```

Three knobs:

| Key | Meaning | Example |
| --- | --- | --- |
| `pyapp-version` | Crates.io version of `pyapp` to compile (no `v` prefix) | `"0.31.0"` |
| `python-version` | Python major.minor bundled into the binary | `"3.13"` |
| `scripts` | Names of console scripts (from `[project.scripts]`) that become binary entry-points | `["app"]` |

`scripts` must match one of your `[project.scripts]` entries:

```toml
[project.scripts]
app = "app.__main__:run"
```

## Build

```bash
# Prereqs: uv sync, assets built, wheel buildable
make build-wheel                                     # dist/app-X.Y.Z-py3-none-any.whl

# Build binary via hatch (delegates to PyApp via Cargo; use `uvx hatch` if hatch is not in dev deps)
PYAPP_PROJECT_PATH="$(realpath dist/app-*.whl)" \
PYAPP_DISTRIBUTION_EMBED=1 \
PYAPP_FULL_ISOLATION=1 \
PYAPP_UV_ENABLED=1 \
  hatch build --target binary                        # dist/binary/app-X.Y.Z
```

Hatch (`hatchling.builders.binary.BinaryBuilder`):

1. Sets `PYAPP_PROJECT_NAME`, `PYAPP_PROJECT_VERSION`, `PYAPP_PYTHON_VERSION` (from `python-version`), and `PYAPP_EXEC_SPEC` (for each script in `scripts`).
2. Inherits all `PYAPP_*` variables from the process environment (`os.environ`).
3. Runs `cargo install pyapp --force --root <temp_dir> --version <pyapp-version>` from crates.io (or `cargo build --release` when `PYAPP_REPO` points to a local PyApp checkout).
4. Writes each resulting binary to `dist/binary/<script>-<version>` (or `dist/binary/<script>-<version>-<CARGO_BUILD_TARGET>` when `CARGO_BUILD_TARGET` is set).

Note: Hatchling's `binary` builder does **not** set `PYAPP_PROJECT_PATH` automatically and does **not** read a `[tool.hatch.build.targets.binary.env]` TOML table. Export `PYAPP_*` variables in your shell or CI `env:` block — without `PYAPP_PROJECT_PATH`, PyApp fetches the package from PyPI by name and version on first run instead of embedding your local wheel.

```bash
export PYAPP_PROJECT_PATH="$(realpath dist/app-*.whl)"
export PYAPP_DISTRIBUTION_EMBED="1"
export PYAPP_FULL_ISOLATION="1"
export PYAPP_UV_ENABLED="1"
export PYAPP_ALLOW_UPDATES="1"
```

| Env var | Effect |
| --- | --- |
| `PYAPP_DISTRIBUTION_EMBED=1` | Embed the Python distribution tarball *inside* the binary. No download on first run. Binary is larger (~50-100 MB) but offline-capable. |
| `PYAPP_FULL_ISOLATION=1` | Create an isolated venv per version; ignore user site-packages. Required for reliable behavior. |
| `PYAPP_UV_ENABLED=1` | Use `uv pip` for the install step (fast). |
| `PYAPP_ALLOW_UPDATES=1` | Enable the `self update` subcommand at runtime. |
| `PYAPP_DISTRIBUTION_VARIANT_GIL` | Optional on Python 3.13+: set to `freethreaded` to select the free-threaded (no-GIL) distribution variant when using default PBS archives. |

At runtime, the compiled PyApp wrapper sets `PYAPP=1` in the environment (or the binary's path when built with `PYAPP_PASS_LOCATION=1`), so application code can detect onefile execution via `bool(os.getenv("PYAPP"))`. Users can also override the runtime extraction directory by exporting `PYAPP_INSTALL_DIR_<PROJECT_NAME>=/custom/path` (where `<PROJECT_NAME>` is the uppercased `PYAPP_PROJECT_NAME` with `-` replaced by `_`; keep it set when invoking `<binary> self remove` or `<binary> self restore`).

## Release pipeline (multi-platform)

litestar-fullstack-inertia's `release.yml` builds 4 binaries in parallel (note: GitHub retired `macos-13` on Dec 4, 2025; use `macos-15-intel` for x86_64 macOS until its planned Fall 2027 retirement, and `macos-15` for Apple Silicon):

```yaml
# .github/workflows/release.yml
jobs:
  build-binary:
    strategy:
      matrix:
        include:
          - target: x86_64-unknown-linux-gnu
            runner: ubuntu-latest
          - target: aarch64-unknown-linux-gnu
            runner: ubuntu-24.04-arm
          - target: x86_64-apple-darwin
            runner: macos-15-intel
          - target: aarch64-apple-darwin
            runner: macos-15
    runs-on: ${{ matrix.runner }}
    needs: build-wheel
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.3
      - run: uv python install 3.13
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: actions/download-artifact@v8
        with:
          name: wheel
          path: dist/
      - run: uv sync --all-extras --dev
      - name: Build binary
        env:
          PYAPP_DISTRIBUTION_EMBED: "1"
          PYAPP_FULL_ISOLATION: "1"
          PYAPP_UV_ENABLED: "1"
        run: |
          export PYAPP_PROJECT_PATH="$(realpath dist/*.whl)"
          uvx hatch build --target binary
      - run: |
          mv dist/binary/app-* dist/binary/app-${{ matrix.target }}
          chmod +x dist/binary/app-${{ matrix.target }}
      - uses: actions/upload-artifact@v7
        with:
          name: binary-${{ matrix.target }}
          path: dist/binary/app-${{ matrix.target }}
```

Then a `publish` job collects all four and uploads to the GitHub release.

## Limitations of the simple flavor

**Default install location:** By default, PyApp extracts into `platform_dirs().data_local_dir().join(project_name()).join(distribution_id()).join(project_version())`, which is OS-specific:

- Linux: `~/.local/share/<project>/<distribution_id>/<version>/`
- macOS: `~/Library/Application Support/<project>/<distribution_id>/<version>/`
- Windows: `%LOCALAPPDATA%\<project>\<distribution_id>\<version>\`

Users can override this at **runtime** via `PYAPP_INSTALL_DIR_<PROJECT_NAME>=/custom/path` (where `<PROJECT_NAME>` is the uppercased `PYAPP_PROJECT_NAME` with `-` replaced by `_`; keep it set when running `<binary> self remove` or `<binary> self restore`), but `hatch-binary` cannot change the **compiled-in default** directory (e.g., making the binary default to `~/.myapp/runtime/` or `/opt/myapp/` without requiring a runtime env var). For a custom compiled-in default, see [pyapp-advanced.md](pyapp-advanced.md).

**Offline installs:** without `PYAPP_DISTRIBUTION_EMBED=1` the binary downloads Python on first run. With it, the binary still calls `uv pip install` at first run, which fetches wheels from PyPI — so you're not fully air-gapped. For fully offline binaries, see [pyapp-advanced.md](pyapp-advanced.md).

**No custom cross-compilation:** hatch-binary uses `cargo build --release`. It doesn't know about `cargo-zigbuild` for portable glibc, so the Linux binary you build on Ubuntu 24.04 won't run on CentOS 7. If your users run older distros, see [pyapp-advanced.md](pyapp-advanced.md).

**Version upgrades are two edits:** bumping `pyapp-version` in pyproject.toml is enough to pull a new PyApp. Bumping `python-version` is enough to ship a new Python. For advanced flavors you also have to edit scripts and workflow env.

## When to stay simple

- End-users have PyPI / GitHub network access
- Target platforms are recent (Ubuntu 22.04+, macOS 13+, Windows Server 2022+)
- Default XDG install location is fine
- You want one source of truth (pyproject.toml)

Ship with hatch-binary. Save a day of engineering.

## When to move to advanced

- Air-gapped customer environments
- Custom install location requirements (corporate policy, `/opt/<app>/`)
- Must support CentOS 7 / RHEL 8 / glibc < 2.28
- Need to pre-install platform-specific wheels (e.g. DuckDB, oracledb) that differ per target
- Binary size and cold-start matter — you want to strip Python and pre-compile `.pyc`

Then jump to [pyapp-advanced.md](pyapp-advanced.md).
