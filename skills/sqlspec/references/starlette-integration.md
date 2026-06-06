# Starlette integration

SQLSpec ships a first-party Starlette extension that wraps the ASGI lifespan to manage connection pools and mounts request-scoped middleware that stores each request's database connection on `request.state`. This guide covers the async ASGI wiring for plain Starlette apps. For FastAPI, see [fastapi-integration.md](fastapi-integration.md); for WSGI Flask, see [flask-integration.md](flask-integration.md).

The whole integration is anchored on a single class — `SQLSpecPlugin` — plus two middleware variants (`SQLSpecManualMiddleware`, `SQLSpecAutocommitMiddleware`) that differ only in their transaction policy. Everything else (the filter system, the sqlcommenter and correlation middleware) composes on top.

## Install

```bash
pip install 'sqlspec[starlette]'
```

The `starlette` extra pulls in `starlette` itself. You still need to install an adapter extra for whichever database you're using — e.g. `sqlspec[starlette,asyncpg]` for Postgres via asyncpg, or `sqlspec[starlette,aiosqlite]` for local SQLite. Adapter-specific notes live in [adapters.md](adapters.md).

## Entry point

```python
from starlette.applications import Starlette

from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.starlette import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "starlette": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
            }
        },
    )
)

app = Starlette()
db_plugin = SQLSpecPlugin(sqlspec, app)
```

Three things to note:

1. `SQLSpecPlugin(sqlspec, app)` is the eager form — the plugin introspects the registry and wires the app immediately. The two-step form `SQLSpecPlugin(sqlspec)` followed by `db_plugin.init_app(app)` is equivalent and is the shape you want when constructing the plugin at module scope and attaching it inside a factory.
2. The `extension_config["starlette"]` dict carries framework settings — `commit_mode`, `session_key`, `connection_key`, `pool_key`, and the optional correlation / sqlcommenter toggles. Defaults are the same per-config (one registered config produces one middleware stack).
3. FastAPI's `SQLSpecPlugin` has its own `extension_config["fastapi"]` block. Declare both `"starlette"` and `"fastapi"` only when the same config must be reused in both host integrations.

## Lifecycle

`init_app` composes the plugin's lifespan with whatever lifespan was already installed on the Starlette router. The upstream wrapper is:

```python
from contextlib import asynccontextmanager

original_lifespan = app.router.lifespan_context

@asynccontextmanager
async def combined_lifespan(app):
    async with db_plugin.lifespan(app), original_lifespan(app):
        yield

app.router.lifespan_context = combined_lifespan
```

Inside `db_plugin.lifespan(app)` the plugin iterates every config that reports `supports_connection_pooling` and calls `await config.create_pool()`, storing the pool on `app.state` under the config's `pool_key`. On shutdown the reverse happens — each pool is closed via `config.close_pool()` (awaited if the adapter returns a coroutine).

Per-request wiring is driven by middleware. For each config whose `disable_di` is not set, the plugin registers one of two middleware instances based on `commit_mode`:

- `SQLSpecManualMiddleware` — acquires a connection, stashes it on `request.state` under `connection_key`, releases on the way out. Never commits or rolls back; your handler owns transaction boundaries.
- `SQLSpecAutocommitMiddleware` — same acquisition, but commits on 2xx responses and rolls back on anything else. Raising exceptions always rolls back and re-raises. `commit_mode="autocommit_include_redirect"` additionally commits 3xx.

See [commit-modes.md](commit-modes.md) for the full decision table and the `extra_commit_statuses` / `extra_rollback_statuses` knobs.

The plugin also conditionally adds two cross-cutting middlewares:

- `CorrelationMiddleware` — only when any config sets `enable_correlation_middleware=True`. Extracts a correlation ID from `x-request-id` (or configured fallback headers), propagates it into `CorrelationContext` (for driver-layer logs), stashes it on `request.state.correlation_id`, and echoes it back via `X-Correlation-ID` on the response.
- `SQLCommenterMiddleware` — on by default when the adapter has `statement_config.enable_sqlcommenter=True`. Annotates generated SQL with the route path, endpoint name, and framework tag so slow queries in the database's own logs can be traced back to the handler that issued them.

Both middlewares are additive and tap into existing driver-layer machinery — they don't change how you write handlers.

### Middleware order

`Starlette.add_middleware` prepends — the most recently added middleware runs outermost. Order of plugin operations at `init_app`:

1. The commit-mode middleware (`SQLSpecManualMiddleware` or `SQLSpecAutocommitMiddleware`) for each configured bind, in registration order. Each adds a layer; the first config registered ends up *innermost*.
2. `CorrelationMiddleware` (if any config enables it).
3. `SQLCommenterMiddleware` (if any config enables it).

So the runtime order, from outermost to innermost: sqlcommenter → correlation → last-registered bind's transaction middleware → ... → first-registered bind's transaction middleware → your route handler.

This matters when you add custom middleware of your own. If you need a connection available inside your middleware, add your middleware *before* constructing the plugin:

