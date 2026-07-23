# litestar-vite — Config Reference

Full reference for the Python `ViteConfig` family, the generated `.litestar.json` bridge, and the JS-side `vite.config.ts` entrypoint.

## ViteConfig

```python
from litestar_vite import DeployConfig, PathConfig, RuntimeConfig, TypeGenConfig, ViteConfig
from litestar_vite.config import ExternalDevServer, LoggingConfig
from litestar_vite.inertia import InertiaConfig

ViteConfig(
    mode="spa",                          # spa | template | hybrid | framework
    enabled=True,                        # False keeps CLI access but disables runtime wiring
    paths=PathConfig(...),
    runtime=RuntimeConfig(...),
    types=TypeGenConfig(generate_page_props=False),
    inertia=None,                        # True or InertiaConfig(...) for Inertia
    logging=LoggingConfig(...),
    deploy=DeployConfig(...),
    dev_mode=False,                      # env-toggled; True in dev
)
```

`ViteConfig` is the Python source of truth. `litestar-vite` writes `.litestar.json`; the npm plugin reads that bridge so JS config normally only needs `litestar({ input: [...] })`.

The canonical modes are `spa`, `template`, `hybrid`, and `framework`.
Aliases normalize immediately: `htmx` to `template`, `inertia` to `hybrid`,
and `ssr` / `ssg` to `framework`. `external` is deprecated and requires
`ExternalDevServer`; replace it with `mode="framework"`.

`enabled=None` is the default auto-detection state and consults `VITE_ENABLED`.
`enabled=False` registers no Vite routes, middleware, static routers, lifespans,
or SPA handler. The plugin configuration and `litestar assets` commands remain
available.

## PathConfig

| Option | Default | Description |
| --- | --- | --- |
| `root` | `Path.cwd()` | Project root (parent of `vite.config.*`) |
| `resource_dir` | `"src"` | Frontend source root |
| `bundle_dir` | `"public"` | Production build output |
| `static_dir` | `"public"` | Static files copied by Vite; adjusted to `<resource_dir>/public` if it would collide with `bundle_dir` |
| `manifest_name` | `"manifest.json"` | Configured manifest filename |
| `hot_file` | `"hot"` | Dev-server marker written through the `.litestar.json` bridge; match JS `hotFile` only when overriding it manually |
| `asset_url` | `ASSET_URL` or `"/static/"` | Public URL prefix for production assets |
| `ssr_output_dir` | `None` | SSR bootstrap output directory |

## RuntimeConfig

| Option | Default | Description |
| --- | --- | --- |
| `port` | `5173` | Vite dev server port |
| `host` | `"127.0.0.1"` | Vite dev server host |
| `protocol` | `"http"` | `"http"` or `"https"` |
| `executor` | `"node"` after normalization | JS runtime (`node`, `bun`, `deno`, `yarn`, `pnpm`) |
| `start_dev_server` | `True` | Start the dev server when `dev_mode=True` |
| `is_react` | `False` | Enable React Fast Refresh support |
| `proxy_mode` | mode-derived | `"vite"` proxies Vite HTTP + WS/HMR through Litestar; `"proxy"` proxies framework dev servers; production uses `None` |
| `external_dev_server` | `None` | External server metadata for framework/external workflows |
| `set_environment` | `True` | Export Vite env vars before running frontend commands |
| `set_static_folders` | `True` | Register static folders for production assets |
| `detect_nodeenv` | `False` | Prefer a nodeenv-managed Node runtime when available |
| `extra_route_prefixes` | `()` | Additional Litestar paths excluded from SPA/framework fallback routing |

`RuntimeConfig.proxy_mode` accepts `"vite"`, `"proxy"`, or `None`. Legacy
`VITE_PROXY_MODE=direct` emits `DeprecationWarning` and becomes `"vite"`.
Browser requests stay on the Litestar origin. Configure
`ExternalDevServer(target=..., command=..., build_command=...)` only when a
non-Vite frontend server owns HTML.

