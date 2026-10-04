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
from litestar_vite.config import LoggingConfig, PaginationContainer, SPAConfig

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
    static_props=None,
    dev_mode=False,
    base_url=None,
    guards=None,
    exclude_static_from_auth=True,
    spa_path=None,
    include_root_spa_paths=False,
)
```

`ViteConfig` is the Python source of truth. `litestar-vite` writes `.litestar.json`; the npm plugin reads that bridge so JS config normally only needs `litestar({ input: [...] })`.

| Option | Default | Description |
| --- | --- | --- |
| `mode` | `None` (inferred; defaults to `"template"`) | `"spa"`, `"template"`, `"hybrid"`, or `"framework"` (aliases: `"htmx"`, `"inertia"`, `"ssr"`, `"ssg"`, `"external"`) |
| `paths` | `PathConfig()` | Filesystem and asset URL path configuration |
| `runtime` | `RuntimeConfig()` | Dev server, proxy, and process execution settings |
| `types` | `None` | `True` or `TypeGenConfig(...)` to enable end-to-end TypeScript generation |
| `inertia` | `None` | `True`, `InertiaConfig(...)`, or `dict` (auto-sets `mode="hybrid"` when `mode=None`) |
| `spa` | `True` (for `spa`/`hybrid`) or `SPAConfig` | HTML transformation and CSRF injection settings |
| `logging` | `None` (`LoggingConfig()`) | Console and lifecycle logging configuration |
| `deploy` | `False` (`DeployConfig(enabled=False)`) | Remote storage deployment settings (`litestar assets deploy`) |
| `static_props` | `None` | Static JSON-serializable dict exposed via `virtual:litestar-static-props` and `static-props.ts` |
| `dev_mode` | `None` (from `runtime.dev_mode`) | Shortcut override for `runtime.dev_mode` |
| `base_url` | `VITE_BASE_URL` or `None` | Public base URL of the Litestar application |
| `enabled` | `None` (auto-detect / `VITE_ENABLED`) | `False` skips runtime routes, middleware, static routers, lifespans, and SPA handler while keeping CLI/config active |
| `guards` | `None` | Litestar route guards applied to SPA catch-all HTML routes |
| `exclude_static_from_auth` | `True` | Sets `opt={"exclude_from_auth": True}` directly on static asset route handlers (`0.30.1+`) |
| `spa_path` | `None` (`"/"`) | Path prefix where the SPA catch-all handler is mounted |
| `include_root_spa_paths` | `False` | Also register root `/` catch-all routes when `spa_path` is a non-root prefix |

The canonical modes are `spa`, `template`, `hybrid`, and `framework`.
Aliases normalize immediately: `htmx` to `template`, `inertia` to `hybrid`,
and `ssr` / `ssg` to `framework`. `external` also normalizes to `framework`
and additionally requires `runtime.external_dev_server`. All five aliases are
permanent and normalize silently.

`PaginationContainer` (`from litestar_vite.config import PaginationContainer`) is the runtime-checkable protocol (`items` + pagination metadata) recognized by Inertia pagination and scroll-props extraction.

## VitePlugin & Static Server Contract (`0.30.1+`)

```python
from litestar_vite import (
    StaticPlacement,
    StaticServerConfig,
    StaticServerMount,
    VitePlugin,
)

