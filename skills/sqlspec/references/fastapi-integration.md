# FastAPI integration

SQLSpec's FastAPI extension is a thin subclass of the Starlette plugin that adds FastAPI-native dependency providers on top of the same middleware, lifespan wiring, and per-config key model. This guide covers handler-level DI via `Depends`, filter-parameter generation via `provide_filters`, and the multi-database / multi-bind scenarios where typed dependencies really pay off. For non-FastAPI ASGI apps see [starlette-integration.md](starlette-integration.md); for WSGI Flask see [flask-integration.md](flask-integration.md).

## Install

```bash
pip install 'sqlspec[fastapi]'
```

The `fastapi` extra depends on `starlette` transitively — the extension imports directly from `sqlspec.extensions.starlette.extension` and `starlette.middleware.base`. Install an adapter extra alongside — `sqlspec[fastapi,asyncpg]` for Postgres via asyncpg, `sqlspec[fastapi,aiosqlite]` for local SQLite, `sqlspec[fastapi,oracledb]` for Oracle, and so on.

## Entry point

```python
from fastapi import FastAPI

from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.fastapi import SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "fastapi": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
            }
        },
    )
)

app = FastAPI()
db_plugin = SQLSpecPlugin(sqlspec, app)
```

Key observations:

1. The config lives under `extension_config["fastapi"]`. Starlette apps use `extension_config["starlette"]`; declare both blocks only when the same adapter config is shared by both integrations.
2. `SQLSpecPlugin(sqlspec, app)` eagerly wires the plugin: it registers the lifespan and adds the commit-mode middleware. The two-step form `plugin = SQLSpecPlugin(sqlspec); plugin.init_app(app)` works the same; use it when you build the registry at module scope and attach the plugin inside a factory.
3. The plugin is the handle you pass around your application — most downstream code only needs `db_plugin.provide_session()` and `db_plugin.provide_filters(...)`.

## Lifecycle

Because the FastAPI plugin extends the Starlette plugin, its lifecycle is identical. `init_app` wraps `app.router.lifespan_context`, so pool creation and shutdown happen inside FastAPI's own lifespan phase:

```python
@asynccontextmanager
async def combined_lifespan(app):
    async with db_plugin.lifespan(app), original_lifespan(app):
        yield
```

Per-request wiring uses the same two middleware variants:

- `SQLSpecManualMiddleware` — acquires a connection from the pool, stashes it on `request.state` under `connection_key`, releases on exit. Transaction boundaries are your responsibility.
- `SQLSpecAutocommitMiddleware` — same acquisition; commits on 2xx (and on 3xx when `commit_mode="autocommit_include_redirect"`), rolls back on everything else or on raised exceptions.

See [commit-modes.md](commit-modes.md) for the status-code decision table.

The plugin also conditionally adds `CorrelationMiddleware` (if any config sets `enable_correlation_middleware=True`) and `SQLCommenterMiddleware` (if the adapter has `statement_config.enable_sqlcommenter=True`). Both are additive — they thread correlation IDs and route metadata into driver logs without touching handler signatures. Details are in [observability.md](observability.md).

A note on middleware ordering: FastAPI's `app.add_middleware` prepends middleware (the most recently added runs outermost). Because the SQLSpec plugin adds its transaction middleware during `init_app`, any `app.add_middleware(...)` calls you make *after* `SQLSpecPlugin(sqlspec, app)` will run *before* the transaction middleware — meaning those middlewares do not yet have a DB connection on `request.state`. If you need to read a connection inside custom middleware, register it before constructing the plugin.

## Config

