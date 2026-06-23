# litestar-vite — Config Reference

Full reference for the Python `ViteConfig` family, the generated `.litestar.json` bridge, and the JS-side `vite.config.ts` entrypoint.

## ViteConfig

```python
from litestar_vite import PathConfig, RuntimeConfig, TypeGenConfig, ViteConfig
from litestar_vite.inertia import InertiaConfig

ViteConfig(
    mode="spa",                          # spa | template | htmx | hybrid | framework | external
    paths=PathConfig(...),
    runtime=RuntimeConfig(...),
    types=True,                          # or TypeGenConfig(...); presence enables type generation
    inertia=True,                        # or InertiaConfig(...); Inertia only
    dev_mode=False,                      # env-toggled; True in dev
)
```

`ViteConfig` is the Python source of truth. `litestar-vite` writes `.litestar.json`; the npm plugin reads that bridge so JS config normally only needs `litestar({ input: [...] })`.

## PathConfig

| Option | Default | Description |
| --- | --- | --- |
| `root` | `Path.cwd()` | Project root (parent of `vite.config.*`) |
| `resource_dir` | `"src"` | Frontend source root |
| `bundle_dir` | `"public"` | Production build output |
| `static_dir` | `"public"` | Static files copied by Vite; adjusted to `<resource_dir>/public` if it would collide with `bundle_dir` |
| `hot_file` | `"hot"` | Dev-server marker written through the `.litestar.json` bridge; match JS `hotFile` only when overriding it manually |
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
| `proxy_mode` | auto | `"vite"` proxies Vite HTTP + WS/HMR through Litestar; `"proxy"` proxies framework dev servers |
| `external_dev_server` | `None` | External server metadata for framework/external workflows |
| `set_environment` | `True` | Export Vite env vars before running frontend commands |
| `set_static_folders` | `True` | Register static folders for production assets |
| `detect_nodeenv` | `False` | Prefer a nodeenv-managed Node runtime when available |

## TypeGenConfig

| Option | Default | Description |
| --- | --- | --- |
| `generate_sdk` | `True` | TypeScript API client |
| `generate_routes` | `True` | `routes.ts` typed URL builder |
| `generate_schemas` | `True` | `schemas.ts` from OpenAPI |
| `generate_page_props` | `True` | Inertia-only — `page-props.ts` generated from `inertia-pages.json`; requires `ViteConfig.inertia` |
| `output` | `"src/generated"` | Output directory (relative to `paths.root`) |
| `routes_path` | `output / "routes.json"` | Route metadata JSON consumed by the JS plugin |
| `routes_ts_path` | `output / "routes.ts"` | Typed route helper |
| `page_props_path` | `output / "inertia-pages.json"` | Inertia page-props metadata consumed by the JS plugin |
| `schemas_ts_path` | `output / "schemas.ts"` | Ergonomic form/response helper types |

## vite.config.ts Contract

The JS-side plugin (`litestar-vite-plugin` from npm) reads `.litestar.json`. Keep `input` in `vite.config.ts`; let Python own paths, proxy mode, typegen paths, and asset URL unless this is a standalone/override setup:

```ts
import litestar from "litestar-vite-plugin"

litestar({
  input: ["src/main.tsx", "src/styles.css"],   // under ViteConfig.paths.resource_dir
})
```

Only pass `bundleDir`, `hotFile`, or `assetUrl` in JS when overriding the Python bridge deliberately, such as a standalone frontend build or custom mono-repo layout.

Also configure Vite top-level:

| Field | Why |
| --- | --- |
| `base` | Asset URL base; CDN URL in prod |
| `publicDir` | Static files copied verbatim |
| `server.port` | Optional in proxy mode; pin for direct/external two-port workflows |
| `server.cors: true` | Only needed when Litestar and Vite are different public origins |
| `build.outDir` | Match `bundle_dir` |
| `build.emptyOutDir` | `true` to avoid stale assets |

## Env Toggles

| Env Var | Purpose |
| --- | --- |
| `ENV` / `LITESTAR_ENV` | Drives `dev_mode` |
| `ASSET_URL` | CDN base URL in prod |
| `VITE_PORT` | Override dev port |
