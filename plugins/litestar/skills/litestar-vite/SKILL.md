---
name: litestar-vite
description: "Auto-activate for litestar_vite, VitePlugin, ViteConfig, PathConfig, RuntimeConfig, TypeGenConfig, InertiaConfig, vite.config.ts, HMR, typegen, assets, or modes. Not for plain Vite."
---

# litestar-vite

`litestar-vite` is the first-party plugin that connects a [Vite](https://vite.dev/) frontend build pipeline to a Litestar backend. It handles dev-server proxying, HMR coordination, manifest resolution for production assets, and (optionally) end-to-end type generation from Litestar OpenAPI to TypeScript.

The reference apps use `spa`, `template`, `htmx`, `hybrid` / `inertia`, `framework` / `ssr` / `ssg`, and `external` modes. Inertia is one `VitePlugin` configured with `ViteConfig(inertia=InertiaConfig(...))`; the plugin wires the internal Inertia integration from that config.

The plugin pairs with the npm package [`litestar-vite-plugin`](https://www.npmjs.com/package/litestar-vite-plugin) on the JS side. Python `ViteConfig` is the source of truth; the generated `.litestar.json` bridge lets JS config normally keep only `litestar({ input: [...] })`.

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
| `template` | Server-rendered Jinja2/Mako pages with Vite-bundled JS/CSS sprinkles | `TemplateConfig` + template helpers resolve dev/prod URLs |
| `htmx` | HTMX hypermedia with Jinja templates and Vite-bundled assets | Add `litestar-htmx`; use `hx-*` and `ls-*` attributes |
| `hybrid` / `inertia` | Inertia.js routes returning JS page components | `ViteConfig(inertia=InertiaConfig(...))` on a single `VitePlugin` |
| `framework` / `ssr` | Nuxt or SvelteKit SSR | JS framework owns rendering; Litestar provides/proxies API |
| `framework` / `ssg` | Astro static generation | `astro.config.mjs` imports `litestar-vite-plugin/astro` |
| `external` | Angular CLI or another external dev/build process | Litestar coordinates URLs/types while the external tool owns build |

Decision tree:

- Need full SPA with client-side routing → **spa**
- Server-rendered HTML, sprinkle Vite-bundled JS → **template**
- HTMX-driven hypermedia with Vite assets → **htmx + HTMXPlugin**
- Server-side routing + JS page components, shared data → **hybrid / inertia** (see `../litestar-inertia/SKILL.md`)
- Already using Nuxt or SvelteKit → **framework** (`ssr` alias is accepted)
- Building an Astro site → **framework** (`ssg` alias is accepted)
- Using Angular CLI rather than the Analog Vite example → **external**

### `VitePlugin` config (Python)

```python
from litestar_vite import (
    ViteConfig, VitePlugin, PathConfig, RuntimeConfig, TypeGenConfig,
)

vite_config = ViteConfig(
    mode="spa",
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
        generate_sdk=True,
        generate_routes=True,
        generate_schemas=True,
        generate_page_props=True,
        output="src/generated",
    ),
)
```

### Explicit fullstack-spa override pattern

From [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) — `src/js/web/vite.config.ts`:

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
    port: Number(process.env.VITE_PORT ?? 3006), // direct/two-port workflows only
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

`litestar-fullstack/src/py/app/server/plugins.py`:

```python
from litestar_vite import VitePlugin
from app import config

vite = VitePlugin(config=config.vite)
```

The `config.vite` `ViteConfig` owns `bundle_dir`, `hot_file`, and `resource_dir`. Duplicate them in JS only when intentionally overriding the `.litestar.json` bridge, as this explicit mono-repo example does.

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
| `schemas.ts` | `output/schemas.ts` | Pydantic / msgspec DTO changes | `components["schemas"]["User"]` typed models |
| `inertia-pages.json` | `output/inertia-pages.json` | Inertia handlers added/changed | Page-prop metadata consumed by the JS plugin |
| `page-props.ts` | `output/page-props.ts` | Inertia handlers added/changed | Typed props for Inertia page components |

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

// schemas
import type { components } from "@/generated/schemas"
type User = components["schemas"]["User"]
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
litestar assets serve            # Start Vite dev server (also auto-started when `dev_mode=True`)
litestar assets build            # Production build (emits manifest.json + hashed bundles)
litestar assets generate-types   # TypeScript type generation
litestar assets export-routes    # routes.json metadata
litestar assets doctor           # Diagnose integration health
litestar assets status           # Read-only status summary
```

### HMR

In dev mode:

1. Vite dev server runs on `runtime.port` (e.g., `5173`).
2. Plugin writes a "hot file" (path = `hot_file`) signaling dev-mode is active.
3. `vite()` returns Litestar-proxied dev URLs by default instead of manifest paths.
4. `vite_hmr()` injects the HMR client script.
5. On rebuild, Vite pushes updates over WS; the page hot-swaps without a reload.

Common HMR gotchas:

- **Hot file mismatch**: remove JS `hotFile` overrides or align them with `ViteConfig.paths.hot_file`. Mismatch ⇒ stale prod URLs in dev.
- **CORS errors**: use default proxy mode first. In direct/two-port mode, set `server.cors: true` so the Litestar origin can fetch dev assets.
- **Port conflict**: proxy mode can auto-pick a Vite port. In direct/two-port mode, pin `runtime.port` and `server.port`.
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
- `vite()` reads `manifest.json` and returns hashed asset tags.
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

See `../litestar-inertia/SKILL.md` for client adapter setup.

### HTMX integration

For HTMX + Jinja, use `ViteConfig(mode="htmx", ...)`, Litestar `TemplateConfig`, and `HTMXPlugin()`. Vite handles JS/CSS bundling; Litestar returns partial HTML enriched with `hx-*` attributes. See `../litestar-htmx/SKILL.md`.

<workflow>

## Workflow

### Step 1: Pick the Mode

Run the decision tree above. Most apps want `spa`, `template`, `htmx`, or `hybrid`. Lock the choice before configuring — switching mode mid-project rewires paths, assets, and TypeGen output.

### Step 2: Install

```bash
pip install litestar-vite
npm install -D vite litestar-vite-plugin
# Plus a framework adapter, e.g.:
npm install -D @vitejs/plugin-react   # or @vitejs/plugin-vue, etc.
```

Optional bootstrap: `litestar assets init` scaffolds `vite.config.ts` + `package.json`.

### Step 3: Wire ViteConfig (Python)

Define `ViteConfig` with `paths=PathConfig(...)`, optional `runtime=RuntimeConfig(...)`, and optional `types=True` / `types=TypeGenConfig(...)`. Toggle `dev_mode` from an env var. Add to `Litestar(plugins=[VitePlugin(config=...)])`.

### Step 4: Wire vite.config.ts (JS)

Add `litestar()` with `input`. Let the `.litestar.json` bridge provide `bundleDir`, `hotFile`, typegen paths, and asset URL unless you are deliberately overriding Python config. Set `base` for prod CDN if needed.

### Step 5: Enable Type Generation (optional)

For SPA / Inertia projects, set `types=TypeGenConfig(...)`. Re-run `litestar assets generate-types` whenever DTOs change. CI should fail if generated files are out of date.

### Step 6: Wire Templates (template / HTMX modes)

Use `vite_hmr()` and `vite()` in your base template.
For HTMX, register `HTMXPlugin()` and keep `ViteConfig(mode="htmx", ...)`.

### Step 7: Verify HMR

`litestar run` → check the dev banner shows `Vite serving at http://localhost:5173`. Edit a frontend file → browser updates without reload. If it doesn't, check the troubleshooting list below.

### Step 8: Build & Deploy

`litestar assets build` in CI → ship `bundle_dir/` as static assets or push to CDN. Set `dev_mode=False` in production env.

</workflow>

<guardrails>

## Guardrails

- **`ViteConfig` is the source of truth** — avoid JS-side `bundleDir`, `hotFile`, and `assetUrl` overrides unless this is a standalone/mono-repo override. Mismatch breaks HMR or manifest resolution silently.
- **Use proxy mode by default** — Vite can auto-pick a port and the hot file carries the actual URL. Pin `server.port` only for direct/two-port workflows.
- **Set `server.cors: true` only for different public origins** — proxy mode keeps Litestar as the public origin.
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

- [ ] Mode (`spa` / `template` / `htmx` / `hybrid` / `framework` / `external`) is explicit
- [ ] HTMX apps use `mode="htmx"` with `HTMXPlugin()`
- [ ] Inertia apps put `InertiaConfig` on `ViteConfig` and register one `VitePlugin`
- [ ] JS-side `bundleDir` / `hotFile` / `assetUrl` overrides are absent or intentionally match `ViteConfig`
- [ ] `dev_mode` is env-toggled
- [ ] Direct/two-port workflows pin `server.port`; proxy-mode workflows do not rely on a fixed Vite port
- [ ] `server.cors: true` only if Litestar and Vite are different public origins in dev
- [ ] Template base file uses `vite_hmr()` before `vite(...)`
- [ ] If `types=TypeGenConfig(...)`, generated types are committed or CI verifies they are up-to-date
- [ ] Production build sets `dev_mode=False` and ships `manifest.json` + hashed bundles
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
  server: { port: Number(process.env.VITE_PORT ?? 3006) }, // direct/two-port workflows only
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