The `SQLSpec` class is the application-level registry. Add each config via `sqlspec.add_config(...)`, then construct the plugin with the registry.

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "fastapi": {
                "commit_mode": "autocommit",
                "connection_key": "db_connection",
                "session_key": "db_session",
                "pool_key": "db_pool",
            }
        },
    )
)
```

The keys the plugin reads from `extension_config["fastapi"]`:

| Key | Default | Purpose |
| --- | --- | --- |
| `connection_key` | `"db_connection"` | `request.state` slot holding the per-request raw connection. |
| `session_key` | `"db_session"` | `request.state` slot holding the cached per-request driver session. Also the lookup key for `provide_session("...")`. |
| `pool_key` | `"db_pool"` | `app.state` slot holding the shared pool. |
| `commit_mode` | `"manual"` | `"manual"` / `"autocommit"` / `"autocommit_include_redirect"`. |
| `extra_commit_statuses` | `None` | Extra status codes that should commit (e.g. `{418}` for a custom success). |
| `extra_rollback_statuses` | `None` | Extra status codes that should roll back. |
| `disable_di` | `False` | Skip middleware for this config entirely. |
| `enable_correlation_middleware` | `False` | Turn on the correlation ID extractor. |
| `correlation_header` | `"x-request-id"` | Primary correlation header. |
| `correlation_headers` | `None` | Additional correlation header fallbacks. |
| `auto_trace_headers` | `True` | Also probe W3C trace headers as fallbacks. |
| `enable_sqlcommenter_middleware` | `True` | Requires `statement_config.enable_sqlcommenter=True` on the adapter. |
| `sqlcommenter_framework` | `"starlette"` | Framework tag in generated SQL comments. Override to `"fastapi"` if you want it in logs. |

For multi-database applications, give each config a distinct `connection_key` / `session_key` / `pool_key`. The plugin raises `ImproperConfigurationError` on duplicates at `init_app`. The full per-bind model is in [multi-database.md](multi-database.md).

## Session injection

FastAPI's dependency injection is driven by `Depends`. The plugin exposes three families of dependency factories:

- `provide_session(key=None)` — returns a callable that resolves to the driver session (the most common shape).
- `provide_connection(key=None)` — returns a callable that resolves to the raw connection (for driver-specific escape hatches).
- `provide_async_session(key)` / `provide_sync_session(key)` — type-narrowed variants for when you're using a string key and need the static type-checker to know whether the config is async or sync.

### Async session with `Annotated`

```python
from typing import Annotated, Any

from fastapi import Depends, FastAPI

from sqlspec.adapters.asyncpg import AsyncpgDriver

app = FastAPI()


@app.get("/orders")
async def list_orders(
    db: Annotated[AsyncpgDriver, Depends(db_plugin.provide_session())],
) -> dict[str, Any]:
    rows = await db.select("SELECT id, status, amount FROM orders")
    return {"orders": rows}
```

`provide_session()` returns a fresh callable every time you call it. Cache it at module scope if you want `Depends` to deduplicate — FastAPI keys its cache on the function identity, so two distinct `provide_session()` returns are treated as two distinct dependencies and called twice per request. The difference is real only if you also pass `use_cache=False`, but caching at module scope is the cleaner posture regardless:

```python
SessionDep = Annotated[AsyncpgDriver, Depends(db_plugin.provide_session())]


@app.get("/orders/{order_id}")
async def get_order(order_id: int, db: SessionDep) -> dict[str, Any]:
    rows = await db.select("SELECT * FROM orders WHERE id = $1", order_id)
    return {"order": rows[0] if rows else None}
```

### String key for multi-bind

```python
from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.adapters.sqlite import SqliteDriver


@app.get("/report")
async def daily_report(
    primary: Annotated[AsyncpgDriver, Depends(db_plugin.provide_session("db_session"))],
    reports: Annotated[SqliteDriver, Depends(db_plugin.provide_session("reports_session"))],
) -> dict[str, Any]:
    orders = await primary.select("SELECT COUNT(*) AS n FROM orders")
    snapshot = reports.select("SELECT * FROM daily_snapshot ORDER BY day DESC LIMIT 1")
    return {"orders": orders, "snapshot": snapshot}
```

The string key matches against each config's `session_key`. With no key argument, the plugin uses the first registered config — fine for single-bind apps, explicit is better for multi-bind.

### Type-narrowed factories

`provide_session()` returns a `Callable[[Request], AsyncDriverAdapterBase | SyncDriverAdapterBase]` — the union type means type checkers can't tell whether `await db.execute(...)` is valid. Two workarounds:

1. **`Annotated` type annotation** — type the parameter explicitly (`Annotated[AsyncpgDriver, Depends(...)]`). The annotation narrows the type locally; `Depends` itself doesn't need to know.
2. **`provide_async_session` / `provide_sync_session`** — these dependency factories return callables typed as the async or sync driver base respectively, so you skip the union.

```python
from sqlspec.driver import AsyncDriverAdapterBase


@app.get("/typed")
async def typed_query(
    db: Annotated[AsyncDriverAdapterBase, Depends(db_plugin.provide_async_session())],
) -> dict[str, Any]:
    return {"ok": True}
```

The `provide_session(config_instance)` and `provide_session(ConfigClass)` overloads exist for the same narrowing purpose — the plugin ignores the value at runtime but the overload resolution picks the right return type for static analysis. All four shapes — `None`, `str`, config instance, config class — produce the same runtime behavior.

### Raw connection

Use `provide_connection()` when you need a driver-native feature that the session wrapper doesn't expose — e.g. asyncpg's `prepare()` API, or oracledb's `callproc`.

```python
from typing import Annotated, Any

