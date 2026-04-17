# litestar-vite — TypeGen Reference

End-to-end type generation from the Litestar backend to TypeScript.

## What Gets Generated

| Output | Source | Purpose |
|---|---|---|
| `openapi.json` | Litestar OpenAPI schema | Source of truth for SDK + schemas |
| `routes.ts` | Route registry | Typed URL builder: `route("name", { params })` |
| `schemas.ts` | Pydantic / msgspec DTOs | Typed models: `components["schemas"]["User"]` |
| `inertia-pages.json` | Inertia handlers | Page-prop typing for Inertia adapters |

## Configuration

```python
from litestar_vite import TypeGenConfig

TypeGenConfig(
    enabled=True,
    generate_sdk=True,
    generate_routes=True,
    generate_schemas=True,
    generate_page_props=True,    # Inertia only
    output="src/generated",
)
```

## CLI

```bash
litestar assets generate-types     # generate everything enabled
litestar assets export-routes      # routes.ts only
```

When `use_server_lifespan=True` and `dev_mode=True`, types regenerate on startup.

## Frontend Use

### Routes

```ts
import { route } from "@/generated/routes"

const url = route("users:get", { id: 123 })
// → "/api/users/123"
```

Route names come from Litestar handler `name=` parameters.

### Schemas

```ts
import type { components } from "@/generated/schemas"

type User = components["schemas"]["User"]
type CreateUserRequest = components["schemas"]["CreateUserRequest"]
```

### SDK (optional)

```ts
import { ApiClient } from "@/generated/sdk"

const client = new ApiClient({ baseUrl: "/api" })
const users = await client.users.list()
```

## CI Integration

Generated files should either be:

1. **Committed and verified in CI**: regenerate in CI and `git diff --exit-code`. If diff, fail.
2. **Generated in CI before build**: not committed; CI runs `litestar assets generate-types` before `npm run build`.

Pattern (1) is preferred — diffs surface in PR review.

## Triggers

| Change | Re-trigger needed |
|---|---|
| Add/change a route handler | yes (`routes.ts`) |
| Add/change a Pydantic / msgspec DTO | yes (`schemas.ts`) |
| Change Inertia handler / page name | yes (`inertia-pages.json`) |
| Refactor internal modules | no (if no API surface change) |

## Pitfalls

- **Out-of-date types ⇒ runtime errors**. Always regenerate before `npm run build` in CI.
- **Frontend imports stale generated/**. Add `.gitignore` if generating in CI; otherwise commit and verify.
- **Inertia page-prop generation requires page handlers to use Inertia response helpers** — generic JSON handlers won't appear in `inertia-pages.json`.
