# Flask integration

This guide covers wiring Advanced Alchemy into a Flask (WSGI) application: `g`-based request-scoped sessions, the application-factory pattern, the `flask database` CLI shim, and the portal-based bridge for async SQLAlchemy inside sync handlers. Routing note: this guide covers Flask. For FastAPI-style DI, see [fastapi-integration.md](fastapi-integration.md). For plain Starlette, see [starlette-integration.md](starlette-integration.md). For Sanic, see [sanic-integration.md](sanic-integration.md).

## Install

```text
pip install 'advanced-alchemy[flask]'
```

This pulls Flask and the core Advanced Alchemy library. The SQLAlchemy driver is installed separately. For the common sync path, use `psycopg[binary]` (PostgreSQL) or the stdlib `sqlite3`-backed driver. For the async-via-portal path, use `asyncpg` or `aiosqlite`.

## Entry point

Import `AdvancedAlchemy` from `advanced_alchemy.extensions.flask`. The extension:

- Registers session cleanup via `app.teardown_appcontext`.
- Adds a `database` command group to `app.cli`.
- Optionally sets up `app.after_request` commit/rollback handlers when `commit_mode` is non-manual.
- For async configs, starts a background `PortalProvider` thread that runs an event loop on behalf of sync handlers.

```python
from flask import Flask

from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    SQLAlchemySyncConfig,
)

alchemy_config = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://app:app@localhost:5432/orders",
    commit_mode="autocommit",
    create_all=True,
)

app = Flask(__name__)
alchemy = AdvancedAlchemy(alchemy_config, app)
```

## Lifecycle

The Flask extension installs two classes of hook:

1. **Session cleanup** — a `teardown_appcontext` callback that closes every `advanced_alchemy_session_<bind_key>` attribute on `g` when the application context ends. This runs even if the handler raised.
2. **Commit/rollback** — when `commit_mode` is `"autocommit"` or `"autocommit_include_redirect"`, an `after_request` handler that calls `session.commit()` for successful responses and lets rollback fall to `teardown_appcontext`. See [commit-modes.md](commit-modes.md) for the full predicate.

Per-request session creation is lazy: `alchemy.get_session()` / `alchemy.get_sync_session()` / `alchemy.get_async_session()` creates the session on first call and stores it on `g` for the rest of the request. Repeated calls in the same request return the same session.

Extension bookkeeping is stored on `app.extensions["advanced_alchemy"]`, so `flask.current_app.extensions["advanced_alchemy"]` returns the `AdvancedAlchemy` instance from anywhere in the request.

## Config

`SQLAlchemySyncConfig` is the common case — Flask is a sync WSGI framework. `SQLAlchemyAsyncConfig` is available for teams that share SQLAlchemy async code between Flask and other frameworks; see the async section below.

| Argument | Default | Notes |
| --- | --- | --- |
| `connection_string` | (required) | Driver-qualified URL. |
| `session_config` | `SyncSessionConfig()` / `AsyncSessionConfig()` | `expire_on_commit`, `autoflush`. |
| `engine_config` | `EngineConfig()` | Pool sizing, echo, dialect tweaks. |
| `commit_mode` | `"manual"` | See [commit-modes.md](commit-modes.md). |
| `bind_key` | `None` | See [multi-database.md](multi-database.md). |
| `create_all` | `False` | Run `metadata.create_all()` on `init_app()`. |

For multi-database setups, see [multi-database.md](multi-database.md). The Flask extension accepts the same sequence-of-configs pattern as the other framework integrations, and `alchemy.get_session("reporting")` returns the session for the named bind key.

## Session injection (sync)

Flask does not ship a dependency-injection system. The idiomatic pattern is to look the session up inside the handler via the extension instance:

```python
from flask import Flask, jsonify
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

@app.route("/orders", methods=["GET"])
def list_orders():
    session = alchemy.get_sync_session()
    rows = session.execute(select(OrderModel)).scalars().all()
    return jsonify([{"id": str(r.id), "total": r.total_cents} for r in rows])
```

`alchemy.get_sync_session()` reads from `g.advanced_alchemy_session_default` (or the appropriate bind-key variant) and creates the session on first call. By the time `teardown_appcontext` runs, the response has been sent; the hook closes the session and deletes the `g` attribute.

**Blueprint.** The same pattern works inside a `Blueprint`:

```python
from flask import Blueprint, current_app, jsonify

orders_bp = Blueprint("orders", __name__)

@orders_bp.route("/orders", methods=["GET"])
def list_orders():
    alchemy_ext = current_app.extensions["advanced_alchemy"]
    session = alchemy_ext.get_sync_session()
    # ... same as above
```

Using `current_app.extensions["advanced_alchemy"]` inside a blueprint avoids the circular import that would otherwise happen if the blueprint tried to import `alchemy` from the app module.

