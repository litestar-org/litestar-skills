# litestar-vite — Config Reference

Full reference for the Python `ViteConfig` family, the generated `.litestar.json` bridge, and the JS-side `vite.config.ts` entrypoint.

## ViteConfig

```python
from litestar_vite import (
    DeployConfig,
    InertiaConfig,
    PathConfig,
    RuntimeConfig,
    TypeGenConfig,
    ViteConfig,
)
from litestar_vite.config import LoggingConfig, SPAConfig

ViteConfig(
    mode="spa",
    enabled=True,
    paths=PathConfig(),
    runtime=RuntimeConfig(),
    types=TypeGenConfig(generate_page_props=False),
    inertia=None,
    spa=SPAConfig(),
    logging=LoggingConfig(),
    deploy=DeployConfig(),
    dev_mode=False,
)
```

`ViteConfig` is the Python source of truth. `litestar-vite` writes `.litestar.json`; the npm plugin reads that bridge so JS config normally only needs `litestar({ input: [...] })`.

The canonical modes are `spa`, `template`, `hybrid`, and `framework`.
Aliases normalize immediately: `htmx` to `template`, `inertia` to `hybrid`,
and `ssr` / `ssg` to `framework`. `external` also normalizes to `framework`
and additionally requires `runtime.external_dev_server`. All five aliases are
permanent and normalize silently.

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
| `http2` | `True` | Enable HTTP/2 proxy support when `h2` is installed |
| `csp_nonce` | `None` | CSP nonce injected into script tags |
| `spa_handler` | `True` | Enable SPA catch-all route handler |

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

## InertiaConfig & InertiaSSRConfig

Import `InertiaConfig` and `InertiaSSRConfig` from `litestar_vite` or
`litestar_vite.config`. Import `InertiaTypeGenConfig` from
`litestar_vite.config`.

| Option | Default | Description |
| --- | --- | --- |
| `root_template` | `"index.html"` | Root HTML template / shell for initial page visit |
| `component_opt_keys` | `("component", "page")` | Route handler opt keys used to match Inertia page components |
| `redirect_unauthorized_to` | `None` | Named route or path to redirect 401/403 exceptions |
| `redirect_404` | `None` | Named route or path to redirect 404 exceptions |
| `extra_static_page_props` | `{}` | Static props shared across all Inertia pages |
| `extra_session_page_props` | `set()` / `{}` | Keys pulled from session and merged into page props |
| `shared_page_prop_types` | `None` | Type mappings for shared props (injected into generated `inertia.d.ts`) |
| `encrypt_history` | `False` | Enable Inertia browser history encryption |
| `type_gen` | `None` | `InertiaTypeGenConfig(include_default_auth=True, include_default_flash=True)` |
| `ssr` | `None` | `InertiaSSRConfig(...)` or `bool` for SSR server integration |
| `use_script_element` | `True` | Embed page JSON inside `<script type="application/json">` tag |
| `precognition` | `False` | Enable Laravel Precognition compatible real-time validation exception handler |

`InertiaSSRConfig` options:

| Option | Default | Description |
| --- | --- | --- |
| `enabled` | `True` | Enable SSR rendering |
| `url` | `"http://127.0.0.1:13714/render"` | Local SSR renderer endpoint |
| `timeout` | `2.0` | HTTP timeout in seconds for SSR render requests |
| `target_selector` | `"#app"` | Container selector to replace with SSR output |
| `command` | `None` | Command to spawn SSR node process (e.g. `["node", "resources/ssr.js"]`) |
| `cwd` | `None` | Working directory for the SSR process |
| `auto_start` | `True` | Automatically start and stop the SSR process with the Litestar lifespan |
| `health_check` | `False` | Check SSR server availability on startup |
| `health_check_timeout` | `10.0` | Maximum wait time in seconds for SSR server health check |

## LoggingConfig

Import `LoggingConfig` from `litestar_vite.config`.

| Option | Default | Description |
| --- | --- | --- |
| `level` | env or `"normal"` | `"quiet"`, `"normal"`, or `"verbose"` |
| `show_paths_absolute` | `False` | Show absolute instead of project-relative paths |
| `suppress_npm_output` | `False` | Hide package-manager script preambles |
| `suppress_vite_banner` | `False` | Hide the Vite startup banner |
| `timestamps` | `False` | Prefix lifecycle output with timestamps |

Warnings honor quiet mode, and non-TTY warnings and errors use Python logging.
Missing assets stay quiet until a serving path needs them, then errors instruct
the user to run `litestar assets build` without exposing absolute manifest paths.

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
  input: ["src/main.tsx", "src/styles.css"],
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
