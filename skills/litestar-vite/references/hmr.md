# litestar-vite — HMR Reference

How Hot Module Replacement works between Litestar and Vite, and how to debug it.

## Architecture

```text
Browser ──HTTP──▶ Litestar (port 8000)
   │                 │
   └─WS──────────────┤ proxy using hot-file target
                     ▼
                  Vite (internal port)
                     │
                     ├─ watches resource_dir
                     └─ pushes updates through Litestar
```

In dev mode:

1. `litestar run` starts Vite when `dev_mode=True` and `RuntimeConfig.start_dev_server=True`.
2. `litestar-vite` writes `.litestar.json` so the JS plugin sees the Python config.
3. Vite writes a "hot file" at `ViteConfig.paths.hot_file`.
4. The plugin checks the hot file on each request — present ⇒ dev proxy mode active.
5. `vite()` returns URLs on the Litestar public origin.
6. `vite_hmr()` injects the HMR client `<script>`.
7. The browser opens the HMR WebSocket against Litestar; Litestar proxies it
   to Vite.

This single-port ASGI contract is the supported development path. Legacy
`VITE_PROXY_MODE=direct` warns and becomes `"vite"`; `"direct"` is not a valid
`RuntimeConfig.proxy_mode`.

## React Fast Refresh

React projects get Fast Refresh through the Vite React plugin and HMR client. Keep `vite_hmr()` before the entrypoint tag.

## Vite 8.1+ HMR Config Shape

Vite 8.1 moved HMR network options from `server.hmr.*` to `server.ws.*`.

Use this shape only when you must override the network settings explicitly:

```ts
export default defineConfig({
  server: {
    ws: {
      host: "localhost",
      path: "vite-hmr",
      clientPort: 8000,
      protocol: "ws",
    },
  },
})
```

Rules:

- Vite 8.1+: place `host`, `port`, `clientPort`, `path`, `protocol`, and `timeout` under `server.ws`.
- Vite 7 / 8.0: place those fields under `server.hmr`.
- Disabling HMR remains `server.hmr = false`.
- In proxy mode, omit explicit HMR network settings unless the default bridge-derived values are wrong.

## Common Issues

### Stale prod URLs in dev

Symptom: `vite()` returns production `/static/...` paths instead of dev-server/proxy paths.

Causes:

- `ViteConfig.paths.hot_file` differs from a manually overridden `litestar({ hotFile })`. The plugin can't find the marker.
- Vite isn't actually running — check `litestar run` logs.
- `dev_mode=False` is set explicitly.

Fix: remove the JS-side `hotFile` override or align it with `ViteConfig.paths.hot_file`; verify Vite started.

### Port conflict / random port

Symptom: HMR works some runs and fails after Vite restarts.

Fix: remove public-origin overrides. The proxy re-reads the hot file by mtime and
recovers when the file is replaced or temporarily missing.

### Vite 8.1 HMR deprecation warning

Symptom: Vite logs that `server.hmr.*` network options are deprecated.

Fix: move HMR network options to `server.ws` when running Vite 8.1+. If the project must support Vite 7 or 8.0 from the same `vite.config.ts`, avoid explicit HMR network config and let `litestar-vite-plugin` emit the version-gated shape.

### HMR works but full reloads happen

Symptom: every edit triggers a full page reload instead of a hot swap.

Causes:

- Component file has a side effect at module top level (timer, fetch, etc.) — Vite invalidates the module.
- React Fast Refresh plugin missing from `vite.config.ts`.
- Non-React framework: HMR boundary not declared in the changed module (`import.meta.hot`).

### WebSocket connection fails

Symptom: the browser connects directly to the Vite port or the WebSocket fails.

Causes:

- Vite isn't running.
- A user-defined `server.origin`, `server.hmr`, or `server.ws` override bypasses
  the bridge-derived Litestar route.

Fix: remove explicit network overrides. The npm plugin sets the HMR client port
to the Litestar port and routes it under the asset URL.

### Browser caches manifest.json

Symptom: deploys ship new bundles but browsers load old ones.

Fix: never set long TTL on `manifest.json`. Hash the bundles (Vite default), but treat the manifest as no-cache.

## Debugging Checklist

- [ ] Load the Litestar URL, not the internal Vite URL
- [ ] `hot_file` exists at the configured path during a dev session
- [ ] Browser network tab shows JS and HMR WebSocket traffic on the Litestar origin
- [ ] `vite_hmr()` rendered to a `<script>` tag in the served HTML
- [ ] Vite 8.1+ configs use `server.ws` for HMR network fields
- [ ] Browser console shows `[vite] connected`
- [ ] WebSocket frames appear in network tab on file edit