plugin = VitePlugin(config=vite_config, asset_loader=None, static_files_config=None)
static_cfg: StaticServerConfig = plugin.get_static_server_config()
```

- `static_files_config`: Optional dict matching Litestar's `create_static_files_router` kwargs (excluding `path` and `directories`).
- `plugin.get_static_server_config()` returns `StaticServerConfig(placement=StaticPlacement.NATIVE | StaticPlacement.ASGI, mounts=(StaticServerMount(...),), reason=...)` for Granian native static file serving eligibility without requiring `exclude_static_from_auth`.

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
| `dev_mode` | `VITE_DEV_MODE` or `False` | Enable development mode |
| `port` | `VITE_PORT` or `5173` | Vite dev server port |
| `host` | `VITE_HOST` or `"127.0.0.1"` | Vite dev server host |
| `protocol` | `VITE_PROTOCOL` or `"http"` | `"http"` or `"https"` |
| `executor` | `"node"` after normalization | JS runtime (`node`, `bun`, `deno`, `yarn`, `pnpm`) |
| `run_command` | `None` | Custom dev command override (e.g. `["npm", "run", "dev"]`) |
| `build_command` | `None` | Custom build command override |
| `build_watch_command` | `None` | Custom watch-build command override |
| `serve_command` | `None` | Custom production SSR server command override (`litestar assets serve --production`) |
| `install_command` | `None` | Custom package install command override |
| `start_dev_server` | `True` | Start the dev server when `dev_mode=True` |
| `is_react` | `False` | Enable React Fast Refresh preamble support |
| `health_check` | `VITE_HEALTH_CHECK` or `False` | Wait for Vite dev server health check on startup |
| `proxy_mode` | mode-derived | `"vite"` proxies Vite HTTP + WS/HMR through Litestar; `"proxy"` proxies framework dev servers; production uses `None` |
| `external_dev_server` | `None` | `ExternalDevServer` or target URL string for framework/external workflows |
| `set_environment` | `True` | Export Vite env vars before running frontend commands |
| `set_static_folders` | `True` | Register static folders for production assets |
| `detect_nodeenv` | `False` | Prefer a nodeenv-managed Node runtime when available |
| `extra_route_prefixes` | `()` | Additional Litestar paths excluded from SPA/framework fallback routing |
| `http2` | `True` | Enable HTTP/2 proxy support when `h2` is installed |
| `trusted_proxies` | `LITESTAR_TRUSTED_PROXIES` or `None` | Trusted proxy hosts/CIDRs (`"*"` or comma-separated) for `ProxyHeadersMiddleware` |
| `csp_nonce` | `None` | CSP nonce injected into script tags |
| `spa_handler` | `True` | Enable SPA catch-all route handler |

`RuntimeConfig.proxy_mode` accepts `"vite"`, `"proxy"`, or `None`. Legacy
`VITE_PROXY_MODE=direct` emits `DeprecationWarning` and becomes `"vite"`.
Browser requests stay on the Litestar origin. Configure
`ExternalDevServer(target=..., command=..., build_command=..., http2=False, enabled=True)` only when a
non-Vite frontend server owns HTML.

## SPAConfig

Import `SPAConfig` from `litestar_vite.config`.

| Option | Default | Description |
| --- | --- | --- |
| `inject_csrf` | `True` | Inject CSRF token into `window.__LITESTAR_CSRF__` in transformed HTML |
| `csrf_var_name` | `"__LITESTAR_CSRF__"` | Global window property name for the injected CSRF token |
| `app_selector` | `"#app"` | Root mount element selector |
| `cache_transformed_html` | `True` | Cache transformed `index.html` in production |
| `cache_duration` | `0` | Cache TTL in seconds (`0` caches indefinitely in production) |

## TypeGenConfig

| Option | Default | Description |
| --- | --- | --- |
| `output` | `Path("src/generated")` | Output directory (relative to `paths.root`) |
| `openapi_path` | `output / "openapi.json"` | Exported OpenAPI schema path |
| `routes_path` | `output / "routes.json"` | Route metadata JSON consumed by the JS plugin |
| `routes_ts_path` | `output / "routes.ts"` | Typed route helper + `CSRF_COOKIE_NAME` / `CSRF_HEADER_NAME` constants (`0.31.0+`) |
| `page_props_path` | `output / "inertia-pages.json"` | Inertia page-props metadata consumed by the JS plugin |
| `schemas_ts_path` | `output / "schemas.ts"` | Ergonomic form/response helper types |
| `asyncapi_path` | `output / "asyncapi.json"` | Exported AsyncAPI 3.0 document path (`0.32.0+`) |
| `channels_ts_path` | `output / "channels.ts"` | Generated `ChannelMap` TypeScript definitions (`0.32.0+`) |
| `generate_sdk` | `True` | TypeScript API client (`@hey-api/openapi-ts`) |
| `generate_zod` | `False` | Zod schemas through the hey-api `zod` plugin |
| `generate_routes` | `True` | `routes.ts` typed URL builder |
| `generate_schemas` | `True` | `schemas.ts` from OpenAPI |
| `generate_page_props` | `True` | Inertia-only — `page-props.ts` generated from `inertia-pages.json`; requires `ViteConfig.inertia` |
| `generate_channels` | `True` | Generate `asyncapi.json` and `channels.ts` when `AsyncAPIPlugin` (`litestar-asyncapi`) is registered on the Litestar app (`0.32.0+`) |
| `global_route` | `False` | Register `window.route` global in generated `routes.ts` |
| `fail_on_error` | `None` | Fail builds (`True`) and warn during dev (`False`) by default; explicit bool overrides both |
| `fallback_type` | `"unknown"` | Fallback (`"unknown"` or `"any"`) for untyped containers in Inertia props |
| `type_import_paths` | `{}` | Map of schema/class name → TypeScript import path for page-prop types absent from OpenAPI |
| `extra_commands` | `[]` | Additional codegen commands (e.g. `[["tsr", "generate"]]`) run after metadata export and before `litestar-vite-typegen` |

The JS generator writes hey-api output under `output/api/`, plus
`page-props.ts`, `schemas.ts`, `static-props.ts`, and `channels.ts` (`0.32.0+`, when `AsyncAPIPlugin` is registered) when enabled.

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
| `extra_session_page_props` | `set()` | Keys pulled from session and merged into page props |
| `shared_page_prop_types` | `None` | Type mappings for shared props (injected into generated `inertia.d.ts`) |
| `encrypt_history` | `False` | Enable Inertia browser history encryption |
| `type_gen` | `None` | `InertiaTypeGenConfig(include_default_auth=True, include_default_flash=True)` |
| `ssr` | `None` | `InertiaSSRConfig(...)` or `bool` for SSR server integration |
| `use_script_element` | `True` | Embed page JSON inside `<script type="application/json">` tag |
| `precognition` | `False` | Enable Laravel Precognition compatible real-time validation exception handler |

`InertiaSSRConfig` options (`0.32.0+` IPC SSR; replaces `0.31.0` HTTP `url`, `auto_start`, `health_check`, and `health_check_timeout` fields):

| Option | Default | Description |
| --- | --- | --- |
| `enabled` | `True` | Enable SSR rendering |
| `timeout` | `2.0` | Timeout in seconds for SSR render requests |
| `target_selector` | `"#app"` | Container selector to replace with SSR output |
| `command` | `None` | Command to spawn production SSR worker process (defaults to `["node", "<ssr_bundle_path>"]`) |
| `cwd` | `None` | Working directory for the production SSR process |
| `fallback_to_client` | `True` | Fall back to client-side CSR bootstrap if SSR rendering fails (`0.32.0+`) |
| `circuit_breaker_enabled` | `True` | Enable `SSRCircuitBreaker` to short-circuit repeated SSR failures (`0.32.0+`) |
| `circuit_breaker_failure_threshold` | `3` | Consecutive failures before opening the SSR circuit (`0.32.0+`) |
| `circuit_breaker_reset_timeout` | `30.0` | Seconds before transitioning an open circuit to `HALF_OPEN` (`0.32.0+`) |

In `0.32.0+`, `litestar_vite.ipc` exports `BaseIPCTransport`, `StdioIPCTransport`, `TCPStreamIPCTransport`, `SSRCircuitBreaker`, `CircuitState`, `IPCError`, `IPCRequest`, `IPCResponse`, `IPCTimeoutError`, `IPCWorkerCrashError`, and `CircuitBreakerOpenError`.

## LoggingConfig

Import `LoggingConfig` from `litestar_vite.config`.

| Option | Default | Description |
| --- | --- | --- |
| `level` | `LITESTAR_VITE_LOG_LEVEL` or `"normal"` | `"quiet"`, `"normal"`, or `"verbose"` |
| `show_paths_absolute` | `False` | Show absolute instead of project-relative paths |
| `suppress_npm_output` | `False` | Hide package-manager script preambles |
| `suppress_vite_banner` | `False` | Hide the Vite startup banner |
| `timestamps` | `False` | Prefix lifecycle output with timestamps |

Warnings honor quiet mode, and non-TTY warnings and errors use Python logging.
Missing assets stay quiet until a serving path needs them, then errors instruct
the user to run `litestar assets build` without exposing absolute manifest paths.

## DeployConfig

| Option | Default | Description |
| --- | --- | --- |
| `enabled` | `True` on `DeployConfig()`; `ViteConfig.deploy` defaults to `False` | Enable remote deployment via `litestar assets deploy` |
| `storage_backend` | `VITE_DEPLOY_STORAGE` or `None` | fsspec URL (`s3://bucket/assets`, `gcs://...`, `abfs://...`) |
| `storage_options` | `{}` | Options forwarded to `fsspec.core.url_to_fs` |
| `asset_url` | `VITE_DEPLOY_ASSET_URL` or `None` | Public CDN URL injected as `ASSET_URL` during `litestar assets deploy` builds |
| `include_manifest` | `True` | Upload `manifest.json` alongside hashed bundles |
| `delete_orphaned` | `VITE_DEPLOY_DELETE` or `True` | Delete remote files absent from the local bundle |
| `content_types` | `{}` | Custom filename extension → MIME content-type overrides |

