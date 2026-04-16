# litestar-vite — Config Reference

Full reference for the Python `ViteConfig` family and the JS-side `vite.config.ts` contract.

## ViteConfig

```python
from litestar_vite import ViteConfig, PathConfig, RuntimeConfig, TypeGenConfig

ViteConfig(
    mode="spa",                          # spa | template | htmx | hybrid | framework
    paths=PathConfig(...),
    runtime=RuntimeConfig(...),
    types=TypeGenConfig(...),            # optional
    use_asset_linker=True,
    use_server_lifespan=True,
    dev_mode=False,                      # env-toggled; True in dev
    hot_file="public/hot",               # MUST match vite.config.ts hotFile
)
```

## PathConfig

| Option | Default | Description |
|---|---|---|
| `root` | `Path.cwd()` | Project root (parent of `vite.config.*`) |
| `resource_dir` | `"resources"` | Frontend source root |
| `bundle_dir` | `"public"` | Production build output |
| `public_dir` | `"public"` | Static files served at `/` |
| `vite_config` | `"vite.config.ts"` | Path to the JS-side config file |

## RuntimeConfig

| Option | Default | Description |
|---|---|---|
| `port` | `5173` | Vite dev server port |
| `host` | `"localhost"` | Vite dev server host |
| `protocol` | `"http"` | `"http"` or `"https"` |
| `hot_reload` | `True` | Enable HMR |

## TypeGenConfig

| Option | Default | Description |
|---|---|---|
| `enabled` | `False` | Master switch |
| `generate_sdk` | `False` | TypeScript API client |
| `generate_routes` | `False` | `routes.ts` typed URL builder |
| `generate_schemas` | `False` | `schemas.ts` from OpenAPI |
| `generate_page_props` | `False` | Inertia-only — `inertia-pages.json` |
| `output` | `"src/generated"` | Output directory (relative to `paths.root`) |

## vite.config.ts Contract

The JS-side plugin (`litestar-vite-plugin` from npm) must agree with `ViteConfig` on these:

```ts
import litestar from "litestar-vite-plugin"

litestar({
  input: ["src/main.tsx", "src/styles.css"],   // matches ViteConfig.resource_dir
  bundleDir: "...",                             // matches ViteConfig.bundle_dir
  hotFile: "...",                               // matches ViteConfig.hot_file
  assetUrl: "/static/",                         // matches Vite `base` in prod
})
```

Also configure Vite top-level:

| Field | Why |
|---|---|
| `base` | Asset URL base; CDN URL in prod |
| `publicDir` | Static files copied verbatim |
| `server.port` | Pin to match `RuntimeConfig.port` |
| `server.cors: true` | Allow Litestar origin to fetch dev assets |
| `build.outDir` | Match `bundle_dir` |
| `build.emptyOutDir` | `true` to avoid stale assets |

## Env Toggles

| Env Var | Purpose |
|---|---|
| `ENV` / `LITESTAR_ENV` | Drives `dev_mode` |
| `ASSET_URL` | CDN base URL in prod |
| `VITE_PORT` | Override dev port |
