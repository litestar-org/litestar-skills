# FastAPI integration

This guide covers wiring Advanced Alchemy into a FastAPI application: the `Depends`-based DI pattern, the `provide_service` and `provide_filters` helpers, and the `database` / `db` CLI shim that ships with the FastAPI extension. Routing note: this guide covers FastAPI. For plain Starlette without `Depends`, see [starlette-integration.md](starlette-integration.md). For Flask (WSGI), see [flask-integration.md](flask-integration.md). For Sanic, see [sanic-integration.md](sanic-integration.md).

## Install

```text
pip install 'advanced-alchemy[fastapi]'
```

This pulls FastAPI, Starlette (FastAPI's ASGI substrate), and the core Advanced Alchemy library. The async SQLAlchemy driver (`asyncpg`, `aiosqlite`, `asyncmy`, etc.) is installed separately. If you want the database CLI integrated with `fastapi dev` / `fastapi run`, also install `fastapi[standard]` so `fastapi_cli` is available.

## Entry point

The FastAPI extension subclasses the Starlette one and adds two FastAPI-specific helpers: `provide_service()` and `provide_filters()`. Both return callables suitable for use inside `Depends(...)`.

```python
from fastapi import FastAPI

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
)

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)

app = FastAPI()
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
```

Passing `app=app` calls `init_app()`, which wraps FastAPI's lifespan context and registers the session middleware. If you prefer to construct the extension before the `FastAPI()` instance exists, omit `app=` and call `alchemy.init_app(app)` later.

## Lifecycle

The FastAPI extension inherits its lifecycle from the Starlette base class:

1. On application startup, the wrapped lifespan runs `config.on_startup()` — which creates the engine and (optionally) calls `metadata.create_all()`.
2. On every request, the session middleware lazily creates an `AsyncSession` (or `Session`) in request-scoped storage and exposes it via the `provide_session()` / `provide_service()` dependencies.
3. After the response is sent, the middleware commits or rolls back based on `commit_mode` and the response's status code, then closes the session and cleans up its request-scoped entry.
4. On application shutdown, the wrapped lifespan calls `config.on_shutdown()`, which disposes the engine.

For the commit predicate and the semantics of `manual`, `autocommit`, and `autocommit_include_redirect`, see [commit-modes.md](commit-modes.md). For the underlying ASGI storage mechanism, see [starlette-integration.md](starlette-integration.md).

**Generator-managed cleanup.** When you use `Depends(alchemy.provide_service(...))`, the dependency is a generator that owns its own commit/rollback/close sequence — it reads the response status during teardown and decides. This is why the middleware defers cleanup when it sees the `_generator_managed` sentinel: cleanup happens inside the generator, not in the middleware, so the transaction boundary lines up with the service's context manager.

## Config

Two config dataclasses are exported (both are re-exports of the Starlette ones):

- `SQLAlchemyAsyncConfig` — async SQLAlchemy.
- `SQLAlchemySyncConfig` — sync SQLAlchemy; the middleware calls `commit`/`rollback`/`close` on a threadpool.

The relevant keyword arguments:

| Argument | Default | Notes |
| --- | --- | --- |
| `connection_string` | (required) | Driver-qualified URL. |
| `session_config` | `AsyncSessionConfig()` / `SyncSessionConfig()` | `expire_on_commit`, `autoflush`. |
| `engine_config` | `EngineConfig()` | Pool sizing, echo, dialect tweaks. |
| `commit_mode` | `"manual"` | See [commit-modes.md](commit-modes.md). |
| `bind_key` | `None` | See [multi-database.md](multi-database.md). |
| `create_all` | `False` | Run `metadata.create_all()` at startup. Use Alembic in production. |

For multi-database setups (a primary write database plus a reporting replica, for example), see [multi-database.md](multi-database.md). The FastAPI extension accepts the same `config=[...]` sequence as the Starlette one, and every provider method (`provide_session`, `provide_service`, etc.) accepts an optional `key=` argument that picks the config by `bind_key`.

## Session injection

The idiomatic FastAPI pattern is to wrap `alchemy.provide_session()` in a `Depends(...)` inside a handler signature:

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]

@router.get("/orders")
async def list_orders(db_session: DatabaseSession) -> list[dict]:
    rows = (await db_session.execute(select(OrderModel))).scalars().all()
    return [{"id": str(r.id), "total": r.total_cents} for r in rows]