Use `deploy_config.with_overrides(storage_backend=..., storage_options=..., delete_orphaned=..., asset_url=...)` to clone a `DeployConfig` with CLI overrides.

## vite.config.ts Contract

The JS-side plugin (`litestar-vite-plugin` from npm) reads `.litestar.json`. Keep `input` in `vite.config.ts`; let Python own paths, proxy mode, typegen paths, and asset URL unless this is a standalone/override setup:

```ts
import litestar from "litestar-vite-plugin"

litestar({
  input: ["src/main.tsx", "src/styles.css"],
})
```

Full `PluginConfig` options accepted by `litestar(...)`:

| Option | Default | Description |
| --- | --- | --- |
| `input` | required | Entry file path(s) to bundle |
| `assetUrl` | bridge / `"/static/"` | Base path for asset URLs |
| `deployAssetUrl` | bridge / `null` | CDN asset URL used during `litestar assets deploy` |
| `bundleDir` | bridge / `"public"` | Build output directory |
| `staticDir` | bridge / `<resourceDir>/public` | Static public assets directory |
| `resourceDir` | bridge / `"src"` | Frontend source directory |
| `hotFile` | bridge / `<bundleDir>/hot` | Dev server hotfile path |
| `ssr` | `undefined` | SSR entry point |
| `ssrOutDir` | bridge / `<bundleDir>/bootstrap/ssr` | SSR output directory |
| `refresh` | `true` | Full-reload watch config (`boolean \| string \| string[] \| RefreshConfig`) |
| `detectTls` | `null` | Herd / Valet TLS domain detection |
| `autoDetectIndex` | `true` | Auto-serve `index.html` in SPA mode |
| `inertiaMode` | bridge | Disable automatic `index.html` serving when Inertia owns HTML |
| `transformOnServe` | `undefined` | Custom `(code, devServerUrl) => string` hook |
| `types` | `"auto"` | `boolean \| "auto" \| TypesConfig` |
| `executor` | bridge / `"node"` | JS package executor (`node`, `bun`, `deno`, `yarn`, `pnpm`) |

