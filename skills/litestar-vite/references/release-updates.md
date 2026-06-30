# litestar-vite - Release Updates 0.24.0 to 0.25.0

Use this file when refreshing guidance against current upstream `litestar-vite` releases.

## Release Anchors

| Version | Upstream change | Skill guidance |
| --- | --- | --- |
| `0.24.0` | SPA handler excludes its own routes from Litestar route-prefix detection. | Non-root `spa_path` values such as `/ui` remain reachable while real backend routes still win. If `/ui/...` fails with `Not an SPA route`, upgrade before adding local workarounds. |
| `0.24.0` | Deferred Inertia props strip resolved keys from `deferredProps` on partial reload. | Initial responses still advertise deferred metadata. Partial reload responses remove only keys they resolved; unrequested deferred props remain advertised. |
| `0.24.0` | Litestar 3 deprecation prep and Inertia integration cleanup. | Use `litestar.plugins.jinja.JinjaTemplateEngine` in examples. Keep `litestar-vite-plugin` as the Litestar bridge owner; do not add `@inertiajs/vite` to generated scaffolds by default. |
| `0.24.1` | Structured Inertia handler returns bootstrap as HTML props. | `dict`, `msgspec.Struct`, dataclass, and Pydantic model returns are prop bags. Initial visits return HTML; Inertia visits spread fields as top-level props. |
| `0.25.0` | Vite 8.1 HMR `server.ws.*` deprecation fix. | Vite 8.1+ HMR network fields belong under `server.ws`; Vite 7 / 8.0 use `server.hmr`; `server.hmr=false` still disables HMR. |

## Vite 8.1 HMR Shape

Prefer no explicit HMR network override in proxy mode. Let `litestar-vite-plugin` emit the version-gated shape from the `.litestar.json` bridge.

When an override is required on Vite 8.1+:

```ts
export default defineConfig({
  server: {
    ws: {
      host: "localhost",
      path: "vite-hmr",
      clientPort: 8000,
    },
  },
})
```

Do not place `host`, `port`, `clientPort`, `path`, `protocol`, or `timeout` under `server.hmr` on Vite 8.1+. Use that legacy shape only for Vite 7 or 8.0.

## Inertia Behavior

- Treat `dict`, `msgspec.Struct`, dataclass, and Pydantic model handler returns as shallow prop bags.
- Initial non-Inertia visits return HTML bootstrap responses.
- Inertia visits (`X-Inertia: true`) return JSON with fields as top-level props.
- Deferred props are advertised on initial responses.
- A partial reload that resolves a deferred prop removes that key from `deferredProps`; it does not remove unrelated deferred keys.
- Keep `litestar-vite-plugin` responsible for the bridge, dev/prod asset resolution, proxy routing, type generation, CSRF helper wiring, and `resolvePageComponent()`.

## Upstream Sources

- `v0.24.0` release: <https://github.com/litestar-org/litestar-vite/releases/tag/v0.24.0>
- `v0.24.1` release: <https://github.com/litestar-org/litestar-vite/releases/tag/v0.24.1>
- `v0.25.0` release: <https://github.com/litestar-org/litestar-vite/releases/tag/v0.25.0>
- SPA route exclusion: <https://github.com/litestar-org/litestar-vite/pull/264>
- Deferred props partial reload fix: <https://github.com/litestar-org/litestar-vite/pull/265>
- Litestar 3 and Inertia integration prep: <https://github.com/litestar-org/litestar-vite/pull/269>
- Structured Inertia bootstrap returns: <https://github.com/litestar-org/litestar-vite/pull/277>
- Vite 8.1 HMR shape: <https://github.com/litestar-org/litestar-vite/pull/293>
- Vite server options: <https://vite.dev/config/server-options>
