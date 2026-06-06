---
name: litestar-build
description: "Auto-activate for uv build, hatch build, PyApp, PYAPP_*, wheel assets, GitHub release matrices, cargo-zigbuild, or python-build-standalone. Not for runtime deployment."
---

# litestar-build

Build-side packaging patterns for Litestar applications: how to produce a **self-contained wheel** that embeds the Vite/Bun frontend, how to wrap that wheel in a **PyApp onefile** binary, and how to wire the whole pipeline into **GitHub Actions** CI and releases.

This skill is the counterpart to [litestar-deployment](../litestar-deployment/SKILL.md) — build is about producing artifacts, deployment is about running them.

## The Core Idea: One Wheel, Self-Contained

A Litestar wheel is the single source of truth for a release. It contains:

- Python code (`src/py/app/` or `app/`)
- SQL migrations, Jinja templates, INI configs
- The **built** Vite/Bun frontend bundle (JS, CSS, HTML, images)
- Email templates rendered from React/MJX to static HTML

Once produced, that wheel can be:

1. `pip install`ed into a container (litestar-deployment).
2. Wrapped in a **PyApp** binary (`dist/<app>`, `dist/app-x86_64-linux-gnu`) for zero-dep distribution.
3. Uploaded to PyPI or a private index.

All three paths assume the wheel is **already complete** — no `bun run build` happens at deploy/install time.

### Why bundle assets into the wheel (and not serve from a CDN)

| Property | Bundled wheel | External CDN |
| --- | --- | --- |
| Deploy artifacts | 1 (`.whl` or binary) | 2+ (wheel + CDN upload) |
| Version alignment | Atomic — API and UI lock-step | Easy to skew; rollback is painful |
| PyApp onefile | Required — the binary embeds the wheel | Not possible — binary can't fetch CDN URLs at install time |
| Offline/air-gapped | Works | Doesn't |
| Dev server startup | Instant (files on disk next to package) | Fine |
| Frontend-only deploys | Rebuild + redeploy wheel | Push to CDN only |