For Vite 7+ `ModuleRunner` dev SSR and fragment rendering (`0.32.0+`), register `litestarViteSsrPlugin` from `litestar-vite-plugin/dev-ssr`:

```ts
import litestar from "litestar-vite-plugin"
import { litestarViteSsrPlugin } from "litestar-vite-plugin/dev-ssr"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [
    litestar({ input: ["resources/main.tsx"], ssr: "resources/ssr.tsx" }),
    litestarViteSsrPlugin({ endpoint: "/__litestar_ssr__", entrypoint: "resources/ssr.tsx" }),
  ],
})
```

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
| `ENV` / `LITESTAR_ENV` | Common application environment toggle |
| `ASSET_URL` | Public asset prefix / CDN base URL in prod |
| `VITE_PORT` | Override Vite dev server port (`5173`) |
| `VITE_HOST` | Override Vite dev server host (`127.0.0.1`) |
| `VITE_PROTOCOL` | Override Vite dev server protocol (`http` / `https`) |
| `VITE_BASE_URL` | Public base URL of the Litestar server |
| `VITE_ENABLED` | Disable runtime wiring (`false`) while retaining CLI/config access |
| `VITE_DEV_MODE` | Enable development behavior (`true` / `false`) |
| `VITE_HOT_RELOAD` | Enable/disable HMR hot reload |
| `VITE_PROXY_MODE` | `vite`, `proxy`, or `none`; `direct` is deprecated |
| `VITE_HEALTH_CHECK` | Enable dev server startup health check |
| `VITE_ALLOW_EXTERNAL_HOST` | Allow non-loopback `VITE_HOST` bindings |
| `LITESTAR_TRUSTED_PROXIES` | Trusted proxy hosts/CIDRs for `ProxyHeadersMiddleware` |
| `LITESTAR_VITE_LOG_LEVEL` | `quiet`, `normal`, or `verbose` |
| `VITE_DEPLOY_STORAGE` | fsspec destination for `assets deploy` |
| `VITE_DEPLOY_ASSET_URL` | Public CDN URL used as the deployment build base |
| `VITE_DEPLOY_DELETE` | Control orphan deletion in `DeployConfig` |
