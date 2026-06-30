# Flask integration

SQLSpec's Flask extension hooks into Flask's request lifecycle via `before_request`, `after_request`, and `teardown_appcontext`. Sessions are pull-based — handlers call `plugin.get_session()` to retrieve the session bound to the current request (stored on `flask.g`). The extension supports both sync adapters (the common Flask shape) and async adapters via a portal pattern that bridges sync call-sites to a background event-loop thread. For async ASGI apps see [fastapi-integration.md](fastapi-integration.md) or [starlette-integration.md](starlette-integration.md).

## Install

```bash
pip install 'sqlspec[flask]'
```

The `flask` extra pulls in `flask` itself. Install an adapter extra alongside — `sqlspec[flask,sqlite]` for SQLite, `sqlspec[flask,psycopg]` for sync Postgres, and so on. If you want to call an async adapter from Flask routes, install its extra and let the plugin's portal do the bridging — `sqlspec[flask,aiosqlite]`, `sqlspec[flask,asyncpg]`.

## Entry point

```python
from flask import Flask

from sqlspec import SQLSpec
from sqlspec.adapters.sqlite import SqliteConfig
from sqlspec.extensions.flask import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    SqliteConfig(
        connection_config={"database": "app.db"},
        extension_config={
            "flask": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
            }
        },
    )
)

app = Flask(__name__)
plugin = SQLSpecPlugin(sqlspec, app)
```

Two forms work:

1. **Eager** — `SQLSpecPlugin(sqlspec, app)` introspects the registry and wires the app immediately. Good for the simple single-file pattern.
2. **Factory / deferred** — construct the plugin at module scope, then call `plugin.init_app(app)` inside `create_app()`. This is the canonical Flask pattern; the plugin is designed for it.

```python
from flask import Flask

from sqlspec import SQLSpec
from sqlspec.adapters.sqlite import SqliteConfig
from sqlspec.extensions.flask import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(SqliteConfig(connection_config={"database": "app.db"}))
plugin = SQLSpecPlugin(sqlspec)


def create_app() -> Flask:
    app = Flask(__name__)
    plugin.init_app(app)
    return app
```

Registering the plugin twice raises `ImproperConfigurationError` — the plugin sets `app.extensions["sqlspec"]` and refuses to overwrite it.

## Lifecycle

`init_app` does four things, in order:

