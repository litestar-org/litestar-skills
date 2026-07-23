# litestar-vite — TypeGen Reference

End-to-end type generation from the Litestar backend to TypeScript.

## What Gets Generated

| Output | Source | Purpose |
| --- | --- | --- |
| `openapi.json` | Litestar OpenAPI schema | Source of truth for SDK + schemas |
| `routes.json` | Route metadata | JSON consumed by `litestar-vite-plugin` |
| `routes.ts` | Route registry | Typed URL builder: `route("name", { params })` |
| `api/` | Litestar OpenAPI schema | hey-api `types.gen.ts`, schemas, SDK functions, and fetch client |
| `schemas.ts` | Route metadata plus hey-api types | `FormInput`, `FormResponse`, and `SuccessResponse` route helpers |
| `inertia-pages.json` | Inertia handler metadata | JSON consumed by `litestar-vite-plugin` |
| `page-props.ts` | Inertia page-prop types | Typed props for Inertia page components |
| `static-props.ts` | `.litestar.json` `staticProps` | Typed default and named exports for static bridge values |

## Configuration

```python
from litestar_vite import TypeGenConfig

TypeGenConfig(
    generate_zod=False,
    generate_sdk=True,
    generate_routes=True,
    generate_schemas=True,
    generate_page_props=True,    # Inertia only
    fail_on_error=None,          # fail builds, warn in dev
    output="src/generated",
)
```

## CLI

```bash
litestar assets generate-types     # generate everything enabled
litestar assets export-routes      # routes.json metadata
litestar assets export-routes --typescript  # routes.ts only
```

The Python pipeline first exports metadata, then runs `extra_commands`, then
invokes the JS generator. Release `0.26.1` writes `.litestar.json` before those
generators read it.

## Frontend Use

### Routes

```ts
import { route } from "@/generated/routes"

const url = route("users:get", { id: 123 })
// → "/api/users/123"
```

Route names come from Litestar handler `name=` parameters.

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

## CI Integration

Generated files should either be:

1. **Committed and verified in CI**: regenerate in CI and `git diff --exit-code`. If diff, fail.
2. **Generated in CI before build**: not committed; CI runs `litestar assets generate-types` before `npm run build`.

Pattern (1) is preferred — diffs surface in PR review.

## Triggers

| Change | Re-trigger needed |
| --- | --- |
| Add/change a route handler | yes (`routes.json` and `routes.ts`) |
| Add/change a Pydantic / msgspec DTO | yes (`schemas.ts`) |
| Change Inertia handler / page name | yes (`inertia-pages.json` and `page-props.ts`) |
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