```

Three details worth noting:

- `alchemy.provide_session()` returns a callable whose signature is `(request: Request) -> AsyncSession`. FastAPI resolves that callable at every request, so you get one session per request.
- Wrapping it in `Annotated[AsyncSession, Depends(...)]` gives you a reusable type alias — handlers declare `db_session: DatabaseSession` with no boilerplate.
- For a sync config, use `alchemy.provide_sync_session()` and annotate with `sqlalchemy.orm.Session`. For handler code that doesn't care which flavor is active, `alchemy.provide_session()` returns the right one based on the resolved config.

**Multi-database.** When you register more than one config, pass the `bind_key` as the argument:

```python
DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]
ReportingSession = Annotated[AsyncSession, Depends(alchemy.provide_session("reporting"))]
```

## Service layer

`alchemy.provide_service(MyService)` returns a generator dependency that:

1. Acquires the request-scoped session via `provide_session()`.
2. Instantiates `MyService.new(session=...)` inside an `async with` / `with` context manager.
3. Yields the service into the handler.
4. On teardown, reads the response status, decides to commit or rollback based on the config's `commit_mode`, and closes the session.

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

class OrderService(SQLAlchemyAsyncRepositoryService[OrderModel]):
    class Repo(SQLAlchemyAsyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

class Order(BaseModel):
    id: UUID | None = None
    customer_email: str
    total_cents: int

class OrderCreate(BaseModel):
    customer_email: str
    total_cents: int

router = APIRouter()

Orders = Annotated[OrderService, Depends(alchemy.provide_service(OrderService))]

@router.get("/orders/{order_id}")
async def get_order(order_id: UUID, orders: Orders) -> Order:
    obj = await orders.get(order_id)
    return orders.to_schema(obj, schema_type=Order)

@router.post("/orders")
async def create_order(data: OrderCreate, orders: Orders) -> Order:
    obj = await orders.create(data)
    return orders.to_schema(obj, schema_type=Order)
```

The `Annotated[OrderService, Depends(alchemy.provide_service(OrderService))]` alias is the typical shape — it's what the upstream docs and example apps use.

**Passing load options.** `provide_service` forwards several arguments down to `Service.new`:

```python
Orders = Annotated[
    OrderService,
    Depends(
        alchemy.provide_service(
            OrderService,
            load=[OrderModel.customer],
            execution_options={"populate_existing": True},
        )
    ),
]
```

This is the FastAPI equivalent of calling `AuthorService(session=db_session, load=[AuthorModel.books])` manually — the generator forwards `load`, `execution_options`, `statement`, `error_messages`, `uniquify`, and `count_with_window_function` to `new()`.

## Filters and pagination

`alchemy.provide_filters(config)` builds a single FastAPI dependency that aggregates pagination, sort, search, id-in/not-in, and created-at/updated-at filters into a `list[FilterTypes]`. The `config` argument is a `FilterConfig` TypedDict.

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from advanced_alchemy import filters
from advanced_alchemy.service import OffsetPagination

router = APIRouter()

@router.get("/orders")
async def list_orders(
    orders: Orders,
    applied_filters: Annotated[
        list[filters.FilterTypes],
        Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "pagination_type": "limit_offset",
                    "pagination_size": 25,
                    "search": "customer_email",
                    "search_ignore_case": True,
                    "sort_field": "created_at",
                    "sort_order": "desc",
                    "created_at": True,
                }
            )
        ),
    ],
) -> OffsetPagination[Order]:
    results, total = await orders.get_many_and_count(*applied_filters)
    return orders.to_schema(results, total, filters=applied_filters, schema_type=Order)
```

The query parameters produced by that config:

| Key | Produces | Query parameter(s) |
| --- | --- | --- |
| `id_filter` | `CollectionFilter` | `?ids=...` |
| `pagination_type="limit_offset"` | `LimitOffset` | `?currentPage=1&pageSize=25` |
| `search` | `SearchFilter` | `?searchString=...&searchIgnoreCase=true` |
| `sort_field` + `sort_order` | `OrderBy` | `?orderBy=created_at&sortOrder=desc` |
| `created_at: True` | `BeforeAfter` | `?createdBefore=...&createdAfter=...` |
| `updated_at: True` | `BeforeAfter` | `?updatedBefore=...&updatedAfter=...` |
| `in_fields` / `not_in_fields` | `CollectionFilter` / `NotInCollectionFilter` | `?<field>In=...` / `?<field>NotIn=...` |

Results are returned in `orders.to_schema(results, total, filters=applied_filters, schema_type=Order)` as an `OffsetPagination[Order]`. The `OffsetPagination` type (from `advanced_alchemy.service`) is framework-agnostic and is the recommended response shape for paginated endpoints.

## Migrations / CLI

The FastAPI extension ships a Click command group that wraps the Alembic CLI. Two ways to wire it in:

### Via the FastAPI CLI (`fastapi dev` / `fastapi run`)

If you have `fastapi_cli` installed (through the `fastapi[standard]` extra), call `assign_cli_group(app)` from your app module. This registers Typer-native `database` and `db` commands on the FastAPI CLI and forwards to the Advanced Alchemy Click migration group. Use this Typer 0.26-compatible path; do not attach the Click group directly to Typer.

```python
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, assign_cli_group