1. **Validates unique keys.** If two configs share a `session_key` or `connection_key`, it raises `ImproperConfigurationError`. The Flask plugin doesn't use a separate `pool_key` — pools are stored in `app.extensions["sqlspec"]["pools"]` keyed by `session_key`.
2. **Starts the portal** (only when any registered config is async). The `PortalProvider` runs a daemon thread with its own event loop; sync Flask routes call into async code through `portal.call(...)`. Sync-only apps skip this — no thread, no overhead.
3. **Creates pools.** For each config with `supports_connection_pooling=True`, calls `config.create_pool()` (or `portal.call(config.create_pool)` for async) and stores the pool on `app.extensions["sqlspec"]["pools"][session_key]`.
4. **Registers request hooks.** For each config where `disable_di` is false:
   - `before_request(self._before_request_handler)` — acquires a connection from the pool (or creates one if the adapter doesn't pool) and stores it on `flask.g` under `connection_key`. For async adapters, the portal calls `conn_ctx.__aenter__()` on the background loop and stores the context manager for the teardown hook to close.
   - `after_request(self._after_request_handler)` — reads the response status code. Under `autocommit`, commits on 2xx (and 3xx for `autocommit_include_redirect`), rolls back otherwise. Under `manual`, does nothing.
   - `teardown_appcontext(self._teardown_appcontext_handler)` — closes the connection (or exits its context manager). Runs whether the request succeeded or raised.
5. **Registers an `atexit` shutdown hook** that closes all pools and stops the portal thread on interpreter exit.

Transaction modes are the same three values as the ASGI extensions — `"manual"`, `"autocommit"`, `"autocommit_include_redirect"` — with the same 2xx / 3xx semantics. See [commit-modes.md](commit-modes.md) for the full decision table.

When `enable_correlation_middleware=True` on any config, the `before_request` handler extracts a correlation ID from headers (primary `x-request-id`, plus any configured fallbacks and W3C trace headers), propagates it into `CorrelationContext` so driver-layer logs pick it up, stores it on `g.correlation_id`, and the `after_request` handler stamps `X-Correlation-ID` on the response.

When `enable_sqlcommenter_middleware=True` (and the adapter has `statement_config.enable_sqlcommenter=True`), the plugin sets `SQLCommenterContext` on each request with the current route and endpoint name. The driver wraps every SQL statement with a comment carrying those attributes. Details in [observability.md](observability.md).

## Config

```python
from sqlspec import SQLSpec
from sqlspec.adapters.sqlite import SqliteConfig

sqlspec = SQLSpec()
sqlspec.add_config(
    SqliteConfig(
        connection_config={"database": "app.db"},
        extension_config={
            "flask": {
                "commit_mode": "autocommit",
                "connection_key": "db_connection",
                "session_key": "db_session",
            }
        },
    )
)
```

Per-config keys the plugin reads from `extension_config["flask"]`:

| Key | Default | Purpose |
| --- | --- | --- |
| `connection_key` | `"sqlspec_connection_<session_key>"` | `flask.g` attribute holding the per-request connection. |
| `session_key` | `"db_session"` | Logical bind name. Used for the pool slot, the `get_session` lookup key, and the session-cache key. |
| `commit_mode` | `"manual"` | `"manual"` / `"autocommit"` / `"autocommit_include_redirect"`. |
| `extra_commit_statuses` | `None` | Extra status codes that trigger commit. |
| `extra_rollback_statuses` | `None` | Extra status codes that trigger rollback. |
| `disable_di` | `False` | Skip request hooks for this config — you own the lifecycle. |
| `enable_correlation_middleware` | `False` | Turn on correlation-ID extraction + response stamping. |
| `correlation_header` | `"x-request-id"` | Primary correlation header name. |
| `correlation_headers` | `None` | Additional fallback headers. |
| `auto_trace_headers` | `True` | Also probe W3C trace headers. |
| `enable_sqlcommenter_middleware` | `True` | Needs `statement_config.enable_sqlcommenter=True` on the adapter. |

Note: there's no `pool_key` on the Flask extension. Pools are keyed by `session_key` in `app.extensions["sqlspec"]["pools"]`.

For multi-bind, give each config a distinct `session_key` (and, since `connection_key` defaults to `f"sqlspec_connection_{session_key}"`, the connection key auto-derives correctly). The per-bind model is covered in [multi-database.md](multi-database.md).

## Session injection (pull-based)

Flask has no DI system; handlers fetch their dependencies. The plugin exposes `get_session(key=None)` for that.

```python
from flask import Flask

from sqlspec.adapters.sqlite import SqliteDriver

app = Flask(__name__)


@app.get("/orders")
def list_orders() -> dict:
    db: SqliteDriver = plugin.get_session()
    rows = db.select("SELECT id, status, amount FROM orders ORDER BY id")
    return {"orders": rows}
```

How the lookup works under the hood:

1. The handler calls `plugin.get_session()`.
2. The plugin picks the first registered config (no key) or looks up the config whose `session_key` matches (with a key).
3. It checks `g.sqlspec_session_cache_<session_key>` — if a session is already built for this request, returns it.
4. Otherwise it reads the connection off `g` (at `connection_key`) and instantiates the driver (`config.driver_type(connection=..., statement_config=...)`).
5. Caches the driver on `g` under the cache key and returns it.

Two `get_session()` calls in the same request return the same driver instance, so they share the same connection (and, under `autocommit`, the same transaction).

For multi-bind, pass the session key:

```python
@app.get("/dashboard")
def dashboard() -> dict:
    primary: SqliteDriver = plugin.get_session("primary_session")
    reports: SqliteDriver = plugin.get_session("reports_session")
    live = primary.select("SELECT COUNT(*) AS n FROM orders WHERE status = 'open'")
    snapshot = reports.select("SELECT * FROM daily_snapshot ORDER BY day DESC LIMIT 7")
    return {"live": live[0], "snapshot": snapshot}
```

`get_connection(key=None)` returns the raw driver connection (the `sqlite3.Connection`, the psycopg `Connection`, or, for async adapters, the native connection object the portal already entered).

### `current_app` and the app-context requirement

`get_session` reads `flask.g`, which is tied to Flask's application context. Inside a request handler the context is set up for you. Outside a request (a CLI command, a background thread started by your app, a test that runs without the test client), you must push a context first:

```python
from flask import current_app


def backfill_orders() -> None:
    app = current_app._get_current_object()
    with app.app_context():
        db = plugin.get_session()
        db.execute("UPDATE orders SET migrated = 1 WHERE migrated IS NULL")
```

Inside the `with app.app_context()` block, the plugin still runs the `before_request`/`teardown_appcontext` hooks via `current_app.ensure_sync` — which means the transaction lifecycle does happen (with `commit_mode="manual"` nothing commits automatically, so you're responsible for `connection.commit()` if you want to persist changes).

### Blueprints

Blueprints are Flask's unit of route organization. They compose cleanly with the plugin — the plugin registers handlers on the `app`, not on blueprints, so blueprint routes pick up DB wiring automatically.

```python
from flask import Blueprint, Flask

from sqlspec.adapters.sqlite import SqliteDriver

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.get("/")
def list_orders() -> dict:
    db: SqliteDriver = plugin.get_session()
    rows = db.select("SELECT id, status FROM orders")
    return {"orders": rows}


@orders_bp.post("/")
def create_order() -> tuple[dict, int]:
    from flask import request

    payload = request.get_json()
    db: SqliteDriver = plugin.get_session()
    result = db.execute(
        "INSERT INTO orders (customer_id, status, amount) VALUES (?, ?, ?) RETURNING id",
        payload["customer_id"],
        "pending",
        payload["amount"],
    )
    return {"id": result.one()["id"]}, 201


def create_app() -> Flask:
    app = Flask(__name__)
    plugin.init_app(app)
    app.register_blueprint(orders_bp)
    return app
```

Under `commit_mode="autocommit"`, the `POST /orders/` returning 201 triggers a commit; a `raise` inside the handler rolls back.

## Filters / providers

Flask's lack of DI means the plugin does not generate filter dependencies the way the FastAPI extension does. You build filters from request query args in the handler:

```python
from flask import Flask, request

from sqlspec import sql
from sqlspec.adapters.sqlite import SqliteDriver
from sqlspec.core import LimitOffsetFilter, OrderByFilter, SearchFilter


@app.get("/orders")
def list_orders() -> dict:
    db: SqliteDriver = plugin.get_session()

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    search = request.args.get("search")
    sort_order = request.args.get("sort_order", "desc")

    filters = [
        LimitOffsetFilter(limit=page_size, offset=page_size * (page - 1)),
        OrderByFilter(field_name="created_at", sort_order=sort_order),
    ]
    if search:
        filters.append(SearchFilter(field_name={"customer_name"}, value=search, ignore_case=True))

    stmt = sql.select("*").from_("orders")
    for flt in filters:
        stmt = flt.append_to_statement(stmt)

    rows = db.select(stmt)
    return {"orders": rows}
```

The filter objects are the same as in every other framework — defined in `sqlspec.core`, consumed via `append_to_statement`. See [filters.md](filters.md) for the catalog (`LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `BeforeAfterFilter`, `InCollectionFilter`, `NotInCollectionFilter`, `NullFilter`, `NotNullFilter`).

If you want the FastAPI-style auto-generated filter query parameters with an OpenAPI schema out of the box, that feature lives in the FastAPI extension because it depends on `Depends` — see [fastapi-integration.md](fastapi-integration.md).

## Async adapters via portal

The non-obvious piece of the Flask extension: it supports async adapters (asyncpg, aiosqlite, psycopg-async) from sync Flask routes by running the adapter's async methods on a background event loop.

The mechanism is `PortalProvider` — a daemon thread started by `init_app` whenever any registered config is async. The thread owns an `asyncio` event loop; `portal.call(coro, *args, **kwargs)` enqueues the coroutine, wakes the loop, blocks the calling thread on a `queue.Queue` until the coroutine returns (or raises), and surfaces the result.

From the handler's perspective, nothing changes. You still call `plugin.get_session()` and get back a driver. The driver's `execute`/`select`/`insert` methods, however, internally need to await async DB operations. The Flask plugin handles this by wrapping the driver in a bridge that forwards async calls through the portal.

```python
from flask import Flask

from sqlspec import SQLSpec
from sqlspec.adapters.aiosqlite import AiosqliteConfig, AiosqliteDriver
from sqlspec.extensions.flask import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    AiosqliteConfig(
        connection_config={"database": "app.db"},
        extension_config={
            "flask": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
            }
        },
    )
)

plugin = SQLSpecPlugin(sqlspec)


def create_app() -> Flask:
    app = Flask(__name__)
    plugin.init_app(app)

    @app.get("/orders")
    def list_orders() -> dict:
        db: AiosqliteDriver = plugin.get_session()
        rows = db.select("SELECT id, status FROM orders")
        return {"orders": rows}

    return app
```

When does the portal get started? The plugin's `__init__` walks the registry and sets `_has_async_configs = True` if any config is an `AsyncDatabaseConfig` or `NoPoolAsyncConfig`. `init_app` then creates a `PortalProvider` and calls `.start()` before creating pools. Pools for async configs are created via `portal.call(config.create_pool)`. Connections are similarly acquired: `portal.call(conn_ctx.__aenter__)` on the way in, `portal.call(conn_ctx.__aexit__, None, None, None)` on the way out.

**When to use async-via-portal vs a sync adapter:**

- **Use a sync adapter** (sqlite3, psycopg sync, oracledb thick) if the synchronous driver is a first-class option. Less machinery, no cross-thread hop per query, no portal thread sitting idle.
- **Use an async adapter via portal** when the only production-quality driver for your database is async (asyncpg for Postgres is the canonical case) or when you want to share the same adapter configuration between a Flask admin interface and a FastAPI/Starlette API.

**Portal gotchas:**

- **Every DB call takes one cross-thread hop.** For latency-sensitive paths, the synchronous alternative is meaningfully faster.
- **Don't start your own event loop on the request thread.** The portal already owns one. `asyncio.run` or `asyncio.get_event_loop` from a handler will fight the portal.
- **Pool sizing is still per-config.** The portal doesn't multiply connections — it just forwards calls into the async pool.
- **Shutdown must go through the plugin.** `atexit` closes pools and stops the portal in the right order. Don't manually `asyncio.run` the pool's `close_pool()` from another thread.

## Migrations / CLI

SQLSpec has a single migrations CLI that is framework-neutral. There is no per-framework subcommand.

```bash
uv run sqlspec database upgrade
uv run sqlspec database current
uv run sqlspec database downgrade -n 1
uv run sqlspec database revision -m "add orders table"
```

Point the CLI at your registry via `SQLSPEC_APP=package.module:sqlspec`. The CLI iterates `sqlspec.configs.values()` and for each config with a `migration_config={...}` block runs the pending scripts against that bind's pool. Each bind keeps its own version table. For async configs, the CLI uses its own portal (sync entrypoint → async adapter), independent of the plugin's portal — this is transparent to you.

See [migrations.md](migrations.md) for command reference, revision authoring, and rollback semantics.

## Example: full working handler

```python
from flask import Flask, request

from sqlspec import SQLSpec, sql
from sqlspec.adapters.sqlite import SqliteConfig, SqliteDriver
from sqlspec.core import LimitOffsetFilter, OrderByFilter, SearchFilter
from sqlspec.extensions.flask import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    SqliteConfig(
        connection_config={"database": "app.db"},
        extension_config={
            "flask": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
            }
        },
    )
)

