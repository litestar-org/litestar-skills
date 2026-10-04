# litestar-vite — TypeGen Reference

End-to-end type generation from the Litestar backend to TypeScript.

## What Gets Generated

| Output | Source | Purpose |
| --- | --- | --- |
| `openapi.json` | Litestar OpenAPI schema | Source of truth for SDK + schemas |
| `routes.json` | Route metadata | JSON consumed by `litestar-vite-plugin` |
| `routes.ts` | Route registry + `app.csrf_config` | Typed URL builder (`route("name", { params })`) + `CSRF_COOKIE_NAME` and `CSRF_HEADER_NAME` constants (`0.31.0+`) |
| `api/` | Litestar OpenAPI schema | hey-api `types.gen.ts`, schemas, SDK functions, and fetch client |
| `schemas.ts` | Route metadata plus hey-api types | `FormInput`, `FormResponse`, and `SuccessResponse` route helpers |
| `inertia-pages.json` | Inertia handler metadata | JSON consumed by `litestar-vite-plugin` |
| `page-props.ts` | Inertia page-prop types | Typed props for Inertia page components |
| `static-props.ts` | `.litestar.json` `staticProps` | Typed default and named exports for static bridge values (`virtual:litestar-static-props`) |
| `asyncapi.json` | `AsyncAPIPlugin` (`litestar-asyncapi`) + Channels / WebSocket / SSE routes (`0.32.0+`) | AsyncAPI 3.0.0 specification when `AsyncAPIPlugin` is registered and `generate_channels=True` |
| `channels.ts` | `asyncapi.json` (`0.32.0+`) | Typed `ChannelMap` consumed by `createTypedChannels()` |

## Configuration

```python
from litestar_vite import TypeGenConfig

TypeGenConfig(
    generate_zod=False,
    generate_sdk=True,
    generate_routes=True,
    generate_schemas=True,
    generate_page_props=True,
    generate_channels=True,
    global_route=False,
    fail_on_error=None,
    output="src/generated",
)
```

In `0.32.0+`, `generate_channels=True` is enabled by default and exports `asyncapi.json` and `channels.ts` whenever `AsyncAPIPlugin` (`from litestar_asyncapi import AsyncAPIPlugin`, install via `litestar-vite[asyncapi]`) is registered on the `Litestar` app (removing stale outputs when the plugin is absent):

```python
from litestar_vite import TypeGenConfig

TypeGenConfig(
    output="src/generated",
    generate_channels=True,
    asyncapi_path="src/generated/asyncapi.json",
    channels_ts_path="src/generated/channels.ts",
)
```

## CLI

```bash
litestar assets generate-types              # generate everything enabled
litestar assets export-routes               # routes.json metadata
litestar assets export-routes --only users,posts --except admin
litestar assets export-routes --typescript  # routes.ts only
```

The Python pipeline first writes `.litestar.json`, exports metadata (`openapi.json`, `routes.json`, `routes.ts`, `inertia-pages.json`, and `asyncapi.json` when enabled), runs `extra_commands` (resolved via the configured JS executor in `node_modules/.bin` or `npx`/`bunx`/`pnpm dlx`/`yarn dlx`/`deno run`), and finally invokes `litestar-vite-typegen`.

## Frontend Use

### Routes & CSRF Constants (`0.31.0+`)

When `app.csrf_config` is configured on the Litestar app, `routes.ts` exports `CSRF_COOKIE_NAME` and `CSRF_HEADER_NAME` (empty strings when CSRF is disabled). Pass them as static fallbacks when `window.__LITESTAR_CSRF_*__` globals are not injected:

```ts
import { CSRF_COOKIE_NAME, CSRF_HEADER_NAME, route } from "@/generated/routes"
import { csrfFetch, csrfHeaders, getCsrfHeaderName, getCsrfToken } from "litestar-vite-plugin/helpers"

const url = route("users:get", { id: 123 })
// → "/api/users/123"

const token = getCsrfToken({ cookieName: CSRF_COOKIE_NAME })
const header = getCsrfHeaderName(CSRF_HEADER_NAME)
const headers = csrfHeaders({ "Content-Type": "application/json" }, { headerName: CSRF_HEADER_NAME, cookieName: CSRF_COOKIE_NAME })
await csrfFetch(url, { method: "POST", headers })
```

Route names come from Litestar handler `name=` parameters. Set `TypeGenConfig(global_route=True)` if you also want `window.route` registered globally.

### OpenAPI Types and SDK

```ts
import type { User } from "@/generated/api"
import { listUsers } from "@/generated/api"

const response = await listUsers()
```

### Route Request and Response Helpers

```ts
import type {
  FormInput,
  FormResponse,
  SuccessResponse,
} from "@/generated/schemas"

type LoginInput = FormInput<"auth:login">
type LoginCreated = SuccessResponse<"auth:login">
type LoginBadRequest = FormResponse<"auth:login", 400>
```

### Typed Realtime Channels (`0.32.0+`)

When `generate_channels=True`, `channels.ts` exports a `ChannelMap` interface derived from `ChannelsPlugin`, `@websocket`, `websocket_listener`, and `ServerSentEvent` routes:

```ts
import { createTypedChannels } from "litestar-vite-plugin/helpers"
import type { ChannelMap } from "@/generated/channels"

const channels = createTypedChannels<ChannelMap>({ basePath: "/ws" })
const stream = channels.stream("notifications", {
  onEvent: (event) => console.log(event),
})
stream.connect()
```

## CI Integration

Generated files should either be:

1. **Committed and verified in CI**: regenerate in CI and `git diff --exit-code`. If diff, fail.
2. **Generated in CI before build**: not committed; CI runs `litestar assets generate-types` before `npm run build`.

Pattern (1) is preferred — diffs surface in PR review.

## Triggers

| Change | Re-trigger needed |
| --- | --- |
| Add/change a route handler or `CSRFConfig` | yes (`routes.json` and `routes.ts`) |
| Add/change a Pydantic / msgspec DTO | yes (`openapi.json`, `api/`, and `schemas.ts`) |
| Change Inertia handler / page name | yes (`inertia-pages.json` and `page-props.ts`) |
| Add/change `ChannelsPlugin`, WebSocket, or SSE route (`0.32.0+`) | yes (`asyncapi.json` and `channels.ts`) |
| Refactor internal modules | no (if no API surface change) |

## Pitfalls

- **Out-of-date types ⇒ runtime errors**. Always regenerate before `npm run build` in CI.
- **Frontend imports stale generated/**. Add `.gitignore` if generating in CI; otherwise commit and verify.
- **Inertia page-prop generation requires page handlers to use `component=` or Inertia response helpers** — generic JSON handlers won't appear in `inertia-pages.json`.
- **Generation failure semantics differ by command**. Production builds fail by
  default; dev-server generation warns. Set `fail_on_error=False` only when a
  warn-only production build is intentional.
- **hey-api owns `output/api/`**. Do not place handwritten files there because
  `@hey-api/openapi-ts` clears its output directory.
