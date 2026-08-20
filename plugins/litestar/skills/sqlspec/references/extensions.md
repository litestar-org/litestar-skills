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

| Mode | Behavior | When to Use |
| --- | --- | --- |
| `"manual"` | No automatic commit. You call `commit()` explicitly. | Complex multi-step transactions |
| `"autocommit"` | Commits after successful response, rolls back on error. | Standard CRUD endpoints |
| `"autocommit_include_redirect"` | Same as autocommit but also commits on 3xx responses. | POST-redirect-GET patterns |

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

### Correlation Header for Request Tracing

```python
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "commit_mode": "autocommit",
            "correlation_header": "x-request-id",
        }
    },
)
```

The correlation header value is extracted from each request and attached to all SQL log events emitted during that request lifecycle.

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

### Custom Exception Classes

All adapters wrap exceptions using `wrap_exceptions` referencing static mappings to the `SQLSpecError` base:

- `AdapterError`: Generic connectivity or execution issues.
- `IntegrityError`: Constraint and uniqueness violations.
- `NotFoundError`: `select_one()` or `select_value()` received no result.
- `ValueError`: `select_one()` or `select_value()` received multiple results.
- `MultipleResultsFoundError`: `select_one_or_none()` or `select_value_or_none()` received multiple results.

### Two-Tier Event Reporting

Inside middleware or loaders:

1. **Graceful Skip**: Input lacks required markers. Return empty set, log at DEBUG level.
2. **Hard Error**: Malformed inputs. Raise strictly with context.