## Application factory

The standard Flask application-factory pattern works by constructing the extension without an `app`, then calling `init_app()` from inside the factory:

```python
from flask import Flask

from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    SQLAlchemySyncConfig,
)

alchemy = AdvancedAlchemy(
    SQLAlchemySyncConfig(
        connection_string="postgresql+psycopg://app:app@localhost:5432/orders",
        commit_mode="autocommit",
    )
)

def create_app() -> Flask:
    app = Flask(__name__)
    alchemy.init_app(app)

    from .routes import orders_bp
    app.register_blueprint(orders_bp)
    return app
```

`init_app()` raises `ImproperConfigurationError` if the same extension is already registered on the application — double-registration is a common bug in factory setups where the module-level `alchemy` is accidentally re-initialized. If you need per-app isolation in tests, construct a fresh `AdvancedAlchemy(...)` per test `app` instance.

## Service layer

The Flask extension ships `FlaskServiceMixin`, which adds a `.jsonify()` method that serializes using the same JSON encoder the extension configured on the engine. Mix it into a service alongside `SQLAlchemySyncRepositoryService`:

```python
from uuid import UUID

from flask import Flask, request
from msgspec import Struct
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemySyncRepositoryService
from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    FlaskServiceMixin,
    SQLAlchemySyncConfig,
)

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

class OrderSchema(Struct):
    customer_email: str
    total_cents: int
    id: UUID | None = None

class OrderService(
    SQLAlchemySyncRepositoryService[OrderModel],
    FlaskServiceMixin,
):
    class Repo(SQLAlchemySyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    SQLAlchemySyncConfig(
        connection_string="postgresql+psycopg://app:app@localhost:5432/orders",
        commit_mode="autocommit",
    ),
    app,
)

@app.route("/orders", methods=["POST"])
def create_order():
    orders_service = OrderService(session=alchemy.get_sync_session())
    obj = orders_service.create(**request.get_json())
    return orders_service.jsonify(orders_service.to_schema(obj, schema_type=OrderSchema))
```

`FlaskServiceMixin.jsonify()` returns a `flask.Response` with `mimetype="application/json"` and the service's `schema_dump`-compatible serializer. It's the Flask equivalent of `flask.jsonify()` for service output.

## Filters and pagination

The Flask extension does not ship a filter aggregator. Build filters from `request.args` and pass them to the service:

```python
from advanced_alchemy import filters

@app.route("/orders", methods=["GET"])
def list_orders():
    current_page = request.args.get("currentPage", 1, type=int)
    page_size = request.args.get("pageSize", 20, type=int)
    search_term = request.args.get("searchString")

    limit_offset = filters.LimitOffset(
        limit=page_size,
        offset=page_size * (current_page - 1),
    )
    applied_filters: list[filters.FilterTypes] = [limit_offset]
    if search_term:
        applied_filters.append(
            filters.SearchFilter(
                field_name={"customer_email"},
                value=search_term,
                ignore_case=True,
            )
        )

    orders_service = OrderService(session=alchemy.get_sync_session())
    results, total = orders_service.get_many_and_count(*applied_filters)
    payload = orders_service.to_schema(
        results, total, filters=applied_filters, schema_type=OrderSchema
    )
    return orders_service.jsonify(payload)
```

The `filters` subpackage is framework-agnostic; `LimitOffset`, `SearchFilter`, `CollectionFilter`, `OrderBy`, `BeforeAfter`, and friends all work the same way here as in any other integration.

## Migrations / CLI

Initializing the extension adds a `database` command group to `app.cli`. With `FLASK_APP` pointed at your app module:

```text
flask database init
flask database revision --autogenerate -m "add orders table"
flask database upgrade head
flask database downgrade -1
flask database history
flask database current
```

Under the hood, `app.cli.add_command(database_group)` runs during `init_app()`, and `database_group` is decorated with `flask.cli.with_appcontext` so the Advanced Alchemy extension (and therefore the configs) is available to the Alembic commands. For end-to-end migration authoring (env.py, autogenerate gotchas, offline SQL), see the [migrations reference](migrations.md).

## Async via portal (advanced)

Flask is sync-first, but the extension supports `SQLAlchemyAsyncConfig` for teams that share async SQLAlchemy code between frameworks. When you register an async config, the extension starts a `PortalProvider` — a background thread that owns an `asyncio` event loop — and exposes it as `alchemy.portal`. Sync Flask handlers call async methods through `alchemy.portal.call(...)`.

```python
from flask import Flask, jsonify
from sqlalchemy import select

from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
        create_all=True,
    ),
    app,
)

@app.route("/orders")
def list_orders():
    session = alchemy.get_async_session()
    rows = alchemy.portal.call(session.execute, select(OrderModel)).scalars().all()
    return jsonify([{"id": str(r.id)} for r in rows])
```

