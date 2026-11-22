# SQLSpec Extensions & Framework Integrations

## Litestar Integration

### Plugin Configuration

```python
from litestar import Litestar
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.litestar import SQLSpecPlugin

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "commit_mode": "autocommit",
        }
    },
)

sqlspec = SQLSpec()
sqlspec.add_config(config)

app = Litestar(
    route_handlers=[...],
    plugins=[SQLSpecPlugin(sqlspec=sqlspec)],
)
```

`SQLSpecPlugin` accepts a configured `SQLSpec` registry, not an adapter config. Register every config before constructing the plugin; the plugin snapshots the registry during initialization.

### Commit Modes

`commit_mode` defaults to `"autocommit"` (except BigQuery, which requires `"manual"` and rejects `"autocommit"` / `"autocommit_include_redirect"` with `ImproperConfigurationError`):

| Mode | Behavior | When to Use |
| --- | --- | --- |
| `"autocommit"` | Default. Commits after successful 2xx response, rolls back on error or 4xx/5xx. | Standard CRUD endpoints |
| `"autocommit_include_redirect"` | Same as autocommit but also commits on 3xx responses. | POST-redirect-GET patterns |
| `"manual"` | No automatic commit. You call `commit()` explicitly. Required for BigQuery. | Complex multi-step transactions |

### Dependency Injection

The plugin automatically provides driver sessions via dependency injection:

```python
from litestar import get, post
from sqlspec.adapters.asyncpg import AsyncpgDriver


@get("/users")
async def list_users(db_session: AsyncpgDriver) -> list[dict[str, object]]:
    result = await db_session.select("SELECT * FROM users")
    return result


@post("/users")
async def create_user(db_session: AsyncpgDriver, data: UserCreate) -> dict:
    result = await db_session.execute(
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id",
        data.name,
        data.email,
    )
    return {"id": result.last_inserted_id}
```

### Session Store Integration

Session stores are adapter-local Litestar stores. Construct the store from the same adapter config and pass it to Litestar's session middleware; `SQLSpecPlugin` does not automatically select a session backend.

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.asyncpg.litestar import AsyncpgStore

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "session_table": "sessions",
            "manage_schema": True,
            "create_schema": True,
        }
    },
)

store = AsyncpgStore(config)
```

Configure expiry in Litestar's session middleware. SQLSpec's extension block controls the table name, additive schema lifecycle, and adapter-specific table options.

### Extension Adapter Name & Store Resolution (`sqlspec.utils.adapters`)

Adapter configs (`SyncDatabaseConfig`, `AsyncDatabaseConfig`, `DatabaseConfigProtocol`) and extension base stores declare `ClassVar` metadata (`adapter_name`, `litestar_store_class`, `events_store_class`, `adk_store_class`, `adk_memory_store_class`). Framework and extension integrations resolve adapter names and concrete store classes via `resolve_adapter_name(config)` and `resolve_extension_store_class(config, extension=..., store_attr=..., store_suffix=...)` in `sqlspec.utils.adapters`.

### Correlation Header & Lifespan Control

```python
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "commit_mode": "autocommit",
            "correlation_header": "x-request-id",
            "enable_correlation_middleware": True,
            "disable_di": False,
            "manage_lifespan": True,
        }
    },
)
```

`SQLSpecPlugin` provides driver sessions (`db_session`), raw connections (`db_connection`), and replica/routing sessions (`replica_session_key` `"db_replica_session"`, `routing_session_key`) using lazy connection checkout on first access. Provider helpers in `sqlspec.extensions.litestar.providers` use `provide_db_session*`, `provide_db_connection*`, and `db_*_provider_maker` (the legacy `provide_request_session*`, `provide_request_connection*`, `*_provider_maker`, and `get_or_create_session` names were replaced in `sqlspec>=0.74`).

- **Read replicas & primary pinning**: configure `ReplicaGroup` / `ReplicaSpec` on `driver_features` or config, then tune `LitestarConfig` keys `enable_routing_middleware`, `default_routing_mode`, `routing_header`, `primary_pin_cookie`, `primary_pin_secret`, `replica_session_key`, `replica_connection_key`, `replica_pool_key`, and `routing_session_key` (with `sign_primary_pin` / `verify_primary_pin`).
- **Tenant isolation**: use `SQLSpecTenantMiddleware`, `TenantContext`, `TenantResolutionSettings`, `resolve_litestar_tenant`, `set_request_tenant`, `require_tenant`, and `tenant_bypass`.
- **Cursor signing**: configure `pagination_cursor_secret`, `pagination_cursor_ttl`, and `pagination_cursor_encrypted` in `extension_config["litestar"]` and `FilterConfig`.
- **Correlation extraction**: `CorrelationMiddleware` extracts the correlation ID from `correlation_header` / `correlation_headers` (plus W3C trace headers when `auto_trace_headers=True`) and attaches it to all SQL log events emitted during that request lifecycle. `SQLSpecPlugin` deduplicates `CorrelationMiddleware` across multiple registered configs.
- **Dishka / Custom DI mode (`disable_di: True, manage_lifespan: True`)**: when `disable_di: True` is set so Dishka owns session/service injection, set `manage_lifespan: True` so `SQLSpecPlugin` still registers the Litestar lifespan handler that drains and closes connection pools on shutdown (`manage_lifespan` defaults to `not disable_di`).

---

## Starlette / FastAPI Integration

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.starlette import SQLSpecPlugin

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql:///db"},
    extension_config={
        "starlette": {
            "commit_mode": "autocommit",
            "correlation_header": "x-request-id",
        }
    },
)

sqlspec = SQLSpec()
sqlspec.add_config(config)
plugin = SQLSpecPlugin(sqlspec)
plugin.init_app(app)
```

