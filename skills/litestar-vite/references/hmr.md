# litestar-vite — HMR Reference

How Hot Module Replacement works between Litestar and Vite, and how to debug it.

## Architecture

```
Browser ──HTTP──▶ Litestar (port 8000)
   │
   └─WS────────▶ Vite dev server (port 5173)
                  │
                  ├─ watches resource_dir for changes
                  └─ pushes update messages → browser swaps modules
```

In dev mode:

1. `litestar run` (with `use_server_lifespan=True`) starts Vite as a child process.
2. Vite writes a "hot file" at the path `ViteConfig.hot_file` (and `vite.config.ts` `hotFile`).
3. The plugin checks the hot file on each request — present ⇒ proxy mode active.
4. `vite_asset()` returns dev URLs (`http://localhost:5173/...`).
5. `vite_hmr_client()` injects the HMR client `<script>`.
6. Browser opens WS to Vite, gets module updates without page reload.

## React Fast Refresh

For React projects, also inject:

```html
{{ vite_react_refresh() }}
```

before any user JS. This installs the React refresh runtime so component state is preserved on edit.

## Common Issues

### Stale prod URLs in dev

Symptom: `vite_asset()` returns `/static/...` paths instead of `http://localhost:5173/...`.

Causes:

- `ViteConfig.hot_file` path differs from `vite.config.ts` `hotFile`. The plugin can't find the marker.
- Vite isn't actually running — check `litestar run` logs.
- `dev_mode=False` is set explicitly.

Fix: align both `hot_file` paths; verify Vite started.

### CORS errors fetching JS

Symptom: browser console shows `CORS policy: No 'Access-Control-Allow-Origin'`.

Fix: set `server.cors: true` in `vite.config.ts`. If using HTTPS, also set `server.origin`.

### Port conflict / random port

Symptom: HMR works some runs, fails others. Asset URLs point at unexpected ports.

Fix: pin both `RuntimeConfig.port` (Python) and `server.port` (JS) to the same value. Don't let Vite auto-pick.

### HMR works but full reloads happen

Symptom: every edit triggers a full page reload instead of a hot swap.

Causes:

- Component file has a side effect at module top level (timer, fetch, etc.) — Vite invalidates the module.
- React Fast Refresh preamble missing — `vite_react_refresh()` not in template.
- Non-React framework: HMR boundary not declared in the changed module (`import.meta.hot`).

### WebSocket connection fails

Symptom: console shows `WebSocket connection to 'ws://localhost:5173/...' failed`.

Causes:

- Vite isn't running.
- Host mismatch — `RuntimeConfig.host="localhost"` but accessed via `127.0.0.1` (browsers treat as different origins for WS).

Fix: align host across both configs and access URL.

### Browser caches manifest.json

Symptom: deploys ship new bundles but browsers load old ones.

Fix: never set long TTL on `manifest.json`. Hash the bundles (Vite default), but treat the manifest as no-cache.

## Debugging Checklist

- [ ] `litestar run` logs show `Vite serving at http://localhost:<port>`
- [ ] `hot_file` exists at the configured path during a dev session
- [ ] Browser network tab shows JS fetched from `localhost:5173`, not `/static/`
- [ ] `vite_hmr_client()` rendered to a `<script>` tag in the served HTML
- [ ] (React) `vite_react_refresh()` rendered before any React import
- [ ] Browser console shows `[vite] connected`
- [ ] WebSocket frames appear in network tab on file edit
