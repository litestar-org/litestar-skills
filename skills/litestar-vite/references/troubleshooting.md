# litestar-vite — Troubleshooting

Common errors and fixes.

## Asset URLs return 404

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/static/main.tsx` 404 in prod | `manifest.json` missing or wrong path | Run `litestar assets build`; verify `bundle_dir` |
| `http://localhost:5173/...` 502 in prod | `dev_mode=True` left on in prod | Env-toggle `dev_mode` from `ENV` var |
| Asset URL points at wrong CDN | `base` / `assetUrl` mismatch | Align `vite.config.ts` `base` with `assetUrl` and `ASSET_URL` env |

## HMR Not Working

See `hmr.md` for the full debug checklist. Quick summary:

- Hot file path mismatch between Python and JS configs
- Vite not actually running (check `litestar run` logs)
- CORS / port mismatch
- Missing `vite_hmr_client()` in template

## Type Generation Fails

| Symptom | Cause | Fix |
| --- | --- | --- |
| `routes.ts` empty | Handlers missing `name=` parameter | Add `name=` to handlers; route names come from there |
| `schemas.ts` missing types | DTO not registered with OpenAPI | Ensure handler return type or `dto=` parameter exposes the schema |
| `inertia-pages.json` empty | Pages use generic JSON responses | Use Inertia response helpers from `litestar_vite.inertia` |
| CI diff after re-gen | Local types out of date | `litestar assets generate-types` then commit |

## Build Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Cannot find module 'litestar-vite-plugin'` | npm package not installed | `npm install -D litestar-vite-plugin` |
| `Rollup failed to resolve import` | `input` path in plugin doesn't match disk | Verify paths; use `path.resolve(__dirname, ...)` for absolute |
| Build outputs to wrong dir | `build.outDir` ≠ `bundleDir` | Both must point at `bundle_dir` |
| `emptyOutDir` warning | `outDir` is outside Vite root | Set `build.emptyOutDir: true` to acknowledge |

## Inertia Issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| Page renders as JSON, not HTML | Missing `InertiaPlugin` or `mode != "hybrid"` | Add `InertiaPlugin`; set `mode="hybrid"` |
| Type errors on page props | `inertia-pages.json` stale | Re-run `litestar assets generate-types` |
| First-load works, navigations break | `root_template` missing Inertia head tags | Use Inertia layout pattern in `base.html` |

## Performance

| Symptom | Cause | Fix |
| --- | --- | --- |
| Slow dev startup | Pre-bundling too many deps | Use `optimizeDeps.include` to pin |
| Slow build | Missing `autoCodeSplitting` | Enable in router plugin (TanStack/etc.) |
| Large bundle | Unused imports / barrel files | Audit with `rollup-plugin-visualizer` |

## When in Doubt

```bash
litestar --app app:app assets status
```

Reports current mode, paths, manifest status, hot-file presence.
