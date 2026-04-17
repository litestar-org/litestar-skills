# PyApp — Simple (hatch-binary)

The path of least resistance: let the `hatch` build backend call PyApp for you. Good when end-users have network access to PyPI and you just want a single-file binary.

Used by **litestar-fullstack-inertia**.

## Full config

```toml
# pyproject.toml
[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[tool.hatch.build.targets.binary]
pyapp-version = "0.29.0"
python-version = "3.12"
scripts = ["app"]
```

Three knobs:

| Key | Meaning | Example |
|---|---|---|
| `pyapp-version` | Git tag of PyApp to compile | `"0.29.0"` |
| `python-version` | Python major.minor bundled into the binary | `"3.12"` |
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

# Build binary via hatch (delegates to PyApp)
uv run hatch build --target binary                   # dist/binary/app
```

Hatch:

1. Clones PyApp at `pyapp-version` into a temp dir.
2. Sets `PYAPP_PROJECT_PATH` to the just-built wheel.
3. Sets `PYAPP_PYTHON_VERSION` to `python-version`.
4. Runs `cargo build --release`.
5. Copies the resulting binary to `dist/binary/<script>`.

The `[tool.hatch.build.targets.binary.env]` table in pyproject.toml lets you set any `PYAPP_*` env var statically. accelerator uses it for the embed/isolation/uv flags:

```toml
[tool.hatch.build.targets.binary.env]
PYAPP_DISTRIBUTION_EMBED = "1"
PYAPP_FULL_ISOLATION = "1"
PYAPP_UV_ENABLED = "1"
PYAPP_ALLOW_UPDATES = "1"
```

| Env var | Effect |
|---|---|
| `PYAPP_DISTRIBUTION_EMBED=1` | Embed the Python distribution tarball *inside* the binary. No download on first run. Binary is larger (~50-100 MB) but offline-capable. |
| `PYAPP_FULL_ISOLATION=1` | Create an isolated venv per version; ignore user site-packages. Required for reliable behavior. |
| `PYAPP_UV_ENABLED=1` | Use `uv pip` for the install step (fast). |
| `PYAPP_ALLOW_UPDATES=1` | Enable the `self update` subcommand at runtime. |

## Release pipeline (multi-platform)

litestar-fullstack-inertia's `release.yml` builds 4 binaries in parallel:

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
            runner: macos-13
          - target: aarch64-apple-darwin
            runner: macos-14
    runs-on: ${{ matrix.runner }}
    needs: build-wheel
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: actions/download-artifact@v7
        with:
          name: wheel
          path: dist/
      - run: uv sync --all-extras --dev
      - run: uv run hatch build --target binary
      - run: |
          mv dist/binary/app dist/binary/app-${{ matrix.target }}
          chmod +x dist/binary/app-${{ matrix.target }}
      - uses: actions/upload-artifact@v6
        with:
          name: binary-${{ matrix.target }}
          path: dist/binary/app-${{ matrix.target }}
```

Then a `publish` job collects all four and uploads to the GitHub release.

## Limitations of the simple flavor

**Install location:** the user can't pick it. PyApp installs to `platform_dirs().data_local_dir()`, which is OS-specific:

- Linux: `~/.local/share/<project>/<distribution_id>/<version>/`
- macOS: `~/Library/Application Support/<project>/<distribution_id>/<version>/`
- Windows: `%LOCALAPPDATA%\<project>\<distribution_id>\<version>\`

Good for typical CLI tools. Wrong if you need `~/.myapp/` or `/opt/myapp/`. For that, see [pyapp-advanced.md](pyapp-advanced.md).

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
