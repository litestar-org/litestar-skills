# litestar-vite — Troubleshooting

Common errors and fixes.

## Asset URLs return 404 or 401

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/static/main.tsx` 404 in prod | `manifest.json` missing or wrong path | Run `litestar assets build`; verify `bundle_dir` |
| `/static/*` returns 401/403 under global auth middleware | `exclude_static_from_auth=False` or running pre-`0.30.1` router-level opt | Upgrade to `litestar-vite>=0.30.1` and keep `ViteConfig(exclude_static_from_auth=True)` (sets `opt={"exclude_from_auth": True}` on static handlers) |
| `http://localhost:5173/...` 502 in prod | `dev_mode=True` left on in prod | Env-toggle `dev_mode` from `ENV` var |
| Asset URL points at wrong CDN | `base` / `assetUrl` mismatch | Align `vite.config.ts` `base` with `assetUrl` and `ASSET_URL` env |
| `HTMLEntryResolutionError` on secondary HTML entry | Entry missing from disk in prod or `/__litestar__/transform-index` unreachable in dev | Ensure `production_path` exists in `bundle_dir` after build and Vite dev server is running in dev (`0.30.0+`) |

## HMR Not Working

See `hmr.md` for the full debug checklist. Quick summary:

- Hot file path mismatch between Python and JS configs
- Vite not actually running (check `litestar run` logs)
- A JS-side origin/HMR override bypassing the Litestar proxy
- Missing `vite_hmr()` in template
- Vite 8.1+ config still puts HMR network fields under `server.hmr` instead of `server.ws`

## Type Generation & CSRF Helpers

| Symptom | Cause | Fix |
| --- | --- | --- |
| `routes.ts` empty | Handlers missing `name=` parameter | Add `name=` to handlers; route names come from there |
| `api/types.gen.ts` missing types | DTO not registered with OpenAPI | Ensure handler request/return annotations or DTO configuration exposes the schema |
| `inertia-pages.json` empty | Pages use generic JSON responses | Use `component=` handlers or Inertia response helpers from `litestar_vite.inertia` |
| Custom `CSRFConfig` header/cookie ignored on static pages | `window.__LITESTAR_CSRF_*__` globals absent when SPA HTML injection is skipped | Import `CSRF_COOKIE_NAME` and `CSRF_HEADER_NAME` from generated `routes.ts` (`0.31.0+`) and pass `{ headerName: CSRF_HEADER_NAME, cookieName: CSRF_COOKIE_NAME }` to `csrfFetch` / `csrfHeaders` |
| CI diff after re-gen | Local types out of date | `litestar assets generate-types` then commit |

## Build Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Cannot find module 'litestar-vite-plugin'` | npm package not installed | `npm install -D litestar-vite-plugin` |
| `Rollup failed to resolve import` | `input` path in plugin doesn't match disk | Verify paths; use `path.resolve(__dirname, ...)` for absolute |
| Build outputs to wrong dir | `build.outDir` ≠ `bundleDir` | Both must point at `bundle_dir` |
| `emptyOutDir` warning | `outDir` is outside Vite root | Set `build.emptyOutDir: true` to acknowledge |

## Inertia, SSR, and Fragment Issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| Page renders as JSON, not HTML | `ViteConfig.inertia` missing or route lacks `component=` / Inertia response helper | Add `InertiaConfig(...)` to `ViteConfig`; set `mode="hybrid"` when explicit mode is needed |
| Type errors on page props | `inertia-pages.json` / `page-props.ts` stale | Re-run `litestar assets generate-types` |
| First-load works, navigations break | `root_template` missing Inertia head tags | Use Inertia layout pattern in `base.html` |
| Structured handler return nests under `content` or boots as JSON | Running pre-0.24.1 behavior or bypassing the Inertia wrapper | Upgrade to `litestar-vite>=0.24.1`; return a prop bag from a `component=` handler |
| Direct `msgspec.Struct` return ignores `rename="camel"` or `msgspec.field(name=...)` | Running pre-`0.30.0` `dataclasses.asdict`-style conversion | Upgrade to `litestar-vite>=0.30.0` (#347), which encodes `msgspec.Struct` via `msgspec.to_builtins()` |
| Deferred metadata appears on a partial response | Running behavior older than `0.26.0` | Upgrade; partial responses omit all `deferredProps` metadata |
| Mutation request becomes a 409 refresh | Running behavior older than `0.26.0` | Upgrade; version mismatch short-circuits stale `GET` visits only |
| SSR or `ComponentResponse` / `vite_fragment` fails in dev (`0.32.0+`) | `litestarViteSsrPlugin` or `server.environments.ssr` missing in Vite 7+ | Register `litestarViteSsrPlugin()` from `litestar-vite-plugin/dev-ssr` or enable `InertiaSSRConfig(fallback_to_client=True, circuit_breaker_enabled=True)` |

## SPA Catch-All Issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| Non-root `spa_path` such as `/ui` returns `Not an SPA route` | SPA handler's own route is treated as a non-SPA Litestar route in pre-0.24.0 versions | Upgrade to `litestar-vite>=0.24.0`; keep real API routes registered normally |
| API routes return SPA HTML | Catch-all SPA route is too broad or registered before explicit routes | Register explicit API routes and let SPA fallback serve only non-Litestar paths |

## Performance

| Symptom | Cause | Fix |
| --- | --- | --- |
| Slow dev startup | Pre-bundling too many deps | Use `optimizeDeps.include` to pin |
| Slow build | Missing `autoCodeSplitting` | Enable in router plugin (TanStack/etc.) |
| Large bundle | Unused imports / barrel files | Audit with `rollup-plugin-visualizer` |

## When in Doubt

```bash
litestar --app app:app assets doctor --runtime-checks
```

Reports configuration drift, manifest status, hot-file presence, and runtime reachability. Use `litestar --app app:app assets status` for read-only status output.

Missing manifests are intentionally quiet during configuration. If an asset is
requested without a usable manifest, run `litestar assets build`; current errors
do not expose absolute manifest paths.
