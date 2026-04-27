# Route Handlers, Controllers, Routers

## Route Handlers

```python
from __future__ import annotations

from litestar import Controller, get, post, put, delete
from litestar.di import Provide


@get("/items/{item_id:int}")
async def get_item(item_id: int) -> Item:
    return await fetch_item(item_id)


@post("/items")
async def create_item(data: CreateItemDTO) -> Item:
    return await save_item(data)
```

## Controller (preferred for related routes)

```python
class ItemController(Controller):
    path = "/api/items"
    tags = ["Items"]
    dependencies = {"service": Provide(get_service)}

    @get("/")
    async def list_items(self, service: ItemService) -> list[Item]:
        return await service.list_all()

    @get("/{item_id:int}")
    async def get_item(self, item_id: int, service: ItemService) -> Item:
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

For larger apps, use the `DomainPlugin` auto-discovery pattern (see [domains.md](domains.md)).

## Cross-references

- Controller-level guards: [guards.md](../../litestar-auth-guards/references/guards.md)
- Controller-level filter dependencies: [pagination.md](../../litestar-data-services/references/pagination.md)
- Folder layout for domains: [domains.md](domains.md)
