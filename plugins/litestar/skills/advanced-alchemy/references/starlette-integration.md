# Starlette integration

This guide covers wiring Advanced Alchemy into a plain Starlette ASGI application. The extension class is the base class that the FastAPI integration subclasses, so the lifecycle story here is the simplest and most directly reflects the ASGI substrate. Routing note: this guide covers Starlette. For FastAPI-style DI with `Depends`, see [fastapi-integration.md](fastapi-integration.md). For Flask (WSGI), see [flask-integration.md](flask-integration.md). For Sanic, see [sanic-integration.md](sanic-integration.md).

## Install

```text
pip install 'advanced-alchemy[starlette]'
```

The `starlette` extra pulls Starlette itself and the async SQLAlchemy dialect of your choice is installed separately (for example `aiosqlite` for SQLite or `asyncpg` for PostgreSQL). If you already depend on Starlette elsewhere, the plain `advanced-alchemy` install plus your driver is enough.

## Entry point

Import `AdvancedAlchemy` from `advanced_alchemy.extensions.starlette`. The class owns engine startup/shutdown, per-request session creation, and the ASGI middleware that commits or rolls back based on the response status code.

```python
from starlette.applications import Starlette

from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
)

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
)

app = Starlette()
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
```

Passing `app=app` calls `alchemy.init_app(app)` for you. If you want to construct the extension before the Starlette app exists (for example, because the app is created inside a factory), omit `app=` and call `init_app()` later.

## Lifecycle

`init_app()` wraps the existing `app.router.lifespan_context` so that Advanced Alchemy's startup (engine construction, optional `create_all`) runs before your own startup hook and its shutdown (engine dispose, state cleanup) runs after your own shutdown hook. You do not need to write a lifespan handler yourself — the extension owns it.

Per-request session handling happens in a pure ASGI middleware (`SessionMiddleware` in `advanced_alchemy.extensions.starlette.config`) that the extension adds to the app during `init_app()`. The middleware:

1. Creates or reuses a session on `request.state.<session_key>` when a handler first asks for one.
2. Observes the response's `http.response.start` status code.
3. Commits or rolls back based on that status code and the config's `commit_mode` — see [commit-modes.md](commit-modes.md) for the full predicate and the semantics of `manual`, `autocommit`, and `autocommit_include_redirect`.
4. Closes the session and deletes the `request.state` attribute.

The middleware intercepts `send` directly rather than using `BaseHTTPMiddleware`, so generator-managed dependencies (used by service providers on the FastAPI subclass) can cleanly own the session lifecycle when needed.

## Config

Two config dataclasses are re-exported from `advanced_alchemy.extensions.starlette`:

- `SQLAlchemyAsyncConfig` — async SQLAlchemy (`AsyncEngine` + `AsyncSession`). Use this for `asyncpg`, `aiosqlite`, `asyncmy`, etc.
- `SQLAlchemySyncConfig` — sync SQLAlchemy (`Engine` + `Session`). The middleware calls `session.commit()` / `session.rollback()` via `starlette.concurrency.run_in_threadpool`, so you can run sync-style ORM code from an async handler.

Both expose the same keyword arguments:

| Argument | Default | Notes |
| --- | --- | --- |
| `connection_string` | (required) | Passed straight to `sqlalchemy.create_engine` / `create_async_engine`. |
| `session_config` | `AsyncSessionConfig()` / `SyncSessionConfig()` | Controls `expire_on_commit`, `autoflush`, etc. |
| `engine_config` | `EngineConfig()` | Pool size, recycle, echo — see SQLAlchemy's engine docs. |
| `commit_mode` | `"manual"` | `manual` / `autocommit` / `autocommit_include_redirect`. |
| `bind_key` | `None` | Identifier when you register more than one config. See [multi-database.md](multi-database.md). |
| `create_all` | `False` | Run `metadata.create_all()` during startup (convenient for tests; use Alembic in production). |

For a side-by-side multi-database setup (a primary write database plus a read-only analytics warehouse, each with its own `bind_key`), see [multi-database.md](multi-database.md).

## Session injection

