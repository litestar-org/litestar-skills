# Sanic integration

This guide covers wiring Advanced Alchemy into a Sanic application: the sanic-ext `Extend.register` pattern, the `request.ctx` session store, and a key API quirk that differs from the other framework integrations. Routing note: this guide covers Sanic. For FastAPI-style DI, see [fastapi-integration.md](fastapi-integration.md). For plain Starlette ASGI, see [starlette-integration.md](starlette-integration.md). For Flask (WSGI), see [flask-integration.md](flask-integration.md).

## Install

```text
pip install 'advanced-alchemy[sanic]'
```

This pulls Sanic, `sanic_ext` (Sanic's official extension framework — required), and the core Advanced Alchemy library. The async SQLAlchemy driver (`asyncpg`, `aiosqlite`, etc.) is installed separately.

## Entry point (differences from FastAPI / Starlette)

> **Watch out:** the Sanic extension uses a **different constructor keyword** than the other frameworks.
>
> - Sanic: `AdvancedAlchemy(sqlalchemy_config=..., sanic_app=...)` — keyword is `sqlalchemy_config=`, not `config=`.
> - Registration is `alchemy.register(app)` (driven by `sanic_ext`), not `AdvancedAlchemy(app=app)`.
>
> Copying the `AdvancedAlchemy(config=..., app=app)` snippet from another framework's guide will raise `TypeError: unexpected keyword argument 'config'`. This is the single most common footgun when porting a FastAPI/Starlette setup to Sanic.

```python
from sanic import Sanic

from advanced_alchemy.extensions.sanic import (
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

app = Sanic("orders-service")
alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config)
alchemy.register(app)
```

You can alternatively pass `sanic_app=app` to the constructor, which calls `register(app)` for you:

```python
alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config, sanic_app=app)
```

Under the hood, `register()` calls `Extend.register(self)` from `sanic_ext` — the extension is a `sanic_ext.extensions.base.Extension` subclass, so `sanic_ext` drives its `startup()` lifecycle.

## Lifecycle

The extension installs its hooks via `sanic_ext` and Sanic's native listener API:

1. **`before_server_start`** — construct the engine, store it on `app.ctx.<engine_key>`, create the session maker, and register dependency providers with `sanic_ext` so `AsyncSession` / `AsyncEngine` / `async_sessionmaker[AsyncSession]` are injectable into handler signatures.
2. **`request` middleware** — lazily create an `AsyncSession` on `request.ctx.<session_key>` if none exists.
3. **`response` middleware** — inspect the response status, commit or rollback per `commit_mode`, close the session, and delete the `request.ctx` attribute.
4. **`after_server_stop`** — dispose the engine and clear the `app.ctx` keys.

For the commit predicate and the semantics of `manual`, `autocommit`, and `autocommit_include_redirect`, see [commit-modes.md](commit-modes.md).

## Config

`SQLAlchemyAsyncConfig` is the usual choice — Sanic is an async framework. `SQLAlchemySyncConfig` exists but drives commit/rollback/close through `asyncio.get_event_loop().run_in_executor(None, ...)`, which is rarely what you want in a production async server.

| Argument | Default | Notes |
| --- | --- | --- |
| `connection_string` | (required) | Driver-qualified URL. |
| `session_config` | `AsyncSessionConfig()` / `SyncSessionConfig()` | `expire_on_commit`, `autoflush`. |
| `engine_config` | `EngineConfig()` | Pool sizing, echo. |
| `commit_mode` | `"manual"` | See [commit-modes.md](commit-modes.md). |
| `bind_key` | `None` | See [multi-database.md](multi-database.md). |
| `create_all` | `False` | Run `metadata.create_all()` during startup. |

For multi-database setups, see [multi-database.md](multi-database.md). The Sanic extension accepts the same sequence-of-configs pattern as the other framework integrations — pass a list via `sqlalchemy_config=[...]` and look configs up by `bind_key`.

## Session injection

Two ways to get a session into a handler:

### Via `request.ctx`

The session is stored at `request.ctx.<session_key>`. The extension exposes a helper that reads (and lazily creates) it:

```python
from sanic import Request, json
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

@app.get("/orders")
async def list_orders(request: Request):
    session = alchemy.get_async_session(request)
    rows = (await session.execute(select(OrderModel))).scalars().all()
    return json([{"id": str(r.id), "total": r.total_cents} for r in rows])
```

### Via sanic-ext dependency injection

The extension registers `AsyncSession` (and the engine, and the session maker) as sanic-ext dependencies during startup. With `sanic_ext` resolving parameters, the handler can declare the session as a typed parameter:

```python
from sanic import Request, json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/orders")
async def list_orders(request: Request, session: AsyncSession):
    rows = (await session.execute(select(OrderModel))).scalars().all()
    return json([{"id": str(r.id), "total": r.total_cents} for r in rows])
```

If you want to additionally register a concrete session type (for example a subclass), call `alchemy.add_session_dependency(AsyncSession)` after `register(app)` — it forwards to `app.ext.add_dependency(...)` from sanic-ext.

## Service layer

The Sanic extension does not ship a `provide_service()` helper analogous to the FastAPI one. Instantiate the service manually with the request-scoped session:

```python
from sanic import Request, json

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

class OrderService(SQLAlchemyAsyncRepositoryService[OrderModel]):
    class Repo(SQLAlchemyAsyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

@app.post("/orders")
async def create_order(request: Request):
    orders_service = OrderService(session=alchemy.get_async_session(request))
    obj = await orders_service.create(request.json)
    return json({"id": str(obj.id)})
```

If you want a "provider" function that returns a configured service, write a small async helper and call it from the handler — sanic-ext will resolve it if you register it as a dependency via `app.ext.add_dependency(...)`.

## Filters and pagination

The Sanic extension does not ship a filter aggregator. Build filters from `request.args` and pass them through:

```python
from advanced_alchemy import filters

@app.get("/orders")
async def list_orders(request: Request):
    current_page = int(request.args.get("currentPage", "1"))
    page_size = int(request.args.get("pageSize", "20"))
    search_term = request.args.get("searchString")

    applied_filters: list[filters.FilterTypes] = [
        filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))
    ]
    if search_term:
        applied_filters.append(
            filters.SearchFilter(
                field_name={"customer_email"}, value=search_term, ignore_case=True
            )
        )

    orders_service = OrderService(session=alchemy.get_async_session(request))
    results, total = await orders_service.get_many_and_count(*applied_filters)
    return json({"total": total, "items": [{"id": str(r.id)} for r in results]})
```

## Migrations / CLI

The Sanic extension does not ship a CLI shim. Run Alembic through the `alchemy` CLI that ships with the core library; point it at the same config objects you pass to the extension. For end-to-end migration authoring, see the [migrations reference](migrations.md).

## Example: full working handler

End-to-end: config + extension registered via sanic-ext + a handler using `request.ctx`-backed session.

```python
from sanic import Request, Sanic, json
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.extensions.sanic import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
)

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

class OrderService(SQLAlchemyAsyncRepositoryService[OrderModel]):
    class Repo(SQLAlchemyAsyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)

app = Sanic("orders-service")
alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config)
alchemy.register(app)

@app.get("/orders")
async def list_orders(request: Request):
    session = alchemy.get_async_session(request)
    rows = (await session.execute(select(OrderModel))).scalars().all()
    return json([{"id": str(r.id), "total": r.total_cents} for r in rows])

@app.post("/orders")
async def create_order(request: Request):
    orders_service = OrderService(session=alchemy.get_async_session(request))
    obj = await orders_service.create(request.json)
    return json({"id": str(obj.id)})
```

One POST to `/orders` with `{"customer_email": "a@b.co", "total_cents": 9900}`:

1. Sanic dispatches to `create_order`; the `request` middleware has already created an `AsyncSession` on `request.ctx`.
2. The handler instantiates `OrderService` with that session and calls `create()`.
3. The handler returns a `json(...)` response; status 200.
4. The `response` middleware sees status 200 and — with `commit_mode="autocommit"` — commits, closes, and deletes the `request.ctx` attribute.

## Cross-links

- [commit-modes.md](commit-modes.md) — `commit_mode` predicate, pitfalls, status-code customization.
- [multi-database.md](multi-database.md) — bind-key pattern.
- [fastapi-integration.md](fastapi-integration.md) — FastAPI counterpart (constructor keyword is `config=`, not `sqlalchemy_config=`).
- [starlette-integration.md](starlette-integration.md) — plain ASGI counterpart.
- [flask-integration.md](flask-integration.md) — WSGI counterpart.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public reference apps (Litestar-based; service/repository code transfers directly).
