# litestar-vite - Release Updates 0.26.0 to 0.27.0

This guidance is audited against immutable tag `v0.27.0`, commit
`bc9e15770bf82cf0a63f40129aea262075361ef5`.

## Release Anchors

| Version | Upstream change | Skill guidance |
| --- | --- | --- |
| `0.26.0` | Four canonical modes with normalized aliases. | Use `spa`, `template`, `hybrid`, or `framework`. Treat `htmx`, `inertia`, `ssr`, and `ssg` as aliases. Replace deprecated `external` with `framework` plus `ExternalDevServer`. |
| `0.26.0` | `ViteConfig.enabled` and `VITE_ENABLED`. | Set `enabled=False` for CLI, worker, and test processes that need config access without runtime routes, middleware, lifespans, static routers, or SPA handlers. |
| `0.26.0` | Single-port proxy and hot-file recovery. | Keep browser HTTP and HMR WebSocket traffic on the Litestar origin. Legacy `VITE_PROXY_MODE=direct` warns and becomes `vite`; it is not a valid constructor mode. Let the bridge and hot file track the internal Vite target. |
| `0.26.0` | Correct Inertia partial and asset-version protocol. | Partial data and partial except filter plain dict props independently; except wins on overlap. Partial responses omit `deferredProps`. Only stale `GET` visits receive `409` plus `X-Inertia-Location`; non-GET submissions continue. |
| `0.26.0` | Infinite-scroll metadata shape. | Read `scrollProps.<propName>`; the protocol emits a record keyed by the returned data prop. |
| `0.26.0` | Type generation hardening. | Production generation failures fail by default; dev-server failures warn. Set `fail_on_error=False` only for deliberate warn-only builds. Generated hey-api output lives under `output/api/`; static bridge types live in `static-props.ts`. |
| `0.26.0` | Transactional, current scaffolds. | Use `assets init --template ...`; framework variants, current hey-api/TanStack/Vite APIs, dependency pins, collision handling, and non-interactive behavior come from the shipped template registry. |
| `0.26.0` | Manifest and deploy fixes. | Resolve `<bundle_dir>/<manifest_name>` first and `.vite/<manifest_name>` second. `assets deploy` recursively detects nested changes. |
| `0.26.1` | Build ordering fix. | `assets build` writes `.litestar.json` before pre-build generators and the JS typegen CLI read it. |
| `0.27.0` | Lifecycle logging cleanup. | Routine start, stop, initialization, health-check success, and type-export success messages are silent. Quiet mode suppresses warnings; non-TTY warnings/errors use Python logging. Missing-manifest messages avoid absolute paths and point to `assets build`. |

## Inertia Protocol Boundary

- Initial non-Inertia visits return HTML; Inertia visits return JSON.
- Structured handler returns become top-level props.
- Initial responses advertise deferred groups.
- Partial responses omit `deferredProps`, including unrequested groups.
- `X-Inertia-Partial-Data` and `X-Inertia-Partial-Except` apply only when the
  partial component matches the route component.
- Asset versions come from the Vite asset loader. A stale `GET` receives a
  protocol refresh response; stale mutation requests keep their method and body.

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
- Tagged changelog: <https://github.com/litestar-org/litestar-vite/blob/v0.27.0/docs/changelog.rst>
- Tagged configuration: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/litestar_vite/config>
- Tagged Inertia tests: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/tests/unit/inertia>
- Tagged CLI tests: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/tests>
