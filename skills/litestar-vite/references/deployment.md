# litestar-vite — Deployment Reference

Production build, static hosting, and CDN patterns.

## Production Build

```bash
litestar assets build
```

Outputs (under `bundle_dir`):

```text
manifest.json                    URL → hashed-asset map
assets/main.<hash>.js            hashed JS bundles
assets/main.<hash>.css           hashed CSS bundles
<files from publicDir>           copied verbatim
```

## Production Toggles

```python
ViteConfig(
    dev_mode=False,                   # CRITICAL — env-toggled
    use_server_lifespan=False,        # no Vite child process
    ...
)
```

In production:

- `vite_asset()` reads `manifest.json` once at startup (or on each call if `use_asset_linker=True`)
- `vite_hmr_client()` and `vite_react_refresh()` become no-ops
- No proxy to Vite dev server

## Static Hosting Options

### Litestar serves static (small/medium apps)

```python
from litestar.static_files import create_static_files_router

app = Litestar(
    route_handlers=[
        ...,
        create_static_files_router(path="/static", directories=["public"]),
    ],
    plugins=[VitePlugin(config=vite_config)],
)
```

Granian handles static asset serving acceptably for moderate traffic.

### Reverse proxy (nginx, Caddy, Cloudflare)

Mount `bundle_dir` as a static volume; reverse proxy serves `/static/*` directly without hitting Litestar. Best for high-traffic apps.

### CDN (CloudFront, Cloudflare, Fastly)

Push `bundle_dir/` to the CDN as part of CI. Set `base` / `assetUrl` to the CDN URL:

```ts
// vite.config.ts
export default defineConfig({
  base: process.env.ASSET_URL ?? "/static/",   // CDN URL in prod
  ...
})
```

Set `ASSET_URL=https://cdn.example.com/assets/v123/` at deploy time.

## Cache Strategy

| Asset | Cache TTL | Why |
| --- | --- | --- |
| `assets/*.js`, `assets/*.css` (hashed) | `max-age=31536000, immutable` | Hashed names → safe to cache forever |
| `manifest.json` | `no-cache` | Must reflect latest deploy |
| `index.html` (template mode) | `no-cache` | References hashed assets via manifest |
| `public/*` (favicon, images) | `max-age=86400` | Stable but might change |

## CI Pipeline

```yaml
# Example (GitHub Actions)
- name: Install JS deps
  run: npm ci

- name: Generate types
  run: litestar --app app:app assets generate-types

- name: Verify types are committed
  run: git diff --exit-code src/generated

- name: Build assets
  run: litestar --app app:app assets build

- name: Push to CDN
  env:
    ASSET_URL: https://cdn.example.com/assets/${{ github.sha }}/
  run: ./scripts/upload-to-cdn.sh public/
```

## Multi-Region / Edge

For edge deployments (Cloudflare Workers, Vercel Edge):

- Build assets in CI
- Push to edge KV or R2
- Set `ASSET_URL` to the edge URL
- Litestar runs in origin region; assets served from edge
- `manifest.json` deployed alongside Litestar (in origin) so URL resolution is consistent

## Rollback

Because assets are hashed, old versions remain valid as long as they're still hosted. To roll back:

1. Deploy old Litestar code (which references old `manifest.json`).
2. Old hashed assets must still be reachable on CDN — never purge by hash.
3. Set `ASSET_URL` to the old version dir if using versioned dirs.

## Pitfalls

- **Forgetting `dev_mode=False` in prod** — proxies to a non-existent Vite server, all asset URLs 502.
- **`manifest.json` cached too long** — new deploys reference hashed files, but old manifest still served, so browsers fetch wrong filenames.
- **Purging old hashed assets** — breaks rollbacks and clients with stale tabs.
- **Mismatched `base` in dev vs prod** — prefer always reading from `process.env.ASSET_URL` with a sensible default.