```python
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware

from sqlspec.extensions.starlette import SQLSpecPlugin


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        return await call_next(request)


app = Starlette()
app.add_middleware(AuditMiddleware)

db_plugin = SQLSpecPlugin(sqlspec, app)
```

`AuditMiddleware` runs *after* the commit-mode middleware (because the plugin prepends later), so by the time `dispatch` runs, `request.state.db_connection` is populated.

## Config

The `SQLSpec` class is the application-level registry. It holds one or more adapter configs; each config describes one logical database bind.

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "starlette": {
                "commit_mode": "autocommit",
                "connection_key": "db_connection",
                "session_key": "db_session",
                "pool_key": "db_pool",
            }
        },
    )
)
```

The per-config keys the plugin reads from `extension_config["starlette"]`:

| Key | Default | Purpose |
| --- | --- | --- |
| `connection_key` | `"db_connection"` | `request.state` slot holding the per-request raw connection. |
| `session_key` | `"db_session"` | `request.state` slot holding the cached per-request driver session. |
| `pool_key` | `"db_pool"` | `app.state` slot holding the shared pool. Auto-suffixed with `id(config)` for non-pooling adapters. |
| `commit_mode` | `"manual"` | `"manual"` / `"autocommit"` / `"autocommit_include_redirect"`. See [commit-modes.md](commit-modes.md). |
| `extra_commit_statuses` | `None` | Status codes that should commit even outside the mode's default window. |
| `extra_rollback_statuses` | `None` | Status codes that should roll back even on success. |
| `disable_di` | `False` | Skip middleware registration for this config (advanced — you manage sessions yourself). |
| `enable_correlation_middleware` | `False` | Turn on correlation-ID extraction + propagation. |
| `correlation_header` | `"x-request-id"` | Primary header the correlation extractor reads. |
| `correlation_headers` | `None` | Additional headers to probe as fallbacks. |
| `auto_trace_headers` | `True` | If true, the extractor also probes standard W3C tracing headers. |
| `enable_sqlcommenter_middleware` | `True` | Requires the adapter's `statement_config.enable_sqlcommenter` to also be true. |
| `sqlcommenter_framework` | `"starlette"` | Framework tag embedded in generated comments. |

Register a second config to talk to a second database — just give the second config distinct `connection_key` / `session_key` / `pool_key` values. The plugin validates uniqueness at `init_app` time and raises `ImproperConfigurationError` on duplicates. Per-bind wiring is covered in depth in [multi-database.md](multi-database.md).

## Session injection

Starlette has no built-in DI; handlers receive the raw request and fish their sessions out themselves. SQLSpec exposes `get_session(request, key=None)` and `get_connection(request, key=None)` on the plugin for exactly this.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from sqlspec.adapters.asyncpg import AsyncpgDriver


async def list_orders(request: Request) -> JSONResponse:
    db: AsyncpgDriver = db_plugin.get_session(request)
    rows = await db.select("SELECT id, status, amount FROM orders ORDER BY id")
    return JSONResponse({"orders": rows})
```

`get_session` caches the driver session per-request — the first call builds it from the connection stashed on `request.state` and stores the instance under `f"{session_key}_instance"`. Subsequent calls in the same request return the same object, so two cooperating services in the same handler see the same transactional view.

`get_connection` returns the raw driver connection (the asyncpg `Connection`, the aiosqlite connection, etc.) — use this only when you need a driver-specific feature that `select` / `execute` / `insert` don't wrap.

When you have multiple configs, pass the `key`:

```python
async def daily_report(request: Request) -> JSONResponse:
    primary = db_plugin.get_session(request, "db_session")
    analytics = db_plugin.get_session(request, "analytics_session")
    ...
```

The lookup matches against each config's `session_key`, not the `connection_key` — the two share a namespace inside the plugin.

### Reading `request.state` directly

The plugin stores the raw connection at `request.state.<connection_key>` and the cached driver session at `request.state.<session_key>_instance` (the `_instance` suffix is added by `get_or_create_session`). For most code, prefer `db_plugin.get_session(request)` — it handles the cache lookup, the build path, and the multi-bind dispatch for you. Read from `request.state` directly only in middleware that runs inside the SQLSpec transaction middleware, where you may want to peek at the connection without invoking the driver-build machinery.

```python
from starlette.middleware.base import BaseHTTPMiddleware


class LogConnectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        conn = getattr(request.state, "db_connection", None)
        if conn is not None:
            # do something driver-specific
            pass
        return await call_next(request)
```

Register this middleware before constructing the plugin so it wraps the transaction middleware (and therefore runs *after* the connection has been stored).

## Filters / providers

Starlette's no-DI posture means the filter helpers don't get the same parameter-injection treatment they do under FastAPI. The SQLSpec filter objects themselves work unchanged — you build them from query params yourself.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from sqlspec import sql
from sqlspec.core import LimitOffsetFilter, SearchFilter


async def list_orders(request: Request) -> JSONResponse:
    db = db_plugin.get_session(request)
    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 20))
    search = request.query_params.get("search")

    filters = [LimitOffsetFilter(limit=page_size, offset=page_size * (page - 1))]
    if search:
        filters.append(SearchFilter(field_name={"customer_name"}, value=search))

    stmt = sql.select("*").from_("orders")
    for flt in filters:
        stmt = flt.append_to_statement(stmt)

    rows = await db.select(stmt)
    return JSONResponse({"orders": rows})
