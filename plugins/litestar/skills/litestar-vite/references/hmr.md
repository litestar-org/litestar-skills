# litestar-vite — HMR Reference

How Hot Module Replacement works between Litestar and Vite, and how to debug it.

## Architecture

```text
Browser ──HTTP──▶ Litestar (port 8000)
   │
   └─WS────────▶ Vite dev server (port 5173)
                  │
                  ├─ watches resource_dir for changes
                  └─ pushes update messages → browser swaps modules
```

In dev mode:

1. `litestar run` starts Vite when `dev_mode=True` and `RuntimeConfig.start_dev_server=True`.
2. `litestar-vite` writes `.litestar.json` so the JS plugin sees the Python config.
3. Vite writes a "hot file" at `ViteConfig.paths.hot_file`.
4. The plugin checks the hot file on each request — present ⇒ dev proxy mode active.
5. `vite()` returns Litestar-proxied dev URLs by default.
6. `vite_hmr()` injects the HMR client `<script>`.
7. Browser opens WS to Vite, gets module updates without page reload.

## React Fast Refresh

React projects get Fast Refresh through the Vite React plugin and HMR client. Keep `vite_hmr()` before the entrypoint tag.

## Common Issues

### Stale prod URLs in dev

Symptom: `vite()` returns production `/static/...` paths instead of dev-server/proxy paths.

Causes:

- `ViteConfig.paths.hot_file` differs from a manually overridden `litestar({ hotFile })`. The plugin can't find the marker.
- Vite isn't actually running — check `litestar run` logs.
- `dev_mode=False` is set explicitly.

Fix: remove the JS-side `hotFile` override or align it with `ViteConfig.paths.hot_file`; verify Vite started.

### CORS errors fetching JS

Symptom: browser console shows `CORS policy: No 'Access-Control-Allow-Origin'`.

Fix: first use the default proxy mode so Litestar is the public origin. In direct/two-port mode, set `server.cors: true`; if using HTTPS, also set `server.origin`.

### Port conflict / random port

Symptom: HMR works some runs, fails others. Asset URLs point at unexpected ports.

Fix: in proxy mode, let Vite auto-pick and read the generated hot-file URL. In direct/two-port mode, pin both `RuntimeConfig.port` (Python) and `server.port` (JS) to the same value.

### HMR works but full reloads happen

Symptom: every edit triggers a full page reload instead of a hot swap.

Causes:

- Component file has a side effect at module top level (timer, fetch, etc.) — Vite invalidates the module.
- React Fast Refresh plugin missing from `vite.config.ts`.
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
- [ ] Browser network tab shows JS fetched through Litestar's proxy in default mode, or from the pinned Vite origin in direct mode
- [ ] `vite_hmr()` rendered to a `<script>` tag in the served HTML
- [ ] Browser console shows `[vite] connected`
- [ ] WebSocket frames appear in network tab on file edit