import asyncpg
from fastapi import Depends


@app.get("/prepared")
async def prepared_query(
    conn: Annotated[asyncpg.Connection, Depends(db_plugin.provide_connection())],
) -> dict[str, Any]:
    stmt = await conn.prepare("SELECT id, status FROM orders WHERE id = $1")
    row = await stmt.fetchrow(42)
    return {"row": dict(row) if row else None}
```

Note: when using a raw connection, the middleware still owns the transaction (commit on 2xx under `autocommit`). You can interleave `db.execute(...)` and `conn.prepare(...)` in the same handler — they share the same connection and the same transaction.

## Filters / providers

The FastAPI extension's killer feature is `provide_filters(FilterConfig(...))` — a dynamic dependency-function generator that builds a FastAPI-compatible callable whose signature advertises filter query parameters to FastAPI. FastAPI reflects on the signature to produce the OpenAPI schema, so the resulting parameters show up in the generated docs for free.

```python
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from sqlspec import sql
from sqlspec.core import FilterTypes
from sqlspec.extensions.fastapi import FilterConfig


order_filters = db_plugin.provide_filters(
    FilterConfig(
        id_filter=UUID,
        search="customer_name,notes",
        search_ignore_case=True,
        pagination_type="limit_offset",
        pagination_size=25,
        sort_field="created_at",
        sort_order="desc",
        created_at=True,
    )
)


@app.get("/orders")
async def list_orders(
    db: Annotated[AsyncpgDriver, Depends(db_plugin.provide_session())],
    filters: Annotated[list[FilterTypes], Depends(order_filters)],
) -> dict[str, Any]:
    stmt = sql.select("*").from_("orders")
    for flt in filters:
        stmt = flt.append_to_statement(stmt)
    rows = await db.select(stmt)
    return {"orders": rows}
```

What the filter keys advertise as query parameters:

| Config key | Query parameter(s) | Filter produced |
| --- | --- | --- |
| `id_filter=UUID` | `?ids=<uuid>&ids=<uuid>` | `InCollectionFilter(field_name="id", values=[...])` |
| `created_at=True` | `?createdBefore=<iso>&createdAfter=<iso>` | `BeforeAfterFilter(field_name="created_at", before=..., after=...)` |
| `updated_at=True` | `?updatedBefore=<iso>&updatedAfter=<iso>` | `BeforeAfterFilter(field_name="updated_at", ...)` |
| `pagination_type="limit_offset"` | `?currentPage=<n>&pageSize=<n>` | `LimitOffsetFilter(limit=page_size, offset=page_size * (currentPage - 1))` |
| `search="col1,col2"` | `?searchString=<q>&searchIgnoreCase=<bool>` | `SearchFilter(field_name={"col1","col2"}, value=q, ignore_case=...)` |
| `sort_field="created_at"` | `?orderBy=<col>&sortOrder=<asc\|desc>` | `OrderByFilter(field_name=col, sort_order=...)` |
| `in_fields=FieldNameType("status", str)` | `?statusIn=<v>&statusIn=<v>` | `InCollectionFilter(field_name="status", values={...})` |
| `not_in_fields=FieldNameType("status", str)` | `?statusNotIn=<v>` | `NotInCollectionFilter(field_name="status", values={...})` |
| `null_fields="notes"` | `?notesIsNull=true` | `NullFilter(field_name="notes")` |
| `not_null_fields="notes"` | `?notesIsNotNull=true` | `NotNullFilter(field_name="notes")` |

The returned callable is memoized on the hashed `FilterConfig`, so calling `db_plugin.provide_filters(same_config)` twice reuses the same dynamically-generated function. Build the filter dependency at module scope and reference the variable in route signatures — don't reconstruct it inside `Annotated[...]` because that regenerates the signature every request.

The handler receives `filters: list[FilterTypes]` — a list of the non-empty filters the request actually carried. The idiomatic consumption pattern is to iterate and call `append_to_statement(stmt)` on each; the filter catalog and semantics are in [filters.md](filters.md).

### Combining with the session

The common shape — session + filters in the same handler — uses two `Depends` entries.

```python
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException

from sqlspec import sql
from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.core import FilterTypes
from sqlspec.extensions.fastapi import FilterConfig


order_filters = db_plugin.provide_filters(
    FilterConfig(
        id_filter=UUID,
        search="customer_name",
        pagination_type="limit_offset",
        sort_field="created_at",
    )
)