# ... app and alchemy already constructed ...

assign_cli_group(app)
```

Then:

```text
fastapi dev app.py database upgrade head
fastapi dev app.py database revision --autogenerate -m "add orders table"
```

### As a standalone Click entry point

Alternatively, wire the command group into your own Click `__main__` using `register_database_commands(app)`:

```python
if __name__ == "__main__":
    from advanced_alchemy.extensions.fastapi.cli import register_database_commands
    from advanced_alchemy.utils.cli_tools import click

    @click.group()
    def cli() -> None:
        """Application CLI."""

    cli.add_command(register_database_commands(app))
    cli()
```

Then `python app.py database upgrade head` works without FastAPI's own CLI entry point.

The migration subcommands (`init`, `revision`, `upgrade`, `downgrade`, `history`, `current`, `stamp`, etc.) are the standard Alembic CLI surface — see the [migrations reference](migrations.md) for end-to-end usage.

## Example: full working handler

End-to-end: config + model + service + filters + CRUD handlers.

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy import filters
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import OffsetPagination, SQLAlchemyAsyncRepositoryService
from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    assign_cli_group,
)

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

class OrderService(SQLAlchemyAsyncRepositoryService[OrderModel]):
    class Repo(SQLAlchemyAsyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

class Order(BaseModel):
    id: UUID | None = None
    customer_email: str
    total_cents: int

class OrderCreate(BaseModel):
    customer_email: str
    total_cents: int

class OrderUpdate(BaseModel):
    customer_email: str | None = None
    total_cents: int | None = None

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)

app = FastAPI()
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
assign_cli_group(app)

router = APIRouter()

Orders = Annotated[OrderService, Depends(alchemy.provide_service(OrderService))]

@router.get("/orders")
async def list_orders(
    orders: Orders,
    applied_filters: Annotated[
        list[filters.FilterTypes],
        Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "pagination_type": "limit_offset",
                    "search": "customer_email",
                    "search_ignore_case": True,
                    "sort_field": "created_at",
                    "sort_order": "desc",
                }
            )
        ),
    ],
) -> OffsetPagination[Order]:
    results, total = await orders.get_many_and_count(*applied_filters)
    return orders.to_schema(results, total, filters=applied_filters, schema_type=Order)

@router.post("/orders")
async def create_order(orders: Orders, data: OrderCreate) -> Order:
    obj = await orders.create(data)
    return orders.to_schema(obj, schema_type=Order)

@router.get("/orders/{order_id}")
async def get_order(orders: Orders, order_id: UUID) -> Order:
    obj = await orders.get(order_id)
    return orders.to_schema(obj, schema_type=Order)

@router.patch("/orders/{order_id}")
async def update_order(orders: Orders, order_id: UUID, data: OrderUpdate) -> Order:
    obj = await orders.update(data, item_id=order_id)
    return orders.to_schema(obj, schema_type=Order)

@router.delete("/orders/{order_id}")
async def delete_order(orders: Orders, order_id: UUID) -> None:
    _ = await orders.delete(order_id)

app.include_router(router)
```

One POST to `/orders` with `{"customer_email": "a@b.co", "total_cents": 9900}`:

1. FastAPI resolves `orders: Orders`. That calls `alchemy.provide_service(OrderService)`, which itself depends on `alchemy.provide_session()`.
2. `provide_session` creates an `AsyncSession` in request-scoped storage.
3. `provide_service` opens `OrderService.new(session=...)` and yields the service into the handler.
4. The handler calls `orders.create(data)`, which inserts the row.
5. Handler returns `Order`. FastAPI serializes to JSON; status 200.
6. The `provide_service` generator's `finally` block reads the response status, sees 200, and — because `commit_mode="autocommit"` — calls `await session.commit()`, then `session.close()`.
7. The middleware sees the generator-managed sentinel, so it skips its own cleanup.
8. The response is sent.

## Cross-links

- [commit-modes.md](commit-modes.md) — `commit_mode` predicate, pitfalls, status-code customization.
- [multi-database.md](multi-database.md) — bind-key pattern; `provide_session("reporting")` etc.
- [starlette-integration.md](starlette-integration.md) — the base class; covers the underlying ASGI lifecycle.
- [flask-integration.md](flask-integration.md) — WSGI equivalent.
- [sanic-integration.md](sanic-integration.md) — `request.ctx`-based equivalent.
- [services.md](services.md) — `SQLAlchemyAsyncRepositoryService` API.
- [filters.md](filters.md) — the underlying filter types (`LimitOffset`, `SearchFilter`, etc.) that `provide_filters` assembles.
- [migrations.md](migrations.md) — Alembic workflow behind the database CLI.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public reference apps (Litestar-based; service/repository code transfers directly).