### FastAPI / Starlette Session Access

`SQLSpecPlugin` exposes a `get_session(request, key=None)` method on the plugin instance — call it inside any handler that needs a per-request session.

```python
from fastapi import FastAPI, Request
from sqlspec.extensions.fastapi import SQLSpecPlugin

app = FastAPI()
db_ext = SQLSpecPlugin(spec, app=app)


@app.get("/users")
async def list_users(request: Request):
    db_session = db_ext.get_session(request)
    result = await db_session.select("SELECT * FROM users")
    return result
```

The plugin caches the session on `request.state` under the configured `session_key` (default `"db_session"`), so subsequent calls within the same request reuse the same session.

---

## EXPLAIN Plan Builder

Analyze and optimize query execution plans fluently.

### Database Compatibility

- **PostgreSQL**: ANALYZE, buffers, timing, JSON formatting.
- **MySQL**: JSON / TREE formatting.
- **SQLite**: QUERY PLAN text output only.

### Fluent Usage

```python
from sqlspec.builder import Explain

explain = Explain("SELECT * FROM users", dialect="postgres").analyze().verbose().format("json").build()
```

---

## Error Handling

### Custom Exception Classes & Default Litestar Exception Handlers

All adapters wrap exceptions using `wrap_exceptions` referencing static mappings to the `SQLSpecError` base:

- `AdapterError`: Generic connectivity or execution issues.
- `IntegrityError` (`UniqueViolationError`, `ForeignKeyViolationError`, `NotNullViolationError`, `CheckViolationError`): Constraint and uniqueness violations.
- `NotFoundError`: `select_one()` or `select_value()` received no result.
- `ValueError`: `select_one()` or `select_value()` received multiple results.
- `MultipleResultsFoundError`: `select_one_or_none()` or `select_value_or_none()` received multiple results.

In Litestar, `SQLSpecPlugin` registers default exception handlers (unless the application already defines a handler for that exception type):

- `NotFoundError` → HTTP `404 Not Found` (`not_found_error_handler`)
- `IntegrityError` → HTTP `409 Conflict` (`integrity_error_handler`, with sub-type detail for unique, foreign-key, not-null, and check violations)

### Two-Tier Event Reporting

Inside middleware or loaders:

1. **Graceful Skip**: Input lacks required markers. Return empty set, log at DEBUG level.
2. **Hard Error**: Malformed inputs. Raise strictly with context.