plugin = SQLSpecPlugin(sqlspec)


def create_app() -> Flask:
    app = Flask(__name__)
    plugin.init_app(app)

    @app.get("/orders")
    def list_orders() -> dict:
        db: SqliteDriver = plugin.get_session()

        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        search = request.args.get("search")

        filters = [
            LimitOffsetFilter(limit=page_size, offset=page_size * (page - 1)),
            OrderByFilter(field_name="created_at", sort_order="desc"),
        ]
        if search:
            filters.append(SearchFilter(field_name={"customer_name"}, value=search, ignore_case=True))

        stmt = sql.select("*").from_("orders")
        for flt in filters:
            stmt = flt.append_to_statement(stmt)

        rows = db.select(stmt)
        return {"orders": rows}

    @app.post("/orders")
    def create_order() -> tuple[dict, int]:
        payload = request.get_json() or {}
        if "customer_id" not in payload or "amount" not in payload:
            return {"detail": "customer_id and amount required"}, 422

        db: SqliteDriver = plugin.get_session()
        result = db.execute(
            "INSERT INTO orders (customer_id, status, amount) VALUES (?, ?, ?) RETURNING id",
            payload["customer_id"],
            "pending",
            payload["amount"],
        )
        return {"id": result.one()["id"]}, 201

    return app