@app.get("/orders")
async def list_orders(
    db: Annotated[AsyncpgDriver, Depends(db_plugin.provide_session())],
    filters: Annotated[list[FilterTypes], Depends(order_filters)],
) -> dict[str, Any]:
    stmt = sql.select("*").from_("orders")
    for flt in filters:
        stmt = flt.append_to_statement(stmt)
    rows = await db.select(stmt)
    if not rows:
        raise HTTPException(status_code=404, detail="no orders match")
    return {"orders": rows}
```

Use `HTTPException` to return non-2xx responses — the `SQLSpecAutocommitMiddleware` reads the final response status, so `raise HTTPException(status_code=404, ...)` will roll back any open transaction (404 is not in the 2xx window). If you *want* the read-only handler to not own a transaction at all, set `commit_mode="manual"` on the config (the default) — nothing commits, nothing rolls back.

## Multi-database

One plugin, multiple configs, one `SQLSpec` registry — the pattern scales linearly. Give each config its own keys:

```python
from fastapi import FastAPI

from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.sqlite import SqliteConfig

sqlspec = SQLSpec()

sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@primary:5432/orders"},
        extension_config={
            "fastapi": {
                "commit_mode": "autocommit",
                "connection_key": "primary_connection",
                "session_key": "primary_session",
                "pool_key": "primary_pool",
            }
        },
    )
)
sqlspec.add_config(
    SqliteConfig(
        connection_config={"database": "/var/lib/app/reports.sqlite"},
        extension_config={
            "fastapi": {
                "commit_mode": "manual",
                "connection_key": "reports_connection",
                "session_key": "reports_session",
                "pool_key": "reports_pool",
            }
        },
    )
)

app = FastAPI()
db_plugin = SQLSpecPlugin(sqlspec, app)
```

At request time each middleware runs — the primary pool acquires once, the reports pool acquires once, both release on the way out. Handlers pick the one they need by passing the matching `session_key` to `provide_session`:

```python
from typing import Annotated, Any

from fastapi import Depends

from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.adapters.sqlite import SqliteDriver


@app.get("/dashboard")
async def dashboard(
    primary: Annotated[AsyncpgDriver, Depends(db_plugin.provide_session("primary_session"))],
    reports: Annotated[SqliteDriver, Depends(db_plugin.provide_session("reports_session"))],
) -> dict[str, Any]:
    live = await primary.select("SELECT COUNT(*) AS n FROM orders WHERE status = 'open'")
    snapshot = reports.select("SELECT day, orders FROM daily_snapshot ORDER BY day DESC LIMIT 7")
    return {"live": live[0], "snapshot": snapshot}
```

Type annotations distinguish async from sync — `AsyncpgDriver.select` returns a coroutine; `SqliteDriver.select` returns the list directly. Each middleware flavor (async vs sync) handles its own acquisition / release correctly; the `FastAPI` event loop awaits async middleware and runs sync middleware in its default threadpool via Starlette's base classes.

Cross-bind `commit_mode` choices matter — pairing an `autocommit` primary with a `manual` reports bind (as above) is the typical read-heavy-with-occasional-writes shape. More permutations and pitfalls in [multi-database.md](multi-database.md).

## Migrations / CLI

SQLSpec's migration CLI is framework-neutral. It reads the same registry the FastAPI plugin reads and runs `up`/`down` against each config that has a `migration_config={...}` block.

```bash
uv run sqlspec database upgrade
uv run sqlspec database current
uv run sqlspec database downgrade -n 1
```

Point the CLI at your registry via `SQLSPEC_APP=package.module:sqlspec` — the `sqlspec` attribute on that module must be the registry instance you registered your configs against. The CLI iterates `sqlspec.configs.values()` and for each config with migrations enabled runs the pending scripts against that bind's pool. Each bind has its own version table; there's no shared history across binds.

There is no per-framework CLI shim. In particular, don't look for a `fastapi database ...` subcommand — the `sqlspec database ...` command is the only shape. See [migrations.md](migrations.md) for command reference, revision authoring, and rollback semantics.

## Example: full working handler

```python
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException

from sqlspec import SQLSpec, sql
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
from sqlspec.core import FilterTypes
from sqlspec.extensions.fastapi import FilterConfig, SQLSpecPlugin

sqlspec = SQLSpec()
sqlspec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
        extension_config={
            "fastapi": {
                "commit_mode": "autocommit",
                "session_key": "db_session",
                "pool_key": "db_pool",
            }
        },
    )
)

app = FastAPI()
db_plugin = SQLSpecPlugin(sqlspec, app)

SessionDep = Annotated[AsyncpgDriver, Depends(db_plugin.provide_session())]

