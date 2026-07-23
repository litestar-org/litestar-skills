# litestar-vite — Deployment Reference

Production build, static hosting, and CDN patterns.

## Production Build

```bash
litestar assets update          # refresh within package.json ranges, when intended
litestar assets update --latest # deliberately ignore ranges
litestar assets build
```

Outputs (under `bundle_dir`):

```text
manifest.json or .vite/manifest.json
                                 URL → hashed-asset map
assets/main.<hash>.js            hashed JS bundles
assets/main.<hash>.css           hashed CSS bundles
<files from publicDir>           copied verbatim
```

## Production Toggles

```python
ViteConfig(
    dev_mode=False,                   # CRITICAL — env-toggled
    runtime=RuntimeConfig(start_dev_server=False),
    ...
)
```

In production:

- `vite()` resolves URLs from `manifest.json`
- `vite_hmr()` becomes a no-op
- No proxy to Vite dev server

Manifest resolution checks `<bundle_dir>/<manifest_name>` first and then
`<bundle_dir>/.vite/<manifest_name>`. Keep the manifest beside the Litestar
runtime even when a CDN serves the hashed assets.

## Static Hosting Options

### Litestar serves static (small/medium apps)

```python
from litestar_vite import RuntimeConfig, ViteConfig, VitePlugin

vite_config = ViteConfig(
    runtime=RuntimeConfig(set_static_folders=True),
    dev_mode=False,
)

app = Litestar(plugins=[VitePlugin(config=vite_config)])
```

The plugin registers production static routing from `PathConfig`.

### Reverse proxy (nginx, Caddy, Cloudflare)

Mount `bundle_dir` as a static volume; reverse proxy serves `/static/*` directly without hitting Litestar. Best for high-traffic apps.

### CDN (CloudFront, Cloudflare, Fastly)

Use the built-in fsspec deployer when the target has an fsspec backend:

```python
from litestar_vite import DeployConfig, ViteConfig

vite_config = ViteConfig(
    deploy=DeployConfig(
        storage_backend="s3://my-bucket/assets",
        asset_url="https://cdn.example.com/assets/",
        delete_orphaned=True,
        include_manifest=True,
    )
)
```

Install the provider separately (`s3fs`, `gcsfs`, or `adlfs`), then preview and
apply:

```bash
litestar assets deploy --dry-run
litestar assets deploy
```

The command builds first, recursively compares nested bundle assets, uploads
changed files, and removes remote orphans when `delete_orphaned=True`. Use
`--no-build` only for an already verified bundle and `--no-delete` for
additive-only rollout.

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
  run: litestar --app app:app assets install

- name: Generate types
  run: litestar --app app:app assets generate-types

- name: Verify types are committed
  run: git diff --exit-code src/generated

- name: Build assets
  run: litestar --app app:app assets build

- name: Preview CDN sync
  run: litestar --app app:app assets deploy --no-build --dry-run

- name: Deploy CDN assets
  run: litestar --app app:app assets deploy --no-build
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

- **Forgetting `dev_mode=False` in prod** — proxies to a non-existent Vite server.
- **`manifest.json` cached too long** — new deploys reference hashed files, but old manifest still served, so browsers fetch wrong filenames.
- **Purging old hashed assets** — breaks rollbacks and clients with stale tabs.
- **Mismatched `base` in dev vs prod** — prefer always reading from `process.env.ASSET_URL` with a sensible default.
- **Deploying without a dry run** — remote orphan deletion may remove assets
  still referenced by another release. Review `assets deploy --dry-run` first.