app = create_app()
```

Request flow for `POST /orders`:

1. Flask enters the request context. `before_request` runs — the plugin pulls the pool from `app.extensions["sqlspec"]["pools"]["db_session"]`, acquires a connection via `config.provide_connection(pool).__enter__()`, and stores it on `g.sqlspec_connection_db_session` (the auto-derived connection key).
2. The handler validates the payload; returns 422 immediately if it's bad — in which case `after_request` reads the 422 status and rolls back (an empty transaction, but the commit is skipped).
3. The handler calls `plugin.get_session()`. The plugin reads the connection off `g`, wraps it in a `SqliteDriver`, caches the driver on `g.sqlspec_session_cache_db_session`, and returns it.
4. The handler runs `INSERT ... RETURNING id` and returns `({"id": ...}, 201)`.
5. `after_request` sees 201, calls `connection.commit()`.
6. Flask sends the response. `teardown_appcontext` runs — calls `conn_ctx.__exit__(None, None, None)` which releases the connection back to the pool, then pops the `g` entries.

Request flow for `GET /orders?page=2&page_size=25&search=acme`:

1. `before_request` acquires a connection.
2. The handler parses `page=2, page_size=25, search="acme"`, builds three filters, folds them into the statement (`LIMIT 25 OFFSET 25`, `ORDER BY created_at DESC`, `WHERE customer_name LIKE '%acme%'`).
3. `db.select(stmt)` executes and returns rows.
4. Handler returns 200. `after_request` commits (2xx under autocommit). `teardown_appcontext` releases the connection.

## Cross-links

- [commit-modes.md](commit-modes.md) — commit/rollback decision table and `extra_commit_statuses` / `extra_rollback_statuses` knobs.
- [multi-database.md](multi-database.md) — multi-bind patterns, per-config `session_key` / `connection_key`, async + sync mixing in one app.
- [filters.md](filters.md) — filter objects (`LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `BeforeAfterFilter`, `InCollectionFilter`, `NotInCollectionFilter`, `NullFilter`, `NotNullFilter`).
- [adapters.md](adapters.md) — adapter-specific pool configuration.
- [migrations.md](migrations.md) — the global `sqlspec database ...` CLI.
- [observability.md](observability.md) — correlation and sqlcommenter hooks, correlation extraction from headers.
- [starlette-integration.md](starlette-integration.md) — the async ASGI sibling for plain Starlette apps.
- [fastapi-integration.md](fastapi-integration.md) — the async ASGI sibling with DI-driven handlers and filter generation.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public canonical apps ([litestar-sqlstack](https://github.com/cofin/litestar-sqlstack), [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo)).