order_filters = db_plugin.provide_filters(
    FilterConfig(
        id_filter=UUID,
        search="customer_name,notes",
        search_ignore_case=True,
        pagination_type="limit_offset",
        pagination_size=25,
        sort_field="created_at",
    )
)
FiltersDep = Annotated[list[FilterTypes], Depends(order_filters)]


@app.get("/orders")
async def list_orders(db: SessionDep, filters: FiltersDep) -> dict[str, Any]:
    stmt = sql.select("id", "customer_name", "status", "amount", "created_at").from_("orders")
    for flt in filters:
        stmt = flt.append_to_statement(stmt)
    rows = await db.select(stmt)
    return {"orders": rows}


@app.post("/orders", status_code=201)
async def create_order(payload: dict[str, Any], db: SessionDep) -> dict[str, Any]:
    if "customer_id" not in payload or "amount" not in payload:
        raise HTTPException(status_code=422, detail="customer_id and amount required")
    result = await db.execute(
        "INSERT INTO orders (customer_id, status, amount) VALUES ($1, $2, $3) RETURNING id",
        payload["customer_id"],
        "pending",
        payload["amount"],
    )
    return {"id": result.one()["id"]}


@app.get("/orders/{order_id}")
async def get_order(order_id: int, db: SessionDep) -> dict[str, Any]:
    rows = await db.select("SELECT * FROM orders WHERE id = $1", order_id)
    if not rows:
        raise HTTPException(status_code=404, detail="order not found")
    return {"order": rows[0]}
```

Request flow for `POST /orders`:

1. FastAPI enters the request scope. The plugin's lifespan has already created the asyncpg pool and stored it on `app.state.db_pool`.
2. `SQLSpecAutocommitMiddleware` acquires a connection and stores it under `request.state.db_connection`.
3. FastAPI resolves `db: SessionDep`. `Depends(db_plugin.provide_session())` calls the factory, which calls `self.get_session(request, None)`, which reads the connection off `request.state`, builds an `AsyncpgDriver`, and caches it.
4. The handler validates the payload (raising 422 if it's missing fields — that short-circuits before any DB work) and runs the insert with `RETURNING id`.
5. The handler returns the response. The middleware reads the 201 status, calls `await connection.commit()`, then releases the connection.
6. FastAPI serializes the response and returns to the client.

Request flow for `GET /orders` with `?searchString=acme&currentPage=2&pageSize=25&sortOrder=asc`:

1. Middleware acquires a connection (autocommit mode).
2. FastAPI resolves both dependencies. `provide_session()` yields the driver; the filter dependency parses the query string and returns `[LimitOffsetFilter(limit=25, offset=25), SearchFilter(field_name={"customer_name","notes"}, value="acme", ignore_case=True), OrderByFilter(field_name="created_at", sort_order="asc")]`.
3. The handler starts with `sql.select(...).from_("orders")`, then folds each filter in via `append_to_statement` — search becomes a `WHERE customer_name ILIKE ... OR notes ILIKE ...`, order-by becomes `ORDER BY created_at ASC`, limit-offset becomes `LIMIT 25 OFFSET 25`.
4. `db.select(stmt)` runs the final SQL, returns the rows.
5. Middleware commits on 200 and releases the connection.

## Cross-links

- [commit-modes.md](commit-modes.md) — `SQLSpecAutocommitMiddleware` vs `SQLSpecManualMiddleware`, including `extra_commit_statuses` / `extra_rollback_statuses`.
- [multi-database.md](multi-database.md) — per-bind `connection_key` / `session_key` / `pool_key`, validation, async + sync mixing.
- [filters.md](filters.md) — the filter object catalog — `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `BeforeAfterFilter`, `InCollectionFilter`, `NotInCollectionFilter`, `NullFilter`, `NotNullFilter`.
- [adapters.md](adapters.md) — adapter pool configuration (`min_size`, `max_size`, `conninfo`, `dsn`).
- [migrations.md](migrations.md) — global `sqlspec database ...` CLI and revision workflow.
- [observability.md](observability.md) — correlation and sqlcommenter middleware that thread request metadata into driver logs. Note: in plain Starlette, this metadata lives on `request.state`; see [starlette-integration.md](starlette-integration.md).
- [starlette-integration.md](starlette-integration.md) — the underlying plugin this FastAPI plugin extends.
- [flask-integration.md](flask-integration.md) — the sync WSGI sibling with portal-based async bridging.
- [../../litestar-styleguide/references/canonical-apps.md](../../litestar-styleguide/references/canonical-apps.md) — public canonical apps ([litestar-sqlstack](https://github.com/cofin/litestar-sqlstack), [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo)) for end-to-end SQLSpec patterns.
