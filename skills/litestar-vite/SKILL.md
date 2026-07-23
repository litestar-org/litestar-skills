---
name: litestar-vite
description: "Auto-activate for litestar_vite, VitePlugin, ViteConfig, PathConfig, RuntimeConfig, TypeGenConfig, InertiaConfig, vite.config.ts, HMR, typegen, assets, or modes. Not for plain Vite."
---

# litestar-vite

`litestar-vite` is the first-party plugin that connects a [Vite](https://vite.dev/) frontend build pipeline to a Litestar backend. It handles dev-server proxying, HMR coordination, manifest resolution for production assets, and (optionally) end-to-end type generation from Litestar OpenAPI to TypeScript.

The runtime has four canonical modes: `spa`, `template`, `hybrid`, and `framework`.
`htmx`, `inertia`, `ssr`, and `ssg` are aliases that normalize to those modes.
`external` is deprecated; use `framework` with `ExternalDevServer`.

The plugin pairs with the npm package [`litestar-vite-plugin`](https://www.npmjs.com/package/litestar-vite-plugin) on the JS side. Python `ViteConfig` is the source of truth; the generated `.litestar.json` bridge lets JS config normally keep only `litestar({ input: [...] })`.

This guidance targets the immutable `v0.27.0` tag. Releases `0.26.0` through
`0.27.0` hardened Inertia protocol behavior, scaffolds, type generation,
single-port HMR routing, manifest fallback, deployment, plugin activation, and
lifecycle logging. See [Release Updates](references/release-updates.md).

## Code Style Rules

- **Python**: PEP 604 unions (`T | None`); consumer Litestar app modules MAY use `from __future__ import annotations`.
- **TypeScript**: strict mode; `defineConfig` from `vite`; one `vite.config.ts` per frontend project.
- Keep `ViteConfig` as the source of truth. Only duplicate `bundleDir`, `hotFile`, or `assetUrl` in `vite.config.ts` for deliberate standalone/override workflows.

## Quick Reference

### Minimal SPA setup (Python side)

```python
from litestar import Litestar
from litestar_vite import PathConfig, ViteConfig, VitePlugin

vite_config = ViteConfig(
    mode="spa",
    enabled=True,
    paths=PathConfig(
        resource_dir="resources",       # frontend source root
        bundle_dir="public",            # built assets land here
        hot_file="hot",                 # written to the .litestar.json bridge
    ),
    dev_mode=True,                      # toggled by env in production
)

app = Litestar(plugins=[VitePlugin(config=vite_config)])
```

### Minimal SPA setup (JS side)

```ts
// vite.config.ts
import { defineConfig } from "vite"
import litestar from "litestar-vite-plugin"
import react from "@vitejs/plugin-react"

export default defineConfig({
  clearScreen: false,
  publicDir: "public",
  plugins: [
    react(),
    litestar({
      input: ["resources/main.tsx", "resources/main.css"],
    }),
  ],
  resolve: { alias: { "@": "/resources" } },
})
```

### Mode Selection

| Mode | Use For | Key Setup |
| --- | --- | --- |
| `spa` | React, Vue, Svelte, or Analog-powered Angular SPA with a Litestar JSON API backend | `dev_mode=True` proxies to Vite; manifest in prod |
| `template` (`htmx` alias) | Server-rendered Jinja2/Mako pages and HTMX with Vite-bundled assets | Use `TemplateConfig`; add `litestar-htmx` when using HTMX |
| `hybrid` (`inertia` alias) | Inertia.js routes returning JS page components | Configure `ViteConfig(inertia=InertiaConfig(...))` |
| `framework` (`ssr` / `ssg` aliases) | Nuxt, SvelteKit, Astro, Angular CLI, or another frontend-owned HTML server | Use the framework entry point or `ExternalDevServer` |

Decision tree:

- Need full SPA with client-side routing → **spa**
- Server-rendered HTML, sprinkle Vite-bundled JS → **template**
- HTMX-driven hypermedia with Vite assets → **template** (`htmx` alias) + `HTMXPlugin`
- Server-side routing + JS page components, shared data → **hybrid** (`inertia` alias; see `../litestar-inertia/SKILL.md`)
- Nuxt, SvelteKit, or Astro owns HTML → **framework**
- Angular CLI or another non-Vite server → **framework** + `ExternalDevServer`

### `VitePlugin` config (Python)

```python
from litestar_vite import (
    ViteConfig, VitePlugin, PathConfig, RuntimeConfig, TypeGenConfig,
)

vite_config = ViteConfig(
    mode="spa",
    enabled=True,             # False makes runtime wiring inert; CLI remains available
    dev_mode=False,           # True in dev, False in prod (env-toggled)
    paths=PathConfig(
        root=".",
        resource_dir="src",
        bundle_dir="public",
        static_dir="src/public",
        hot_file="hot",
        asset_url="/static/",
    ),
    runtime=RuntimeConfig(
        port=5173,
        host="localhost",
        protocol="http",
        executor="bun",
    ),
    types=TypeGenConfig(
        generate_zod=False,
        generate_sdk=True,
        generate_routes=True,
        generate_schemas=True,
        generate_page_props=False,
        output="src/generated",
    ),
)
```

`enabled=None` auto-detects serving contexts and consults `VITE_ENABLED`.
`enabled=False` leaves `VitePlugin.config` and asset CLI commands available but
skips runtime routes, middleware, static routers, lifespans, and the SPA
handler.

### Type Generation

```python
TypeGenConfig(
    generate_sdk=True,
    generate_routes=True,
    generate_schemas=True,
    generate_page_props=True,    # Inertia only
    output="src/generated",
)
```

| Output | Path | Trigger | Frontend Use |
| --- | --- | --- | --- |
| `openapi.json` | `output/openapi.json` | Whenever OpenAPI schema changes | Source of truth for SDK + schemas |
| `routes.json` | `output/routes.json` | Route table changes | Route metadata consumed by the JS plugin |
| `routes.ts` | `output/routes.ts` | Route table changes | `route("name", { params })` typed URL builder |
| `api/` | `output/api/` | OpenAPI changes | hey-api types, schemas, SDK, and fetch client |
| `schemas.ts` | `output/schemas.ts` | Route request/response changes | `FormInput`, `FormResponse`, and `SuccessResponse` helpers |
| `inertia-pages.json` | `output/inertia-pages.json` | Inertia handlers added/changed | Page-prop metadata consumed by the JS plugin |
| `page-props.ts` | `output/page-props.ts` | Inertia handlers added/changed | Typed props for Inertia page components |
| `static-props.ts` | `output/static-props.ts` | `ViteConfig.static_props` changes | Typed static bridge values |

CLI:

```bash
litestar assets generate-types          # one-off generation
litestar assets export-routes           # routes.json metadata
litestar assets export-routes --typescript  # routes.ts only
litestar --app app:app run              # generates on startup if enabled
```

Frontend consumption:

```ts
// routes
import { route } from "@/generated/routes"
const url = route("users:get", { id: 123 })

// hey-api output
import type { User } from "@/generated/api"

// ergonomic route helpers
import type { FormInput } from "@/generated/schemas"
type LoginInput = FormInput<"auth:login">
```

### `ViteAssetLoader` and Template Helpers

Auto-registered Jinja2 globals when a template engine is configured:

| Helper | Use |
| --- | --- |
| `{{ vite('resources/main.ts') }}` | Render script/link tags for a Vite input; handles dev vs manifest |
| `{{ vite_hmr() }}` | Inject HMR client `<script>` in dev mode; no-op in prod |
| `{{ vite_static('favicon.svg') }}` | Resolve a static asset URL |
| `{{ vite_routes() }}` | Render inline route metadata for client-side routing |

Minimal base template:

```html
<!DOCTYPE html>
<html>
<head>
  {{ vite_hmr() }}
  {{ vite('resources/main.tsx') }}
</head>
<body>
  <div id="app"></div>
</body>
</html>
```

For programmatic use inside a handler:

```python
from litestar import get
from litestar.response import Template
from litestar_vite import ViteAssetLoader

loader = ViteAssetLoader(config=vite_config)

@get("/")
async def index() -> Template:
    return Template("index.html", context={"vite": loader})
```

### CLI

```bash
litestar assets init             # Scaffold vite.config.ts and package.json
litestar assets install          # Run npm/pnpm/bun install
litestar assets update           # Update within package.json semver ranges
litestar assets update --latest  # Ignore semver ranges
litestar assets serve            # Start Vite dev server (also auto-started when `dev_mode=True`)
litestar assets build            # Production build (emits manifest.json + hashed bundles)
litestar assets deploy --dry-run # Build and preview an fsspec-backed deployment
litestar assets deploy           # Build and sync to DeployConfig.storage_backend
litestar assets generate-types   # TypeScript type generation
litestar assets export-routes    # routes.json metadata
litestar assets doctor           # Diagnose integration health
litestar assets status           # Read-only status summary
```

`assets init --template` accepts `react`, `react-router`,
`react-tanstack`, `react-inertia`, `react-inertia-jinja`, `vue`,
`vue-inertia`, `vue-inertia-ssr`, `vue-inertia-jinja`,
`vue-inertia-jinja-ssr`, `svelte`, `svelte-inertia`,
`svelte-inertia-jinja`, `sveltekit`, `nuxt`, `astro`, `htmx`,
`jinja-htmx`, `htmx-no-jinja`, `angular`, and `angular-cli`.

### HMR

In dev mode:

1. Vite dev server runs on `runtime.port` (e.g., `5173`).
2. Plugin writes a "hot file" (path = `hot_file`) signaling dev-mode is active.
3. The browser uses the Litestar origin for dev assets and HMR.
4. `vite_hmr()` injects the HMR client script.
5. Litestar proxies asset HTTP and the HMR WebSocket to the hot-file target.
6. On rebuild, Vite pushes updates over the proxied WebSocket.

Common HMR gotchas:

- **Hot file mismatch**: remove JS `hotFile` overrides or align them with `ViteConfig.paths.hot_file`. Mismatch ⇒ stale prod URLs in dev.
- **CORS errors**: remove direct-origin overrides. The supported dev contract keeps Litestar as the public origin.
- **Port conflict**: let Vite choose its internal port and let the hot file update the proxy target.
- **Vite 8.1 HMR deprecation**: put HMR network fields under `server.ws`, not `server.hmr`. Keep `server.hmr=false` only when disabling HMR. Use `server.hmr` network fields only when the project is pinned to Vite 7 or 8.0.
- **Browsers cache `manifest.json`**: cache-bust by hash; never serve manifest.json from a CDN with long TTL.

Vite 8.1+ explicit HMR network override:

```ts
export default defineConfig({
  server: {
    ws: {
      host: "localhost",
      path: "vite-hmr",
      clientPort: 8000,
    },
  },
})
```

Prefer no explicit HMR network override. `litestar-vite-plugin` routes the
browser to the Litestar port and emits the version-correct configuration from
`.litestar.json`.

### Production Build & Deploy

```bash
# Build for production
litestar assets build

# Outputs:
#   <bundle_dir>/manifest.json or .vite/manifest.json
#   <bundle_dir>/assets/*.js       ← hashed JS bundles
#   <bundle_dir>/assets/*.css      ← hashed CSS bundles
#   <bundle_dir>/<public files>    ← copied from publicDir
```

In production:

- Set `dev_mode=False` (env-toggled).
- Litestar serves `bundle_dir` as static files OR a CDN serves them and `base` (Vite) / `assetUrl` (plugin) points at the CDN.
- Asset loading first checks `<bundle_dir>/<manifest_name>`, then
  `<bundle_dir>/.vite/<manifest_name>`.
- HMR helpers become no-ops.

CDN pattern:

```ts
// vite.config.ts
export default defineConfig({
  base: process.env.ASSET_URL ?? "/static/",   // CDN URL in prod, /static/ in dev
  ...
})
```

### Inertia integration

```python
from litestar_vite import PathConfig, TypeGenConfig, ViteConfig, VitePlugin
from litestar_vite.inertia import InertiaConfig

vite = VitePlugin(
    config=ViteConfig(
        mode="hybrid",
        paths=PathConfig(resource_dir="resources"),
        inertia=InertiaConfig(root_template="base.html"),
        types=TypeGenConfig(output="resources/generated"),
    )
)

app = Litestar(plugins=[vite], middleware=[session_backend.middleware])
```

Current Inertia behavior:

- Initial non-Inertia visits return an HTML bootstrap. Inertia visits (`X-Inertia: true`) return JSON.
- Handler returns shaped like prop bags (`dict`, `msgspec.Struct`, dataclass instance, or Pydantic model) become top-level page props. They are not nested under `content`.
- Initial responses advertise deferred props. Partial responses omit
  `deferredProps`, including unrequested groups.
- `X-Inertia-Partial-Data` includes requested keys; `X-Inertia-Partial-Except`
  excludes keys and wins on overlap.
- Asset-version mismatch returns `409` plus `X-Inertia-Location` for stale
  `GET` visits only. Non-`GET` submissions continue to the handler.
- Use `litestar-vite-plugin` as the bridge owner. Do not add `@inertiajs/vite` to generated Litestar scaffolds by default.

See `../litestar-inertia/SKILL.md` for client adapter setup.

### HTMX integration

For HTMX + Jinja, use `ViteConfig(mode="template", ...)`, Litestar
`TemplateConfig`, and `HTMXPlugin()`. The `htmx` alias normalizes to
`template`; it does not create a separate runtime mode.

<workflow>

## Workflow

### Step 1: Pick the Mode

Run the decision tree above. Most apps want `spa`, `template`, `hybrid`, or
`framework`. Lock the canonical choice before configuring; aliases do not create
separate runtime modes.

### Step 2: Install

```bash
pip install litestar-vite
npm install -D vite litestar-vite-plugin
# Plus a framework adapter, e.g.:
npm install -D @vitejs/plugin-react   # or @vitejs/plugin-vue, etc.
```

Optional bootstrap: `litestar assets init --template <name>` generates a
transactional scaffold. Use `--no-prompt` in automation and `--overwrite` only
after reviewing collisions.

### Step 3: Wire ViteConfig (Python)

Define `ViteConfig` with `paths=PathConfig(...)`, optional `runtime=RuntimeConfig(...)`, and optional `types=True` / `types=TypeGenConfig(...)`. Toggle `dev_mode` from an env var. Add to `Litestar(plugins=[VitePlugin(config=...)])`.

### Step 4: Wire vite.config.ts (JS)

Add `litestar()` with `input`. Let the `.litestar.json` bridge provide `bundleDir`, `hotFile`, typegen paths, and asset URL unless you are deliberately overriding Python config. Set `base` for prod CDN if needed.

### Step 5: Enable Type Generation (optional)

For SPA / Inertia projects, set `types=TypeGenConfig(...)`. Re-run `litestar assets generate-types` whenever DTOs change. CI should fail if generated files are out of date.

### Step 6: Wire Templates (template / HTMX modes)

Use `vite_hmr()` and `vite()` in your base template.
For HTMX, register `HTMXPlugin()` and use `ViteConfig(mode="template", ...)`.

### Step 7: Verify HMR

Run `litestar run`, load the Litestar URL, and verify asset HTTP plus the HMR
WebSocket stay on that public origin. The internal Vite port is discovered
through the hot file.

### Step 8: Build & Deploy

Run `litestar assets update` deliberately when refreshing frontend dependencies.
Run `litestar assets build` in CI, or configure `DeployConfig` and use
`litestar assets deploy`. Set `dev_mode=False` in production.

</workflow>

<guardrails>

## Guardrails

- **`ViteConfig` is the source of truth** — avoid JS-side `bundleDir`, `hotFile`, and `assetUrl` overrides unless this is a standalone/mono-repo override. Mismatch breaks HMR or manifest resolution silently.
- **Use the single-port ASGI contract** — the browser connects to Litestar for
  asset HTTP and HMR. `RuntimeConfig.proxy_mode` accepts `"vite"`, `"proxy"`,
  or `None`; legacy `VITE_PROXY_MODE=direct` warns and becomes `"vite"`.
- **Use `server.ws` for Vite 8.1+ HMR network overrides** — `server.hmr.host`, `server.hmr.port`, `server.hmr.clientPort`, `server.hmr.path`, `server.hmr.protocol`, and `server.hmr.timeout` are the Vite 7 / 8.0 shape.
- **Do not configure a second public dev origin** — the supported proxy contract
  removes the need for frontend CORS.
- **Toggle `dev_mode` from env**, never hardcode `True` in committed code — leaving dev mode on in prod proxies to a non-existent dev server.
- **Keep `RuntimeConfig.start_dev_server=True` in dev** so `litestar run` starts/stops Vite. For prod, set `dev_mode=False`.
- **Commit generated types** OR regenerate in CI and check no diff — a drift between OpenAPI and `schemas.ts` is a runtime error.
- **Never serve `manifest.json` with long-TTL caching** — frontend deploys depend on it being current.
- **One `vite.config.ts` per frontend project** — multiple configs in one repo confuse the plugin's path resolution.
- **Use `base` (Vite) / `assetUrl` (plugin)** for CDN deployments. Prefer env-driven values (`process.env.ASSET_URL`).
- **Not for Webpack/Rollup/esbuild/Parcel** — `litestar-vite` integrates specifically with Vite's dev server protocol.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering a `litestar-vite` integration, verify:

- [ ] Canonical mode (`spa` / `template` / `hybrid` / `framework`) is explicit
- [ ] HTMX apps use `mode="template"` with `HTMXPlugin()`
- [ ] Inertia apps put `InertiaConfig` on `ViteConfig` and register one `VitePlugin`
- [ ] JS-side `bundleDir` / `hotFile` / `assetUrl` overrides are absent or intentionally match `ViteConfig`
- [ ] `dev_mode` is env-toggled
- [ ] Browser asset and HMR connections use the Litestar origin
- [ ] Vite 8.1+ HMR network overrides use `server.ws`; Vite 7 / 8.0 overrides use `server.hmr`
- [ ] Template base file uses `vite_hmr()` before `vite(...)`
- [ ] If `types=TypeGenConfig(...)`, generated types are committed or CI verifies they are up-to-date
- [ ] Production build sets `dev_mode=False` and ships an existing candidate
      manifest plus hashed bundles
- [ ] `enabled=False` contexts register no Vite routes, middleware, or lifespans
- [ ] Dependency refreshes use `litestar assets update`; remote sync uses
      `litestar assets deploy --dry-run` before deployment
- [ ] CDN deploys set `base` / `assetUrl` from `ASSET_URL` env var
- [ ] No competing Webpack/Rollup config in the same project

</validation>

<example>

## Example

**Task:** A Litestar SPA app with React + TanStack Router + Tailwind, building into the Litestar static dir, with HMR in dev.

```python
# app/config/vite.py
import os
from pathlib import Path

from litestar_vite import PathConfig, RuntimeConfig, ViteConfig

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = PROJECT_ROOT / "src/js/web"
STATIC_DIR = PROJECT_ROOT / "src/py/app/server/static/web"

vite = ViteConfig(
    paths=PathConfig(
        root=FRONTEND_ROOT,
        bundle_dir=STATIC_DIR,
        hot_file="hot",
        asset_url="/static/web/",
    ),
    runtime=RuntimeConfig(port=3006, executor="bun", is_react=True),
    dev_mode=os.getenv("ENV", "dev") == "dev",
)
```

```python
# app/server/plugins.py
from litestar_vite import VitePlugin
from app import config

vite = VitePlugin(config=config.vite)
```

```ts
// src/js/web/vite.config.ts
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import litestar from "litestar-vite-plugin"
import { defineConfig } from "vite"

export default defineConfig({
  clearScreen: false,
  base: process.env.ASSET_URL ?? "/static/web/",
  publicDir: "public",
  server: { port: Number(process.env.VITE_PORT ?? 3006) }, // optional internal port pin
  build: {
    outDir: path.resolve(__dirname, "../../py/app/server/static/web"),
    emptyOutDir: true,
  },
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    tailwindcss(),
    react(),
    litestar({
      input: ["src/main.tsx", "src/styles.css"],
      bundleDir: path.resolve(__dirname, "../../py/app/server/static/web"), // explicit override
      hotFile: path.resolve(__dirname, "../../py/app/server/static/web/hot"), // explicit override
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
})
```

```bash
# Dev — Litestar boots Vite alongside the ASGI server
litestar --app app:app run

# Prod build
ENV=prod litestar assets build
```

</example>

---

## References Index

For deep-dives on specific surfaces, see:

- **[Config](references/config.md)** — Full `ViteConfig`, `PathConfig`, `RuntimeConfig`, `TypeGenConfig`, and `vite.config.ts` reference.
- **[Modes](references/modes.md)** — SPA / template / HTMX / Inertia / framework deep-dive with decision matrices.
- **[TypeGen](references/typegen.md)** — Type generation pipeline, output reference, CI integration.
- **[HMR](references/hmr.md)** — HMR architecture, debugging, common pitfalls.
- **[Deployment](references/deployment.md)** — Production build, static hosting, CDN patterns, cache strategy.
- **[Troubleshooting](references/troubleshooting.md)** — Common errors and fixes.
- **[Release Updates](references/release-updates.md)** — audited `0.26.0`
  through `0.27.0` behavior changes.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app + plugin lifecycle.
- **[inertia](../litestar-inertia/SKILL.md)** — Inertia-specific frontend setup (paired with `hybrid` mode).
- **[litestar-htmx](../litestar-htmx/SKILL.md)** — HTMX integration with Vite-bundled assets.

## Official References

- <https://vite.dev/guide/>
- <https://vite.dev/config/>
- <https://github.com/litestar-org/litestar-vite/tree/v0.27.0>
- <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/docs>
- <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/tests>
- <https://www.npmjs.com/package/litestar-vite-plugin>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [TypeScript](../litestar-styleguide/references/typescript.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
