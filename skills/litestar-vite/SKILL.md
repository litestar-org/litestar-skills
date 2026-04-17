---
name: litestar-vite
description: "Auto-activate for litestar_vite imports, VitePlugin, ViteConfig, PathConfig, RuntimeConfig, TypeGenConfig, vite.config.ts, astro.config.mjs with `litestar-vite-plugin/astro`, `litestar assets` CLI. First-party plugin coordinating a Vite frontend with a Litestar backend across **SPA / template / HTMX / Inertia / framework** modes. Produces ViteConfig + vite.config.ts wiring, manifest resolution, TypeGen (routes.ts, schemas.ts, openapi.json, inertia-pages.json), Jinja helpers (`vite()`, `vite_hmr()`, `vite_react_refresh()`), HMR, production build. Supported frameworks: **React** (+ TanStack Router), **Vue 3**, **Svelte**, **Angular** (`@analogjs/vite-plugin-angular`), **HTMX+Jinja** (with `ls-for`/`ls-if`/`$data` client templating), **Inertia.js** (React/Vue ±Jinja), **Nuxt, SvelteKit, Astro**. Use when: wiring any frontend with Litestar, choosing a mode, scaffolding from an example, setting up HMR, or generating types. Not for Webpack, Rollup, esbuild, Parcel, or plain Vite outside Litestar."
---

# litestar-vite

`litestar-vite` is the first-party plugin that connects a [Vite](https://vite.dev/) frontend build pipeline to a Litestar backend. It handles dev-server proxying, HMR coordination, manifest resolution for production assets, and (optionally) end-to-end type generation from Litestar OpenAPI to TypeScript.

It supports five modes — **SPA**, **template**, **HTMX**, **Inertia (hybrid)**, and **framework (SSR)** — letting one plugin cover everything from a static-asset add-on to a full Inertia.js app.

The plugin pairs with the npm package [`litestar-vite-plugin`](https://www.npmjs.com/package/litestar-vite-plugin) on the JS side. Both must agree on `input`, `bundleDir`, `hotFile`, and asset URL.

## Code Style Rules

- **Python**: PEP 604 unions (`T | None`); consumer Litestar app modules MAY use `from __future__ import annotations`.
- **TypeScript**: strict mode; `defineConfig` from `vite`; one `vite.config.ts` per frontend project.
- The Python `ViteConfig` and JS `vite.config.ts` are a single coupled contract. Change them together or HMR/manifest will silently break.

## Quick Reference

### Minimal SPA setup (Python side)

```python
from litestar import Litestar
from litestar_vite import ViteConfig, VitePlugin

vite_config = ViteConfig(
    bundle_dir="public",                # built assets land here
    resource_dir="resources",           # frontend source root
    use_server_lifespan=True,           # vite dev runs alongside `litestar run`
    dev_mode=True,                      # toggled by env in production
    hot_file="public/hot",              # MUST match vite.config.ts hotFile
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
  server: { cors: true },
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
| `spa` | Standalone single-page app (React, Vue, Svelte) with Litestar JSON API backend | `dev_mode=True` proxies to Vite; manifest in prod |
| `template` | Server-rendered pages (Jinja2/Mako) with Vite-bundled JS/CSS sprinkles | `vite_asset()` template helper resolves dev/prod URLs |
| `htmx` | HTMX hypermedia with Vite-bundled assets and HMR | `template` mode + `htmx` extras; partial HTML responses |
| `hybrid` (Inertia) | Inertia.js — server routes returning Inertia responses + JS page components | `litestar_vite.inertia.InertiaPlugin` alongside `VitePlugin` |
| `framework` | SSR frameworks (Nuxt, SvelteKit) | Plugin defers to the framework; coordinates port + manifest |

Decision tree:

- Need full SPA with client-side routing → **spa**
- Server-rendered HTML, sprinkle Vite-bundled JS → **template**
- HTMX-driven hypermedia with Vite assets → **htmx**
- Server-side routing + JS page components, shared data → **hybrid (Inertia)** (see `../litestar-inertia/SKILL.md`)
- Already using Nuxt / SvelteKit / a JS-side SSR framework → **framework**

### `VitePlugin` config (Python)

```python
from litestar_vite import (
    ViteConfig, VitePlugin, PathConfig, RuntimeConfig, TypeGenConfig,
)

vite_config = ViteConfig(
    mode="spa",
    paths=PathConfig(
        root=".",
        resource_dir="src",
        bundle_dir="public",
        public_dir="public",
        vite_config="vite.config.ts",
    ),
    runtime=RuntimeConfig(
        port=5173,
        host="localhost",
        protocol="http",
        hot_reload=True,
    ),
    types=TypeGenConfig(
        enabled=True,
        generate_sdk=True,
        generate_routes=True,
        generate_schemas=True,
        generate_page_props=True,
        output="src/generated",
    ),
    use_asset_linker=True,
    use_server_lifespan=True,
    dev_mode=False,           # True in dev, False in prod (env-toggled)
    hot_file="public/hot",
)
```

### Canonical fullstack-spa pattern

`litestar-fullstack-spa/src/js/web/vite.config.ts`:

```ts
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
  server: {
    cors: true,
    port: Number(process.env.VITE_PORT ?? 3006),
  },
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
      bundleDir: path.resolve(__dirname, "../../py/app/server/static/web"),
      hotFile: path.resolve(__dirname, "../../py/app/server/static/web/hot"),
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
})
```

`litestar-fullstack-spa/src/py/app/server/plugins.py`:

```python
from litestar_vite import VitePlugin
from app import config