Starlette does not ship a dependency-injection system. The extension therefore gives you the session via `request.state`:

```python
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

async def healthcheck(request: Request) -> JSONResponse:
    session = alchemy.get_async_session(request)
    result = await session.execute(text("SELECT 1"))
    return JSONResponse({"ok": result.scalar() == 1})
```

`alchemy.get_async_session(request)` returns the `AsyncSession` bound to this request, creating it on first call and reusing it on subsequent calls in the same request. Use `alchemy.get_sync_session(request)` for a `SQLAlchemySyncConfig`, or `alchemy.get_session(request)` when the handler is polymorphic over both.

The session is also accessible directly at `request.state.<session_key>`; the default `session_key` is `db_session`, but the extension namespaces it to avoid collisions (`advanced_alchemy_async_session_db_session` by default).

## Service layer

The standalone Starlette extension does not ship a `provide_service()` helper — that is a FastAPI-only convenience built on top of `Depends`. To use the service layer in a plain Starlette handler, instantiate the service with the request-scoped session directly:

```python
from sqlalchemy.orm import Mapped, mapped_column
from starlette.requests import Request
from starlette.responses import JSONResponse

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

async def list_orders(request: Request) -> JSONResponse:
    session = alchemy.get_async_session(request)
    orders_service = OrderService(session=session)
    results = await orders_service.get_many()
    return JSONResponse([{"id": str(o.id), "total": o.total_cents} for o in results])
```

## Filters and pagination

The standalone Starlette extension does not ship a filter-aggregator (`create_filter_dependencies` / `provide_filters`) — again, that is a FastAPI convenience. In a Starlette handler, build filters from query parameters yourself using the framework-neutral types in `advanced_alchemy.filters`:

```python
from advanced_alchemy.filters import LimitOffset, SearchFilter
from starlette.requests import Request
from starlette.responses import JSONResponse

async def list_orders(request: Request) -> JSONResponse:
    session = alchemy.get_async_session(request)
    orders_service = OrderService(session=session)

    page = int(request.query_params.get("currentPage", 1))
    page_size = int(request.query_params.get("pageSize", 20))
    search_term = request.query_params.get("searchString")

    filters = [LimitOffset(limit=page_size, offset=page_size * (page - 1))]
    if search_term:
        filters.append(
            SearchFilter(field_name={"customer_email"}, value=search_term, ignore_case=True)
        )

    results, total = await orders_service.get_many_and_count(*filters)
    return JSONResponse({"items": [...], "total": total})
```

## Migrations / CLI

The standalone Starlette extension does not expose a CLI shim. Run Alembic through the `alchemy` CLI that ships with the core library — point it at the same config objects you pass to the extension. For the end-to-end migration workflow, see the [migrations reference](migrations.md).

## Example: full working handler

End-to-end: config + extension + a single handler wired through the ASGI lifespan.

```python
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
)

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)

async def list_orders(request: Request) -> JSONResponse:
    session = alchemy.get_async_session(request)
    rows = (await session.execute(select(OrderModel))).scalars().all()
    return JSONResponse([{"id": str(r.id), "total": r.total_cents} for r in rows])

app = Starlette(routes=[Route("/orders", list_orders)])
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
```

One request to `/orders`:

1. The extension's middleware lazily creates an `AsyncSession` on `request.state`.
2. The handler calls `alchemy.get_async_session(request)` and receives that session.
3. The handler returns a 200 `JSONResponse`.
4. `commit_mode="autocommit"` + status 200 → the middleware calls `session.commit()`, then `session.close()`, then deletes the session from `request.state`.

## Cross-links

- [commit-modes.md](commit-modes.md) — `commit_mode` predicate, pitfalls, status-code customization.
- [multi-database.md](multi-database.md) — bind-key pattern for multiple configs.
- [fastapi-integration.md](fastapi-integration.md) — DI-based session injection; subclasses the Starlette extension.
- [flask-integration.md](flask-integration.md) — WSGI equivalent.
- [sanic-integration.md](sanic-integration.md) — `request.ctx`-based equivalent.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public reference apps (Litestar-based, but the service/repository code transfers directly).