## TypeGenConfig

| Option | Default | Description |
| --- | --- | --- |
| `generate_sdk` | `True` | TypeScript API client |
| `generate_zod` | `False` | Zod schemas through the hey-api `zod` plugin |
| `generate_routes` | `True` | `routes.ts` typed URL builder |
| `generate_schemas` | `True` | `schemas.ts` from OpenAPI |
| `generate_page_props` | `True` | Inertia-only — `page-props.ts` generated from `inertia-pages.json`; requires `ViteConfig.inertia` |
| `output` | `"src/generated"` | Output directory (relative to `paths.root`) |
| `routes_path` | `output / "routes.json"` | Route metadata JSON consumed by the JS plugin |
| `routes_ts_path` | `output / "routes.ts"` | Typed route helper |
| `page_props_path` | `output / "inertia-pages.json"` | Inertia page-props metadata consumed by the JS plugin |
| `schemas_ts_path` | `output / "schemas.ts"` | Ergonomic form/response helper types |
| `fail_on_error` | `None` | Fail builds and warn during dev by default; explicit `False` keeps warn-only behavior |
| `fallback_type` | `"unknown"` | Fallback for untyped containers in Inertia props |
| `type_import_paths` | `{}` | TypeScript imports for page-prop types absent from OpenAPI |
| `extra_commands` | `[]` | Code generators run before the JS typegen CLI |

The JS generator writes hey-api output under `output/api/`, plus
`page-props.ts`, `schemas.ts`, and `static-props.ts` when enabled.

## LoggingConfig

Import `LoggingConfig` from `litestar_vite.config`.

| Option | Default | Description |
| --- | --- | --- |
| `level` | env or `"normal"` | `"quiet"`, `"normal"`, or `"verbose"` |
| `show_paths_absolute` | `False` | Show absolute instead of project-relative paths |
| `suppress_npm_output` | `False` | Hide package-manager script preambles |
| `suppress_vite_banner` | `False` | Hide the Vite startup banner |
| `timestamps` | `False` | Prefix lifecycle output with timestamps |

Release `0.27.0` removes routine success/start/stop chatter. Warnings honor
quiet mode, and non-TTY warnings and errors use Python logging. Missing assets
stay quiet until a serving path needs them, then errors instruct the user to
run `litestar assets build` without exposing absolute manifest paths.

## DeployConfig

`DeployConfig(enabled=True, storage_backend="s3://bucket/assets")` enables
`litestar assets deploy`. `storage_options` pass through to fsspec,
`asset_url` sets the build base, `delete_orphaned` controls remote cleanup, and
`include_manifest` controls manifest upload.

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
| `server.port` | Optional internal Vite port pin; browser traffic still uses Litestar |
| `server.ws` | Vite 8.1+ HMR network overrides (`host`, `port`, `clientPort`, `path`, `protocol`, `timeout`) |
| `server.hmr` | Vite 7 / 8.0 HMR network overrides; `false` disables HMR |
| `build.outDir` | Match `bundle_dir` |
| `build.emptyOutDir` | `true` to avoid stale assets |

## Env Toggles

| Env Var | Purpose |
| --- | --- |
| `ENV` / `LITESTAR_ENV` | Drives `dev_mode` |
| `ASSET_URL` | CDN base URL in prod |
| `VITE_PORT` | Override dev port |
| `VITE_ENABLED` | Disable runtime wiring while retaining CLI/config access |
| `VITE_DEV_MODE` | Enable development behavior |
| `VITE_PROXY_MODE` | `vite`, `proxy`, or `none`; `direct` is deprecated |
| `LITESTAR_VITE_LOG_LEVEL` | `quiet`, `normal`, or `verbose` |
| `VITE_DEPLOY_STORAGE` | fsspec destination for `assets deploy` |
| `VITE_DEPLOY_ASSET_URL` | Public CDN URL used as the deployment build base |