vite = VitePlugin(config=config.vite)
```

The `config.vite` `ViteConfig` references the **same** `bundle_dir`, `hot_file`, and `resource_dir` paths as the JS-side `vite.config.ts`. They are one coupled contract.

### Type Generation

```python
TypeGenConfig(
    enabled=True,
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
| `routes.ts` | `output/routes.ts` | Route table changes | `route("name", { params })` typed URL builder |
| `schemas.ts` | `output/schemas.ts` | Pydantic / msgspec DTO changes | `components["schemas"]["User"]` typed models |
| `inertia-pages.json` | `output/inertia-pages.json` | Inertia handlers added/changed | Page-prop typing for Inertia adapters |

CLI:

```bash
litestar assets generate-types          # one-off generation
litestar assets export-routes           # routes.ts only
litestar --app app:app run              # generates on startup if enabled
```

Frontend consumption:

```ts
// routes
import { route } from "@/generated/routes"
const url = route("users:get", { id: 123 })

// schemas
import type { components } from "@/generated/schemas"
type User = components["schemas"]["User"]
```

### `ViteAssetLoader` and Template Helpers

Auto-registered Jinja2 globals when a template engine is configured:

| Helper | Use |
| --- | --- |
| `{{ vite_asset('src/main.ts') }}` | Resolve script URL (dev: proxied; prod: hashed manifest) |
| `{{ vite_css('src/app.css') }}` | Render `<link rel="stylesheet">` tag |
| `{{ vite_hmr_client() }}` | Inject HMR client `<script>` in dev mode (no-op in prod) |
| `{{ vite_react_refresh() }}` | Inject React Fast Refresh preamble before React app code |

Minimal base template:

```html
<!DOCTYPE html>
<html>
<head>
  {{ vite_hmr_client() }}
  {{ vite_react_refresh() }}
  {{ vite_css('src/app.css') }}
</head>
<body>
  <div id="app"></div>
  {{ vite_asset('src/main.tsx') | safe }}
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
litestar assets serve            # Start Vite dev server (also auto-started with `litestar run` when use_server_lifespan=True)
litestar assets build            # Production build (emits manifest.json + hashed bundles)
litestar assets generate-types   # TypeScript type generation
litestar assets export-routes    # routes.ts only
litestar assets status           # Verify integration health
```

### HMR

In dev mode:

1. Vite dev server runs on `runtime.port` (e.g., `5173`).
2. Plugin writes a "hot file" (path = `hot_file`) signaling dev-mode is active.
3. `vite_asset()` returns proxied URLs (`http://localhost:5173/...`) instead of manifest paths.
4. `vite_hmr_client()` injects the HMR client script.
5. On rebuild, Vite pushes updates over WS; the page hot-swaps without a reload.

Common HMR gotchas:

- **Hot file mismatch**: `ViteConfig.hot_file` and `vite.config.ts` `hotFile` must point to the same path. Mismatch ⇒ stale prod URLs in dev.
- **CORS errors**: set `server.cors: true` in `vite.config.ts` so the Litestar origin can fetch dev assets.
- **Port conflict**: pin `runtime.port` and `server.port`; do not let Vite auto-pick.
- **Browsers cache `manifest.json`**: cache-bust by hash; never serve manifest.json from a CDN with long TTL.

### Production Build & Deploy

```bash
# Build for production
litestar assets build

# Outputs:
#   <bundle_dir>/manifest.json     ← URL → hashed-asset map
#   <bundle_dir>/assets/*.js       ← hashed JS bundles
#   <bundle_dir>/assets/*.css      ← hashed CSS bundles
#   <bundle_dir>/<public files>    ← copied from publicDir
```

In production:

- Set `dev_mode=False` (env-toggled).
- Litestar serves `bundle_dir` as static files OR a CDN serves them and `base` (Vite) / `assetUrl` (plugin) points at the CDN.
- `vite_asset()` reads `manifest.json` once and returns hashed URLs.
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
from litestar_vite import VitePlugin
from litestar_vite.inertia import InertiaPlugin, InertiaConfig

app = Litestar(plugins=[
    VitePlugin(config=vite_config),
    InertiaPlugin(config=InertiaConfig(root_template="base.html")),
])
```

See `../litestar-inertia/SKILL.md` for client adapter setup.

### HTMX integration

For HTMX mode, use `template` mode in `ViteConfig` plus the HTMX htmx-vite plugin client. Vite handles JS/CSS bundling; Litestar returns partial HTML enriched with `hx-*` attributes. See `../litestar-htmx/SKILL.md`.

<workflow>

## Workflow

### Step 1: Pick the Mode

Run the decision tree above. Most apps want `spa` or `hybrid`. Lock the choice before configuring — switching mode mid-project is painful.

### Step 2: Install

```bash
pip install litestar-vite
npm install -D vite litestar-vite-plugin
# Plus a framework adapter, e.g.:
npm install -D @vitejs/plugin-react   # or @vitejs/plugin-vue, etc.
```

Optional bootstrap: `litestar assets init` scaffolds `vite.config.ts` + `package.json`.

### Step 3: Wire ViteConfig (Python)

Define `ViteConfig` with `bundle_dir`, `resource_dir`, `hot_file`, `runtime` settings. Toggle `dev_mode` from an env var. Add to `Litestar(plugins=[VitePlugin(config=...)])`.

### Step 4: Wire vite.config.ts (JS)

Add `litestar()` plugin with matching `input`, `bundleDir`, `hotFile`. Set `server.cors: true`, pin `server.port`, set `base` for prod CDN if needed.

### Step 5: Enable Type Generation (optional)

For SPA / Inertia projects, set `TypeGenConfig(enabled=True, ...)`. Re-run `litestar assets generate-types` whenever DTOs change. CI should fail if generated files are out of date.

### Step 6: Wire Templates (template / HTMX modes)

Use `vite_hmr_client()`, `vite_react_refresh()` (React only), `vite_css()`, `vite_asset()` in your base template.

### Step 7: Verify HMR

`litestar run` → check the dev banner shows `Vite serving at http://localhost:5173`. Edit a frontend file → browser updates without reload. If it doesn't, check the troubleshooting list below.

### Step 8: Build & Deploy

`litestar assets build` in CI → ship `bundle_dir/` as static assets or push to CDN. Set `dev_mode=False` in production env.

</workflow>

<guardrails>

## Guardrails

- **`ViteConfig` paths and `vite.config.ts` paths are a single contract** — `bundle_dir`, `hot_file`, `resource_dir`, asset URL, `input` must agree. Mismatch breaks HMR or manifest resolution silently.
- **Pin `server.port` in `vite.config.ts`** — auto-picked ports break the plugin's URL resolution.
- **Set `server.cors: true`** when Litestar serves on a different origin than Vite in dev.
- **Toggle `dev_mode` from env**, never hardcode `True` in committed code — leaving dev mode on in prod proxies to a non-existent dev server.
- **Use `use_server_lifespan=True`** for dev so `litestar run` starts/stops Vite. For prod, set `dev_mode=False`; the lifespan is irrelevant.
- **Commit generated types** OR regenerate in CI and check no diff — a drift between OpenAPI and `schemas.ts` is a runtime error.
- **Never serve `manifest.json` with long-TTL caching** — frontend deploys depend on it being current.
- **One `vite.config.ts` per frontend project** — multiple configs in one repo confuse the plugin's path resolution.
- **Use `base` (Vite) / `assetUrl` (plugin)** for CDN deployments. Prefer env-driven values (`process.env.ASSET_URL`).
- **Not for Webpack/Rollup/esbuild/Parcel** — `litestar-vite` integrates specifically with Vite's dev server protocol.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering a `litestar-vite` integration, verify:

- [ ] Mode (`spa` / `template` / `htmx` / `hybrid` / `framework`) is explicit
- [ ] `bundle_dir` and `hotFile` paths in `ViteConfig` match `vite.config.ts`
- [ ] `dev_mode` is env-toggled
- [ ] `server.port` is pinned in `vite.config.ts`
- [ ] `server.cors: true` if Litestar and Vite are on different origins in dev
- [ ] Template base file uses `vite_hmr_client()` (and `vite_react_refresh()` for React) before any user JS
- [ ] If `TypeGenConfig.enabled=True`, generated types are committed or CI verifies they are up-to-date
- [ ] Production build sets `dev_mode=False` and ships `manifest.json` + hashed bundles
- [ ] CDN deploys set `base` / `assetUrl` from `ASSET_URL` env var
- [ ] No competing Webpack/Rollup config in the same project

</validation>

<example>

## Example

**Task:** A Litestar SPA app with React + TanStack Router + Tailwind, building into the Litestar static dir, with HMR in dev.

```python
# app/config/vite.py
from litestar_vite import ViteConfig, PathConfig, RuntimeConfig
import os

vite = ViteConfig(
    paths=PathConfig(
        root=".",
        resource_dir="src/js/web",
        bundle_dir="src/py/app/server/static/web",
        vite_config="src/js/web/vite.config.ts",
    ),
    runtime=RuntimeConfig(port=3006, hot_reload=True),
    use_server_lifespan=True,
    dev_mode=os.getenv("ENV", "dev") == "dev",
    hot_file="src/py/app/server/static/web/hot",
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
  server: { cors: true, port: Number(process.env.VITE_PORT ?? 3006) },
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
      bundleDir: path.resolve(__dirname, "../../py/app/server/static/web"),
      hotFile: path.resolve(__dirname, "../../py/app/server/static/web/hot"),
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

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app + plugin lifecycle.
- **[inertia](../litestar-inertia/SKILL.md)** — Inertia-specific frontend setup (paired with `hybrid` mode).
- **[litestar-htmx](../litestar-htmx/SKILL.md)** — HTMX integration with Vite-bundled assets.

## Official References

- <https://vite.dev/guide/>
- <https://vite.dev/config/>
- <https://github.com/litestar-org/litestar-vite>
- <https://litestar-org.github.io/litestar-vite/>
- <https://litestar-org.github.io/litestar-vite/inertia/>
- <https://www.npmjs.com/package/litestar-vite-plugin>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [TypeScript](../litestar-styleguide/references/typescript.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