Two properties of this setup:

- **The portal is not free.** A thread plus an event loop is allocated at `init_app()` time. If your workload is fully sync, use `SQLAlchemySyncConfig` instead.
- **Don't call `session.commit()` directly inside the handler unless `commit_mode="manual"`.** The extension installs an `after_request` handler that already drives commit/rollback through the portal using the configured `commit_mode`.

The `alchemy.portal.call(fn, *args, **kwargs)` API runs `fn(*args, **kwargs)` on the portal's event loop and returns the result synchronously to the calling Flask thread. Coroutine functions are awaited; plain callables are scheduled as a single-call coroutine.

## Example: full working handler

End-to-end sync example with service + filters + CRUD:

```python
from uuid import UUID

from flask import Flask, request
from msgspec import Struct
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy import filters
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemySyncRepositoryService
from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    FlaskServiceMixin,
    SQLAlchemySyncConfig,
)

class OrderModel(UUIDBase):
    __tablename__ = "order"
    customer_email: Mapped[str] = mapped_column()
    total_cents: Mapped[int] = mapped_column()

class OrderSchema(Struct):
    customer_email: str
    total_cents: int
    id: UUID | None = None

class OrderService(
    SQLAlchemySyncRepositoryService[OrderModel],
    FlaskServiceMixin,
):
    class Repo(SQLAlchemySyncRepository[OrderModel]):
        model_type = OrderModel

    repository_type = Repo

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    SQLAlchemySyncConfig(
        connection_string="postgresql+psycopg://app:app@localhost:5432/orders",
        commit_mode="autocommit",
        create_all=True,
    ),
    app,
)

@app.route("/orders", methods=["GET"])
def list_orders():
    current_page = request.args.get("currentPage", 1, type=int)
    page_size = request.args.get("pageSize", 20, type=int)
    limit_offset = filters.LimitOffset(
        limit=page_size, offset=page_size * (current_page - 1)
    )
    orders_service = OrderService(session=alchemy.get_sync_session())
    results, total = orders_service.get_many_and_count(limit_offset)
    payload = orders_service.to_schema(
        results, total, filters=[limit_offset], schema_type=OrderSchema
    )
    return orders_service.jsonify(payload)

@app.route("/orders", methods=["POST"])
def create_order():
    orders_service = OrderService(session=alchemy.get_sync_session())
    obj = orders_service.create(**request.get_json())
    return orders_service.jsonify(orders_service.to_schema(obj, schema_type=OrderSchema))

@app.route("/orders/<uuid:order_id>", methods=["GET"])
def get_order(order_id: UUID):
    orders_service = OrderService(session=alchemy.get_sync_session())
    obj = orders_service.get(order_id)
    return orders_service.jsonify(orders_service.to_schema(obj, schema_type=OrderSchema))

@app.route("/orders/<uuid:order_id>", methods=["PATCH"])
def update_order(order_id: UUID):
    orders_service = OrderService(session=alchemy.get_sync_session())
    obj = orders_service.update(**request.get_json(), item_id=order_id)
    return orders_service.jsonify(orders_service.to_schema(obj, schema_type=OrderSchema))

@app.route("/orders/<uuid:order_id>", methods=["DELETE"])
def delete_order(order_id: UUID):
    orders_service = OrderService(session=alchemy.get_sync_session())
    orders_service.delete(order_id)
    return "", 204
```

One POST to `/orders` with `{"customer_email": "a@b.co", "total_cents": 9900}`:

1. Flask resolves the handler; the request context is pushed.
2. The handler calls `alchemy.get_sync_session()`, which creates a session and stores it on `g.advanced_alchemy_session_default`.
3. The service inserts the row.
4. The handler returns a `Response` with status 200.
5. The `after_request` hook (installed by `commit_mode="autocommit"`) pops the session from `g`, sees 200, and commits.
6. `teardown_appcontext` runs; any remaining sessions on `g` are closed. In this case the `after_request` hook already popped it.

## Cross-links

- [commit-modes.md](commit-modes.md) — `commit_mode` predicate, pitfalls, status-code customization.
- [multi-database.md](multi-database.md) — bind-key pattern; `alchemy.get_sync_session("reporting")` etc.
- [fastapi-integration.md](fastapi-integration.md) — FastAPI counterpart with `Depends`-based DI.
- [starlette-integration.md](starlette-integration.md) — ASGI base class behind FastAPI.
- [sanic-integration.md](sanic-integration.md) — async framework counterpart.
- [services.md](services.md) — `SQLAlchemySyncRepositoryService` and `FlaskServiceMixin`.
- [filters.md](filters.md) — filter types (`LimitOffset`, `SearchFilter`, etc.).
- [migrations.md](migrations.md) — Alembic workflow behind `flask database`.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public reference apps (Litestar-based; service/repository code transfers directly).
