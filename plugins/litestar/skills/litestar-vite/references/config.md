# litestar-vite — Config Reference

Full reference for the Python `ViteConfig` family and the JS-side `vite.config.ts` contract.

## ViteConfig

```python
from litestar_vite import InertiaConfig, PathConfig, RuntimeConfig, TypeGenConfig, ViteConfig

ViteConfig(
    mode="spa",                          # spa | template | hybrid | ssr | ssg | external
    paths=PathConfig(...),
    runtime=RuntimeConfig(...),
    types=TypeGenConfig(...),            # presence enables type generation
    inertia=InertiaConfig(...),          # Inertia only
    dev_mode=False,                      # env-toggled; True in dev
)
```

## PathConfig

| Option | Default | Description |
| --- | --- | --- |
| `root` | `Path.cwd()` | Project root (parent of `vite.config.*`) |
| `resource_dir` | `"src"` | Frontend source root |
| `bundle_dir` | `"public"` | Production build output |
| `static_dir` | `"public"` | Static files copied by Vite; adjusted to `<resource_dir>/public` if it would collide with `bundle_dir` |
| `hot_file` | `"hot"` | Dev-server marker; must match `litestar()` `hotFile` |
| `asset_url` | `ASSET_URL` or `"/static/"` | Public URL prefix for production assets |
| `ssr_output_dir` | `None` | SSR bootstrap output directory |

## RuntimeConfig

| Option | Default | Description |
| --- | --- | --- |
| `port` | `5173` | Vite dev server port |
| `host` | `"127.0.0.1"` | Vite dev server host |
| `protocol` | `"http"` | `"http"` or `"https"` |
| `executor` | `None` | JS runtime (`node`, `bun`, `deno`, `yarn`, `pnpm`) |
| `start_dev_server` | `True` | Start the dev server when `dev_mode=True` |
| `is_react` | `False` | Enable React Fast Refresh support |

## TypeGenConfig

| Option | Default | Description |
| --- | --- | --- |
| `generate_sdk` | `True` | TypeScript API client |
| `generate_routes` | `True` | `routes.ts` typed URL builder |
| `generate_schemas` | `True` | `schemas.ts` from OpenAPI |
| `generate_page_props` | `True` | Inertia-only — `inertia-pages.json`; requires `ViteConfig.inertia` |
| `output` | `"src/generated"` | Output directory (relative to `paths.root`) |

## vite.config.ts Contract

The JS-side plugin (`litestar-vite-plugin` from npm) must agree with `ViteConfig` on these:

```ts
import litestar from "litestar-vite-plugin"

litestar({
  input: ["src/main.tsx", "src/styles.css"],   // under ViteConfig.paths.resource_dir
  bundleDir: "...",                             // matches ViteConfig.paths.bundle_dir
  hotFile: "...",                               // matches ViteConfig.paths.hot_file
  assetUrl: "/static/",                         // matches Vite `base` in prod
})
```

Also configure Vite top-level:

| Field | Why |
| --- | --- |
| `base` | Asset URL base; CDN URL in prod |
| `publicDir` | Static files copied verbatim |
| `server.port` | Pin to match `RuntimeConfig.port` |
| `server.cors: true` | Allow Litestar origin to fetch dev assets |
| `build.outDir` | Match `bundle_dir` |
| `build.emptyOutDir` | `true` to avoid stale assets |

## Env Toggles

| Env Var | Purpose |
| --- | --- |
| `ENV` / `LITESTAR_ENV` | Drives `dev_mode` |
| `ASSET_URL` | CDN base URL in prod |
| `VITE_PORT` | Override dev port |