For **most Litestar apps that ship as a product** (CLIs, internal tools, enterprise installers), bundled-in-wheel is correct. Projects like [litestar-fullstack-inertia](#example-projects) and [litestar-fullstack](#example-projects) all bundle.

### Why litestar-vite configs look the way they do in reference apps

This is the piece most developers miss. The Vite/litestar-vite configs in the reference apps are **deliberately set up so the Vite output lands inside the Python package directory** — because that's what makes the wheel pick them up automatically.

**litestar-fullstack** (`src/js/web/vite.config.ts`):

```ts
export default defineConfig({
  build: {
    outDir: path.resolve(__dirname, "../../py/app/server/static/web"),  // ← inside src/py/app/ (the Python package)
    emptyOutDir: true,
  },
  plugins: [
    litestar({
      bundleDir: path.resolve(__dirname, "../../py/app/server/static/web"),
      hotFile: path.resolve(__dirname, "../../py/app/server/static/web/hot"),
    }),
  ],
})
```

**litestar-fullstack-inertia** — the litestar-vite plugin resolves `bundle_dir` relative to the project root, and Python settings point it at a package-internal path:

```python
# app/lib/settings.py
return ViteConfig(
    paths=PathConfig(
        root=BASE_DIR.parent,
        bundle_dir=Path("app/domain/web/public"),   # ← inside app/ (the Python package)
        resource_dir=Path("resources"),
    ),
)
```

**Advanced reference pattern** — same approach: Vite and the offline-report build write to `src/py/<app>/server/public/` and `src/py/<app>/domain/web/static/reports/offline/`, both under the package root.

Contrast with a naïve `vite build` that writes to `./dist/` at the repo root: those files are **outside** the package directory listed in `[tool.hatch.build.targets.wheel] packages = [...]`, so Hatchling silently drops them. The wheel ships without a frontend.

Rule: **Vite's `outDir` and litestar-vite's `bundle_dir` must point inside one of the Python packages that Hatchling is told to include.** Everything else flows from that.

## Quick Reference

| Topic | Reference | Key Commands |
| --- | --- | --- |
| Wheel build + asset bundling | [references/wheel-assets.md](references/wheel-assets.md) | `uv build --wheel`, `[tool.hatch.build.targets.wheel.force-include]`, `ignore-vcs = true` |
| PyApp — simple (hatch-binary) | [references/pyapp-simple.md](references/pyapp-simple.md) | `uv run hatch build --target binary` |
| PyApp — advanced (offline + custom install dir) | [references/pyapp-advanced.md](references/pyapp-advanced.md) | `tools/bundler.py build`, `cargo zigbuild` |
| GitHub Actions CI (test matrix) | [references/github-ci.md](references/github-ci.md) | `astral-sh/setup-uv@v7`, `oven-sh/setup-bun@v2`, composite actions |
| GitHub Actions release | [references/github-release.md](references/github-release.md) | matrix onefiles, `cargo-zigbuild`, `gh release create` |
| Upgrading Python / PyApp | [references/upgrading.md](references/upgrading.md) | Files to edit in sync |

## Canonical Makefile Build Graph

Every Litestar app with bundled assets has some variant of this:

```makefile
.PHONY: install build-assets build-wheel build-onefile

install:                          ## Install Python + JS deps
	@uv sync --all-groups
	@cd src/js/web && bun install --frozen-lockfile

build-assets:                     ## Build frontend into the Python package
	@uv run app assets install
	@uv run app assets build

build-wheel: build-assets         ## Self-contained Python wheel
	@uv build --wheel

build-onefile: build-wheel        ## Single-file PyApp binary
	@./tools/scripts/build-onefile-package.sh
```

The dependency chain is **load-bearing**: `build-onefile` depends on `build-wheel`, which depends on `build-assets`. Running them out of order produces an empty or broken artifact.

### The two-variant story

Real projects have multiple JS build outputs that all need to land in the wheel:

```makefile
js-build-all: js-build-web js-build-offline-report
build-wheel: generate-licenses build-templates js-build-all
	@uv build --wheel
```

Each `js-build-*` target emits into a distinct subdirectory of the Python package (`src/py/<app>/server/public`, `src/py/<app>/domain/web/static/reports/offline`, etc.). Because they're all inside the package, a single `uv build --wheel` captures everything.

<workflow>

## Workflow

### Step 1: Point Vite output inside the Python package

Open `vite.config.ts`. Set `build.outDir` to an absolute path inside your Python package (`src/py/<pkg>/...` or `<pkg>/...`). Set `litestar({ bundleDir, hotFile })` to the same path. **Do not** let Vite default to `./dist/`.

### Step 2: Choose a Hatchling bundling strategy

- **`force-include`** (inertia): List the built-asset directory explicitly under `[tool.hatch.build.targets.wheel.force-include]`. Built assets stay `.gitignore`d. Explicit, auditable.
- **`ignore-vcs = true`** (SPA): Tell Hatchling to ignore `.gitignore`. All package files ship. Simpler; requires discipline to keep dev junk out of package dirs.

See [references/wheel-assets.md](references/wheel-assets.md) for full config.

### Step 3: Wire Makefile targets

Create `install`, `build-assets`, `build-wheel`. Make the wheel target **depend** on the asset target. Add any secondary generators (`build-templates`, `generate-licenses`) as additional wheel prerequisites.

### Step 4: Add PyApp (if shipping a binary)

Decide which flavor:

- **Simple**: add `[tool.hatch.build.targets.binary]` to pyproject.toml and run `uv run hatch build --target binary`. Good when end-users have PyPI access. See [pyapp-simple.md](references/pyapp-simple.md).
- **Advanced**: write a `tools/bundler.py` that pre-installs deps into a `python-build-standalone` archive, patches PyApp's `src/app.rs` for a custom install dir, then runs `cargo zigbuild`. Good for air-gapped distribution or bespoke install locations. See [pyapp-advanced.md](references/pyapp-advanced.md).

### Step 5: Add GitHub Actions CI

Start with a reusable `test.yml` that accepts `python-version` + `coverage` inputs. Call it from `ci.yml` across a matrix. Use `astral-sh/setup-uv@v7` and `oven-sh/setup-bun@v2`. See [github-ci.md](references/github-ci.md).

For larger projects, factor `setup-python` and `setup-node` into `.github/actions/` composite actions.

### Step 6: Add release workflow

Trigger on `v*` tags. Run the test matrix first. Then build the wheel once. Then build PyApp onefiles in a per-target matrix (`x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, Apple, Windows). Upload to `gh release create`. See [github-release.md](references/github-release.md).

</workflow>

<guardrails>

## Guardrails

- **Vite/bun output must land inside a Python package directory.** Otherwise Hatchling drops it. Set `build.outDir` and `litestar({ bundleDir })` to an absolute path under `src/py/<pkg>/` or `<pkg>/`.
- **`uv build` runs last.** Assets, licenses, templates, OpenAPI TypeGen all run **before** `uv build --wheel`. Hatchling can't build Vite itself.
- **Pick one bundling strategy.** `force-include` or `ignore-vcs = true`, not both. Mixing them causes duplicate-file warnings and unpredictable wheel contents.
- **PyApp envs are build-time, not runtime.** `PYAPP_PROJECT_NAME`, `PYAPP_PYTHON_VERSION`, `PYAPP_DISTRIBUTION_EMBED` are consumed when `cargo build` compiles PyApp — not when the resulting binary runs. Setting them at runtime does nothing.
- **PyApp version upgrades touch multiple files.** `pyproject.toml`, `build-onefile-package.sh`, `.github/workflows/release.yml`, `tools/bundler.py`. See [upgrading.md](references/upgrading.md).
- **`cargo-zigbuild` for portable glibc.** Plain `cargo build` on a modern Linux runner produces binaries that fail on older distros (glibc too new). Use `cargo zigbuild --target x86_64-unknown-linux-gnu.2.17` to link against glibc 2.17 (CentOS 7-era). Required for broad compatibility.
- **Static-link native deps in PyApp.** Set `BZIP2_SYS_STATIC=1` and `LZMA_API_STATIC=1` before `cargo zigbuild`, or patch `Cargo.toml` to add `features = ["static"]`. Otherwise the onefile fails to load on systems without matching `libbz2.so` / `liblzma.so`.
- **Pin `uv` and `bun` versions in CI.** Use exact pinned versions (e.g., `UV_VERSION=0.11.6` and `BUN_INSTALL_VERSION=bun-v1.3.12`). Drift in either breaks reproducible builds.
- **Create placeholder asset dirs in CI.** Hatchling's wheel target fails if `app/domain/web/public` or `src/py/app/server/static/web` doesn't exist at wheel-build time. CI jobs that don't build the frontend (lint, mypy, pyright) still need `mkdir -p <asset-dir>` before `uv sync`.
- **Never commit built frontend output.** Keep `bundle_dir` paths in `.gitignore`. CI rebuilds them on every run. Reason: JS builds are non-deterministic across machines and cause noisy diffs.
- **Coverage on one Python version only.** Multiple versions uploading the same `coverage.xml` silently stomp each other. Pin it to one version in your matrix (`if: matrix.python-version == '3.12'`).
- **Disk cleanup on self-hosted runners.** GitHub's `ubuntu-latest` has ~30GB free; building wheels + PyApp + Docker images can blow past that. Aggressive cleanup before the build job is routine.

</guardrails>

<validation>

## Validation Checkpoint

Before claiming "the wheel builds":

- [ ] `make build-wheel` succeeds in a clean checkout (after `make install`)
- [ ] `unzip -l dist/*.whl | grep -E '\.(js|css|html)$'` shows the built frontend
- [ ] The wheel installs cleanly (`uv pip install dist/*.whl` in a fresh venv)
- [ ] `python -c "import app; app.run()"` (or equivalent) serves assets with no extra steps
- [ ] `.gitignore` excludes the built asset directory
- [ ] Vite's `build.outDir` is an absolute path inside a Python package dir
- [ ] Hatchling config uses exactly one of `force-include` OR `ignore-vcs = true`

Before claiming "the PyApp binary works":

- [ ] `dist/<app> --help` runs on the build machine
- [ ] The binary is ≥ 50 MB (much smaller means it's not embedding Python)
- [ ] On Linux, `ldd dist/<app>` shows ≤ libc / libm / libpthread (no `libbz2`, no `liblzma`)
- [ ] A network-isolated `docker run --rm --network=none ghcr.io/.../distroless -- <app> --help` succeeds (proves no runtime PyPI fetches)
- [ ] The install dir (`~/.<app>/runtime/` or similar) is created on first run and re-used on second run

Before claiming "CI works":

- [ ] Python matrix covers minimum + stable + latest (e.g., 3.11, 3.12, 3.13)
- [ ] `make build-wheel` runs in CI and the resulting wheel is uploaded as an artifact
- [ ] Pre-commit / ruff / mypy / pyright / slotscheck run on every PR
- [ ] Release workflow is gated on CI (`needs: [lint, test]`)
- [ ] A tag push produces wheel + onefiles + GitHub release in one run

</validation>

## Example Projects

Everything in this skill is distilled from three production projects. Read these for the full picture:

- **[litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia)** — monolithic `app/` layout, Inertia.js + React 19, `force-include` bundling, `hatch build --target binary` for 4-platform PyApp.
- **[litestar-fullstack](https://github.com/litestar-org/litestar-fullstack)** — nested `src/py/app/` + `src/js/web/` layout, React + TanStack Router SPA, `ignore-vcs = true` bundling, React Email templates.

## Official References

- <https://ofek.dev/pyapp/> — PyApp documentation (all `PYAPP_*` env vars)
- <https://github.com/ofek/pyapp> — PyApp source (patch target: `src/app.rs`)
- <https://hatch.pypa.io/latest/config/build/> — Hatchling build config
- <https://hatch.pypa.io/latest/plugins/builder/binary/> — Hatch binary builder (simple PyApp)
- <https://docs.astral.sh/uv/concepts/projects/build/> — `uv build` reference
- <https://github.com/astral-sh/python-build-standalone/releases> — Portable Python archives
- <https://github.com/rust-cross/cargo-zigbuild> — cargo-zigbuild for portable glibc
- <https://bun.sh/docs/cli/install> — Bun install and lockfile

## Cross-References

- [litestar-deployment](../litestar-deployment/SKILL.md) — runtime deployment (Dockerfiles, K8s, Railway, Cloud Run, systemd) that consumes the artifacts this skill produces
- [litestar-vite](../litestar-vite/SKILL.md) — Vite plugin config (asset pipeline details, TypeGen, HMR)
- [litestar-granian](../litestar-granian/SKILL.md) — Granian ASGI server (what the wheel's entry-point starts)
- [litestar settings](../litestar-settings/references/settings.md) — env-driven `@dataclass` settings that work both in-wheel and as a PyApp binary

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [CI/CD](../litestar-styleguide/references/ci-cd.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
