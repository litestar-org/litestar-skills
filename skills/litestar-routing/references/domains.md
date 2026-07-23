# Domain-Clustered Folder Structure

Cluster code by business domain — each domain owns its schemas, services, controllers, guards, and jobs in a single folder. Shared infrastructure lives in `lib/`.

## Canonical Layout

```text
src/app/
├── domain/
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── controllers.py     # AccountController, UserController
│   │   ├── services.py        # AccountService, UserService
│   │   ├── schemas.py         # camelized msgspec DTOs
│   │   ├── guards.py          # requires_active_user, requires_superuser
│   │   ├── deps.py            # Provide() / Dishka providers
│   │   └── jobs.py            # SAQ tasks for this domain
│   ├── teams/
│   │   ├── controllers.py     # TeamController, MembershipController
│   │   └── ...
│   └── tasks/
│       └── ...
├── db/
│   ├── models/                # SQLAlchemy / advanced-alchemy models
│   └── migrations/            # Alembic
├── lib/                       # cross-cutting shared infrastructure
│   ├── exceptions.py          # ApplicationError hierarchy
│   ├── schema.py              # CamelizedBaseStruct base
│   ├── settings.py            # @dataclass settings
│   ├── deps.py                # shared filter dependencies
│   └── serialization.py
└── server/
    ├── app.py                 # Litestar() instance
    ├── plugins.py             # GranianPlugin, SAQPlugin, etc.
    └── routers.py             # Router composition
```

Refs: [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/app/`), [litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia) (`src/app/`).

## Why Domain Clustering

- **Locality of change.** Adding a field to `User` touches `domain/accounts/{schemas,services,controllers}.py` — three files in one folder, not three folders.
- **Bounded contexts.** Each domain folder is a candidate for extraction into a separate service later if needed.
- **Test colocation.** `tests/domain/accounts/test_users.py` mirrors source layout exactly.
- **Plugin auto-discovery.** Litestar Autowire walks configured domain packages
  to register controllers and listeners automatically.

## Shared `lib/`

`lib/` is for code that doesn't belong to any single domain:

- **`lib/exceptions.py`** — `ApplicationError` hierarchy (see [exceptions.md](../../litestar-exceptions/references/exceptions.md))
- **`lib/schema.py`** — `CamelizedBaseStruct` and shared msgspec primitives (see [dto.md](../../litestar-dto-openapi/references/dto.md))
- **`lib/settings.py`** — `@dataclass` config (see [settings.md](../../litestar-settings/references/settings.md))
- **`lib/deps.py`** — common filter / pagination dependencies reused across Controllers

When something in `lib/` becomes domain-specific, move it to that domain's folder.

## Multi-tenant Workspaces

For workspace-scoped apps, the workspace dimension lives in guards and channel names — not in folder layout:

```python
# domain/workspaces/guards.py
async def requires_workspace_membership(connection, _) -> None: ...

# domain/workspaces/controllers.py
class WorkspaceController(Controller):
    path = "/api/workspaces/{workspace_id:uuid}"
    guards = [requires_active_user, requires_workspace_membership]
```

Channels follow the same scoping (`workspace:{id}:events`). See [websockets.md](../../litestar-realtime/references/websockets.md).

## Cross-references

- Package discovery via Litestar Autowire:
  [litestar-autowire](../../litestar-autowire/SKILL.md)
- Workspace channel patterns: [websockets.md](../../litestar-realtime/references/websockets.md)
- Guard composition for tenant isolation: [guards.md](../../litestar-auth-guards/references/guards.md)