```

The filter objects themselves (`LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `BeforeAfterFilter`, `InCollectionFilter`, `NotInCollectionFilter`, `NullFilter`, `NotNullFilter`) are the same across frameworks — they live in `sqlspec.core`. See [filters.md](filters.md) for the full catalog and `append_to_statement` semantics.

If you want the FastAPI-style `provide_filters(FilterConfig(...))` dependency generator, you need to move to FastAPI — it builds the dependency function dynamically around `Depends`, which is a FastAPI construct. In plain Starlette, parse query params in the handler (as above) or extract to a helper of your own.

## Migrations / CLI

SQLSpec exposes one unified migrations CLI that reads the registry the framework extensions read. Per-framework shims don't exist — you invoke the global CLI against your configured registry.

```bash
# Using `uv` (recommended)
uv run sqlspec database upgrade

# Or, in an activated venv
sqlspec database upgrade
```

The CLI walks `sqlspec.configs.values()` and for each config with `migration_config={...}` runs the pending migrations against that bind's pool. Each bind keeps its own version table; there is no shared history across binds.

To make the CLI see your registry, point it at a Python attribute via `SQLSPEC_APP=package.module:sqlspec` (or the equivalent `--config` flag). The adapter configs and their `extension_config` blocks work the same way regardless of which framework the process happens to be serving. See [migrations.md](migrations.md) for command reference, revision authoring, and rollback semantics.

## Example: full working handler

```python
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
from sqlspec.extensions.starlette import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "starlette": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
                "pool_key": "db_pool",
            }
        },
    )
)

db_plugin = SQLSpecPlugin(sqlspec)


async def list_orders(request: Request) -> JSONResponse:
    db: AsyncpgDriver = db_plugin.get_session(request)
    rows = await db.select(
        "SELECT id, status, amount FROM orders WHERE status = $1 ORDER BY id",
        ["pending"],
    )
    return JSONResponse({"orders": rows})


async def create_order(request: Request) -> JSONResponse:
    payload = await request.json()
    db: AsyncpgDriver = db_plugin.get_session(request)
    result = await db.execute(
        "INSERT INTO orders (customer_id, status, amount) VALUES ($1, $2, $3) RETURNING id",
        [payload["customer_id"], "pending", payload["amount"]],
    )
    return JSONResponse({"id": result.one()["id"]}, status_code=201)


app = Starlette(
    routes=[
        Route("/orders", list_orders, methods=["GET"]),
        Route("/orders", create_order, methods=["POST"]),
    ]
)
db_plugin.init_app(app)
```

What happens on a `POST /orders`:

1. Starlette's ASGI loop starts the request scope. On the first request after startup, the plugin's `lifespan` context has already created the asyncpg pool and stored it on `app.state.db_pool`.
2. `SQLSpecAutocommitMiddleware.dispatch` runs. It pulls the pool off `app.state`, acquires a connection via `config.provide_connection(pool)`, and stores it on `request.state.db_connection`.
3. The router dispatches to `create_order`. The handler calls `db_plugin.get_session(request)`, which looks up the connection on `request.state`, builds an `AsyncpgDriver` around it (or returns the cached one), and returns it.
4. The handler runs `INSERT ... RETURNING id`. The middleware hasn't committed anything yet — it's still inside the `async with` block.
5. The handler returns a `201`. Back in the middleware, `_should_commit(201)` is `True` (2xx window), so the middleware calls `await connection.commit()`.
6. The middleware exits the `async with` block, releasing the connection back to the pool. The response flows out to the client.

If step 4 had raised an exception, the middleware would have caught it, called `await connection.rollback()`, released the connection, and re-raised. If the handler had returned `422`, the middleware would have rolled back (not committed) and returned the response normally.

## Cross-links

- [commit-modes.md](commit-modes.md) — full behavior of `SQLSpecAutocommitMiddleware` vs `SQLSpecManualMiddleware`, including `extra_commit_statuses` / `extra_rollback_statuses`.
- [multi-database.md](multi-database.md) — per-config `connection_key` / `session_key` / `pool_key` for applications talking to more than one database.
- [filters.md](filters.md) — the filter object catalog (`LimitOffsetFilter`, `SearchFilter`, `OrderByFilter`, `BeforeAfterFilter`, `InCollectionFilter`).
- [adapters.md](adapters.md) — adapter-specific pool config (`min_size` / `max_size` / `conninfo` / `dsn`).
- [migrations.md](migrations.md) — the global `sqlspec database ...` migration CLI and how it reads the registry.
- [observability.md](observability.md) — correlation middleware, sqlcommenter middleware, and how they thread request context into driver-layer logs.
- [fastapi-integration.md](fastapi-integration.md) — the DI-oriented sibling built on this same plugin class.
- [flask-integration.md](flask-integration.md) — sync WSGI variant with the portal bridge for async drivers.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public apps that demonstrate end-to-end SQLSpec configuration.
