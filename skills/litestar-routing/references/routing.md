# Route Handlers, Controllers, Routers

## Route Handlers

```python
from __future__ import annotations

from typing import Annotated

from litestar import Controller, delete, get, post, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery, QueryParameter


@get("/items/{item_id:int}")
async def get_item(item_id: FromPath[int]) -> Item:
    return await fetch_item(item_id)


@post("/items")
async def create_item(data: CreateItemDTO) -> Item:
    return await save_item(data)


@get("/items")
async def list_items(
    limit: Annotated[int, QueryParameter(gt=0, le=100)] = 20,
    search: FromQuery[str | None] = None,
) -> list[Item]:
    return await search_items(limit=limit, search=search)
```

Request parameter sources are explicit in Litestar 2.24:

| Need | Declaration |
| --- | --- |
| Unconstrained query or path value | `FromQuery[T]` / `FromPath[T]` |
| Constraints, description, alias, or schema metadata | `Annotated[T, QueryParameter(...)]` / `Annotated[T, PathParameter(...)]` |
| Default value | Put `= value` on the function parameter |

Migrate implicit query/path parameters to `FromQuery[T]` / `FromPath[T]`.
Migrate `Parameter(query=...)`, `Parameter(header=...)`, and
`Parameter(cookie=...)` to the source-specific parameter classes with `name=`.
`Parameter(...)` remains valid for pure metadata in `Annotated`, but the
source-specific classes communicate intent and are preferred.

## Controller (preferred for related routes)

```python
class ItemController(Controller):
    path = "/api/items"
    tags = ["Items"]
    dependencies = {"service": Provide(get_service)}

    @get("/")
    async def list_items(self, service: NamedDependency[ItemService]) -> list[Item]:
        return await service.list_all()

    @get("/{item_id:int}")
    async def get_item(
        self,
        item_id: FromPath[int],
        service: NamedDependency[ItemService],
    ) -> Item:
        return await service.get(item_id)
```

`Controller` shares `path`, `dependencies`, `guards`, `tags`, and `middleware` across handlers — the canonical unit of organization.

## Domain Clustering

Cluster Controllers by **business domain**, not by HTTP method. Each domain owns its `controllers.py`:

```text
src/app/domain/
├── accounts/
│   ├── controllers.py   # AccountController, UserController
│   ├── services.py
│   ├── schemas.py
│   └── guards.py
├── teams/
│   ├── controllers.py   # TeamController, MembershipController
│   └── ...
└── tasks/
    ├── controllers.py
    └── ...
```

Canonical refs: [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/app/domain/`). Each domain folder is self-contained — schemas, services, controllers, guards, and jobs all live together.

## Router Composition

```python
# src/app/server/routers.py
from litestar import Router

from app.domain.accounts.controllers import AccountController, UserController
from app.domain.teams.controllers import TeamController


def create_api_router() -> Router:
    return Router(
        path="/api",
        route_handlers=[
            AccountController,
            UserController,
            TeamController,
        ],
    )
```

For larger domain-package apps, use
[Litestar Autowire](../../litestar-autowire/SKILL.md) to discover controllers
and listeners (see [domains.md](domains.md)).

## Cross-references

- Controller-level guards: [guards.md](../../litestar-auth-guards/references/guards.md)
- Controller-level filter dependencies: [pagination.md](../../litestar-data-services/references/pagination.md)
- Folder layout for domains: [domains.md](domains.md)

## Tagged source

- [2.24 parameter declarations](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/usage/routing/parameters.rst)
- [2.24 explicit declarations](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/topics/explicit_declarations.rst)
