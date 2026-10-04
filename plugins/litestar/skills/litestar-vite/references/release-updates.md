# litestar-vite - Release Updates 0.26.0 to 0.32.0

This guidance is audited against `litestar-vite` `0.32.0` and covers release changes from `0.26.0` through `0.32.0`.

## Release Anchors

| Version | Upstream change | Skill guidance |
| --- | --- | --- |
| `0.26.0` | Four canonical modes with normalized aliases. | Use `spa`, `template`, `hybrid`, or `framework`. Treat `htmx`, `inertia`, `ssr`, and `ssg` as aliases; `external` also normalizes to `framework` and needs an `ExternalDevServer`. |
| `0.26.0` | `ViteConfig.enabled` and `VITE_ENABLED`. | Set `enabled=False` for CLI, worker, and test processes that need config access without runtime routes, middleware, lifespans, static routers, or SPA handlers. |
| `0.26.0` | Single-port proxy and hot-file recovery. | Keep browser HTTP and HMR WebSocket traffic on the Litestar origin. Legacy `VITE_PROXY_MODE=direct` warns and becomes `vite`; it is not a valid constructor mode. Let the bridge and hot file track the internal Vite target. |
| `0.26.0` | Correct Inertia partial and asset-version protocol. | Partial data and partial except filter plain dict props independently; except wins on overlap. Partial responses omit `deferredProps`. Only stale `GET` visits receive `409` plus `X-Inertia-Location`; non-GET submissions continue. |
| `0.26.0` | Infinite-scroll metadata shape. | Read `scrollProps.<propName>`; the protocol emits a record keyed by the returned data prop. |
| `0.26.0` | Type generation hardening. | Production generation failures fail by default; dev-server failures warn. Set `fail_on_error=False` only for deliberate warn-only builds. Generated hey-api output lives under `output/api/`; static bridge types live in `static-props.ts`. |
| `0.26.0` | Transactional, current scaffolds. | Use `assets init --template ...`; framework variants, current hey-api/TanStack/Vite APIs, dependency pins, collision handling, and non-interactive behavior come from the shipped template registry. |
| `0.26.0` | Manifest and deploy fixes. | Resolve `<bundle_dir>/<manifest_name>` first and `.vite/<manifest_name>` second. `assets deploy` recursively detects nested changes. |
| `0.26.1` | Build ordering fix. | `assets build` writes `.litestar.json` before pre-build generators and the JS typegen CLI read it. |
| `0.27.0` | Lifecycle logging cleanup. | Routine start, stop, initialization, health-check success, and type-export success messages are silent. Quiet mode suppresses warnings; non-TTY warnings/errors use Python logging. Missing-manifest messages avoid absolute paths and point to `assets build`. |
| `0.28.0` | Browser stream helpers and the `<litestar-stream>` element. | Zero-dependency WebSocket/SSE helpers cover generic routes, Channels routes, and Litestar Queues routes, with reconnect backoff, heartbeat filtering, and deduplication. For JSON streams prefer them over `htmx-ext-ws` / `htmx-ext-sse` rather than stacking a second reconnect policy. |
| `0.28.0` | Server-neutral production static-provider contract. | Optional native serving on Granian 0.16+ (`GranianPlugin(static="auto")`); Litestar's static route is retained on every other ASGI server. Placement resolves to native or ASGI with a diagnostic reason. |
| `0.28.0` | Hotfile readiness and Vite 8.1 HMR. | The JS plugin writes the hotfile only once the dev server listens, so startup requests fall through to built assets instead of returning `502`. Vite 8.1+ emits network options under `server.ws.*`; Vite 7 / 8.0 keep `server.hmr.*`. |
| `0.29.0` | `mode="external"` is permanent again. | It no longer emits a `DeprecationWarning`. All five aliases normalize silently. |
| `0.29.0` | `InertiaConfig.shared_page_prop_types` and generated `inertia.d.ts`. | Declare types for props pushed via `share()` so guard/middleware props resolve to real generated types instead of a synthesized `AuthData`. The generated `inertia.d.ts` makes `page.flash.success` a `string[]`; `include_default_flash=False` skips it. |
| `0.29.0` | Custom CSRF names reach the browser. | `csrfCookieName` / `csrfHeaderName` ride the `.litestar.json` bridge, so `getCsrfToken()`, `csrfHeaders()`, `csrfFetch()`, and the HTMX extension follow `CSRFConfig(cookie_name=..., header_name=...)`. |
| `0.29.0` | SPA/proxy prefix reservation narrowed. | `/api` and `/schema` are reserved only when real Litestar routes, OpenAPI config, or `RuntimeConfig.extra_route_prefixes` claim them. Add `extra_route_prefixes=("/api",)` if an app relied on the old guessed fallback. |
| `0.29.0` | CSP-safe HTMX JSON-template interpreter. | Assignment, `new`, functions/arrows, computed indexing, array literals, and globals other than `JSON` and `Math` are gone. `@event` exposes a sanitized `$event`. Drop `script-src 'unsafe-eval'` when nothing else needs it. |
| `0.29.0` | **Breaking:** `MissingDependencyError` takes `extra=` in place of `install_package=`. | `extra` names a `litestar-vite` extra and may be omitted. |
| `0.29.0` | **Breaking:** `litestar_vite.commands` and `init_vite()` removed. | Use `litestar_vite.scaffolding` (`TemplateContext` plus `generate_project()`), which is what `litestar assets init` calls. |
| `0.29.0` | Deprecated `materialize_shared_props_to_session()` for removal in `v0.30.0`. | Inertia redirect responses perform the session handoff automatically. |
| `0.29.1` | Hotfile and HMR fixes. | Relative hot-file paths resolve beneath an absolute `bundleDir`. Vite 8.1+ HMR merges only defined values, so explicit overrides and disable flags survive; proxy mode lets Vite infer the browser client port. |
| `0.30.0` | Direct `msgspec.Struct` field-rename preservation in Inertia (#347). | Direct `msgspec.Struct` returns from `component=` handlers encode via `msgspec.to_builtins()` so `rename=` rules (`camel`, `kebab`, `pascal`) and `msgspec.field(name=...)` aliases survive as top-level page props. |
| `0.30.0` | Secondary Vite HTML entry resolution (#348). | Added `ViteAssetLoader.resolve_html_entry(entry, *, production_path, absolute_dev_asset_urls=False)` and `resolve_html_entry_sync(...)`, `HTMLEntryResolutionError`, and `/__litestar__/transform-index` `{ entry }` support for secondary HTML entrypoints. |
| `0.30.1` | Static auth exclusion and Granian static eligibility (#351). | `ViteConfig.exclude_static_from_auth=True` emits `opt={"exclude_from_auth": True}` directly on static route handlers and decouples `VitePlugin.get_static_server_config()` (`StaticServerConfig`, `StaticPlacement`, `StaticServerMount`) for Granian native static serving. |
| `0.31.0` | CSRF constants in `routes.ts` and static helper fallbacks (#354). | `generate_routes_ts` emits `CSRF_COOKIE_NAME` and `CSRF_HEADER_NAME` from `app.csrf_config`. `getCsrfHeaderName`, `getCsrfToken`, `csrfHeaders`, and `csrfFetch` accept `CsrfOptions` / `CsrfFetchOptions` (`headerName`, `cookieName`) when `window.__LITESTAR_CSRF_*__` globals are absent. |
| `0.32.0` | UI component fragments & `<litestar-island>` (#369). | Render React, Vue, Svelte, or Astro fragments from Python via `ComponentResponse(component, props=..., mode="static" \| "island")`, `FragmentEngine`, `render_fragment`, or Jinja `{{ vite_fragment(...) }}`, with scoped CSS chunk extraction from `manifest.json` and `<litestar-island>` client hydration (`getIslandClientScript()` from `litestar-vite-plugin/fragments`). |
| `0.32.0` | Persistent IPC SSR worker, Vite 7+ `ModuleRunner`, and circuit breaker (#369). | `litestar_vite.ipc` provides `StdioIPCTransport` (prod stdin/stdout JSON-RPC worker `litestar-vite-ssr-worker`), `TCPStreamIPCTransport` (dev `/__litestar_ssr__` via `litestarViteSsrPlugin` using Vite 7+ `ModuleRunner`), and `SSRCircuitBreaker` (`CircuitState`). `InertiaSSRConfig` removes legacy HTTP `url`/`auto_start`/`health_check`/`health_check_timeout` fields and adds `fallback_to_client`, `circuit_breaker_enabled`, `circuit_breaker_failure_threshold`, and `circuit_breaker_reset_timeout`. |
| `0.32.0` | AsyncAPI 3.0 & typed channels (#368). | `TypeGenConfig(generate_channels=True)` (default `True`) exports `asyncapi.json` and `channels.ts` (`ChannelMap`) when `AsyncAPIPlugin` (`litestar-asyncapi`, extra `litestar-vite[asyncapi]`) is registered on the Litestar app (removing stale outputs when absent), paired with `createTypedChannels()` in `litestar-vite-plugin/helpers`. |
| `0.32.0` | Single-port AnyIO streaming proxy, Vite `>=7.0.0` floor, & Inertia slot tokens (#369). | Unifies dev mode on the single-port AnyIO byte-streaming proxy (`ViteProxyMiddleware` + `/static/vite-hmr`), enforces Vite `>=7.0.0` peer dependency floor, and supports `<!--inertia-head-->` / `<!--inertia-body-->` slot replacement with fallback to `#app`. |

## Inertia Protocol Boundary

- Initial non-Inertia visits return HTML; Inertia visits return JSON.
- Structured handler returns (`dict`, `msgspec.Struct`, dataclass, Pydantic) become top-level props, preserving `msgspec.Struct` `rename=` and `field(name=...)` rules (`0.30.0+`).
- Initial responses advertise deferred groups.
- Partial responses omit `deferredProps`, including unrequested groups.
- `X-Inertia-Partial-Data` and `X-Inertia-Partial-Except` apply only when the
  partial component matches the route component.
- Asset versions come from the Vite asset loader. A stale `GET` receives a
  protocol refresh response; stale mutation requests keep their method and body.
- Precognition validation requests (`@precognition`, `InertiaConfig.precognition=True`) return 204 No Content with `Precognition-Success: true` (`PrecognitionResponse`) when validation succeeds; validation errors return 422 with formatted errors.

## Scaffolds

`litestar assets init --template <name>` ships React, React Router, React
TanStack, React Inertia, Vue, Vue Inertia, Svelte, Svelte Inertia, SvelteKit,
Nuxt, Astro, HTMX/Jinja, Angular Vite, and Angular CLI families. Inertia Jinja
and SSR variants are separate template names. Use `--no-prompt` for automation
and `--overwrite` only after reviewing collisions.

## Upstream Sources

- `v0.26.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.26.0>
- `v0.26.1`: <https://github.com/litestar-org/litestar-vite/tree/v0.26.1>
- `v0.27.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0>
- `v0.28.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.28.0>
- `v0.29.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.29.0>
- `v0.29.1`: <https://github.com/litestar-org/litestar-vite/tree/v0.29.1>
- `v0.30.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.30.0>
- `v0.30.1`: <https://github.com/litestar-org/litestar-vite/tree/v0.30.1>
- `v0.31.0`: <https://github.com/litestar-org/litestar-vite/tree/v0.31.0>
- Tagged changelog: <https://github.com/litestar-org/litestar-vite/blob/v0.31.0/docs/changelog.rst>
- Tagged configuration: <https://github.com/litestar-org/litestar-vite/tree/v0.31.0/src/py/litestar_vite/config>
- Tagged Inertia tests: <https://github.com/litestar-org/litestar-vite/tree/v0.31.0/src/py/tests/unit/inertia>
- Tagged CLI tests: <https://github.com/litestar-org/litestar-vite/tree/v0.31.0/src/py/tests>
