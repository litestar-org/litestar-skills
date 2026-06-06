# Multi-Database Configuration

This reference describes how SQLSpec supports applications that talk to more than one database in the same process — for example a primary OLTP store plus a read-only analytics warehouse, or a Postgres tenant store plus a DuckDB report cache. The mechanism is the same across every framework integration: register multiple adapter configs with a `SQLSpec()` registry, give each one distinct `connection_key` / `session_key` / `pool_key` values, and the framework extension iterates the registry to wire one middleware stack per config. Per-framework injection wiring (how the right session ends up in a handler signature) is covered in the framework guides.

## The `SQLSpec` Registry

The `SQLSpec` class is the application-level registry. It holds an ordered collection of adapter configs and exposes `add_config()` to extend it. The upstream signature:

```python
class SQLSpec:
    """Configuration manager and registry for database connections and pools."""

    def __init__(
        self,
        *,
        loader: SQLFileLoader | None = None,
        observability_config: ObservabilityConfig | None = None,
    ) -> None:
        self._configs: dict[int, DatabaseConfigProtocol[Any, Any, Any]] = {}
        ...

    def add_config(self, config: SyncConfigT | AsyncConfigT) -> SyncConfigT | AsyncConfigT:
        config_id = id(config)
        ...
        self._configs[config_id] = config
        return config
```

Two important properties:

1. **The config instance is the handle.** `add_config` returns the same object you passed in, and the registry uses Python's `id()` as the dict key. To reference a specific config later, hold the reference you passed in — there is no string-based lookup at the registry level.
2. **Per-key state lives on the config, not the registry.** Each adapter config carries its own `connection_key`, `session_key`, and `pool_key` (set via `extension_config["<framework>"]`). The framework extension reads these per-config values to decide where on `request.state` and `app.state` to store connections, sessions, and pools.

## The Per-Key Model

When the framework extension scans the registry, it builds one `SQLSpecConfigState` per config, with these defaults from upstream:

| Field | Default | Purpose |
| --- | --- | --- |
| `connection_key` | `"db_connection"` | Slot on `request.state` for the per-request connection |
| `session_key` | `"db_session"` | Slot on `request.state` for the per-request driver session |
| `pool_key` | `"db_pool"` | Slot on `app.state` for the shared pool |

If two configs share a key, the second middleware overwrites the first. **You must give each config a unique triple** — the same way `bind_key` works in advanced-alchemy, only here you set the key directly on each `extension_config` dict.

## Registering Multiple Configs

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.duckdb import DuckDBConfig

primary = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@primary:5432/orders"},
    extension_config={
        "starlette": {
            "commit_mode": "autocommit",
            "connection_key": "primary_connection",
            "session_key": "primary_session",
            "pool_key": "primary_pool",
        },
    },
)

analytics = DuckDBConfig(
    connection_config={"database": "/var/lib/app/analytics.duckdb"},
    extension_config={
        "starlette": {
            "commit_mode": "manual",
            "connection_key": "analytics_connection",
            "session_key": "analytics_session",
            "pool_key": "analytics_pool",
        },
    },
)

sqlspec = SQLSpec()
sqlspec.add_config(primary)
sqlspec.add_config(analytics)
```

The extension reads `sqlspec.configs.values()` at startup, builds one `SQLSpecConfigState` per config, and registers one middleware per state. The order of registration determines middleware ordering — the first config registered has its middleware run outermost.

## Looking Up a Specific Config

The framework extensions expose `get_session(request, key=None)` and `get_connection(request, key=None)` for runtime lookup. From upstream:

```python
def get_session(self, request: Request, key: str | None = None) -> Any:
    ...

def get_connection(self, request: Request, key: str | None = None) -> Any:
    ...
```

When `key=None`, the lookup uses the *first* registered config — convenient for the single-bind case. When `key` is set, it must match the `session_key` (for `get_session`) or `connection_key` (for `get_connection`) of one of the registered configs.

The agnostic shape of "give me the right session for this bind" is therefore:

```python
session = plugin.get_session(request, key="primary_session")
analytics_session = plugin.get_session(request, key="analytics_session")
```

How `plugin` is obtained, and how this lookup is hidden behind a per-framework dependency-injection primitive, is the subject of the framework guides.

## Async + Sync in the Same Application

`SQLSpec.add_config` accepts both `SyncConfigT` and `AsyncConfigT`. A common shape: async primary (asyncpg) plus sync analytics (DuckDB or psycopg) because the analytics queries run inside a threadpool.

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.psycopg import PsycopgSyncConfig

primary = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@primary:5432/orders"},
    extension_config={"starlette": {"commit_mode": "autocommit",
                                     "session_key": "primary_session"}},
)
analytics = PsycopgSyncConfig(
    connection_config={"conninfo": "postgresql://reader:reader@warehouse:5432/analytics"},
    extension_config={"starlette": {"commit_mode": "manual",
                                     "session_key": "analytics_session"}},
)

sqlspec = SQLSpec()
sqlspec.add_config(primary)
sqlspec.add_config(analytics)
```

The middleware registered for each config respects that config's flavor — async configs get awaited acquisition / commit / release; sync configs run those calls in the host's threadpool.

## Pooling Considerations

Each adapter config owns its own pool. Pools are *not* shared across configs even when they target the same physical database — registering the same Postgres DSN under two different configs produces two independent pools, doubling the connection footprint. To share a pool, share the config instance.

Per-pool sizing belongs in each config's `connection_config`:

```python
primary = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://app:app@primary:5432/orders",
        "min_size": 5,
        "max_size": 20,
    },
    extension_config={"starlette": {"commit_mode": "autocommit",
                                     "pool_key": "primary_pool"}},
)

analytics = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://reader:reader@warehouse:5432/analytics",
        "min_size": 1,
        "max_size": 5,
    },
    extension_config={"starlette": {"commit_mode": "manual",
                                     "pool_key": "analytics_pool"}},
)
```

The exact `connection_config` keys are adapter-specific (asyncpg uses `min_size` / `max_size`, psycopg uses `min_size` / `max_size`, OracleDB uses `min` / `max`, etc. — see [adapters.md](./adapters.md)). Sizing each pool independently is the correct posture; the registry does not enforce a global cap.

## Sync Bridge

For purely sync hosts (a sync WSGI worker or a CLI), the registry works identically — pass sync configs only. The `SQLSpec()` constructor and `add_config` method are the same; the framework extensions detect each config's flavor and wire the appropriate middleware.

```python
from sqlspec import SQLSpec
from sqlspec.adapters.psycopg import PsycopgSyncConfig
from sqlspec.adapters.sqlite import SqliteConfig

primary = PsycopgSyncConfig(
    connection_config={"conninfo": "postgresql://app:app@primary:5432/orders"},
    extension_config={"starlette": {"commit_mode": "autocommit",
                                     "session_key": "primary_session"}},
)
reports = SqliteConfig(
    connection_config={"database": ":memory:"},
    extension_config={"starlette": {"commit_mode": "manual",
                                     "session_key": "reports_session"}},
)
sqlspec = SQLSpec()
sqlspec.add_config(primary)
sqlspec.add_config(reports)
```

## Migrations Across Multiple Binds

SQLSpec's migration runner reads the registry the same way the framework extension does: it iterates `sqlspec.configs.values()` and, for each config that has migrations enabled (`migration_config={...}` on the adapter), runs the up/down scripts against that config's pool. Each bind has its own `versions/` directory and its own version-tracking table — there is no shared migration history across binds. See [adapters.md](./adapters.md) for adapter-specific migration setup.

## Common Pitfalls

- **Forgetting to set unique keys.** Two configs that both default to `connection_key="db_connection"` will silently overwrite each other's `request.state` slot. The handler that asks for the second connection will get the first one — or `None`, depending on middleware order. Always set `connection_key`, `session_key`, and `pool_key` explicitly when you have more than one config.
- **`add_config` does not deduplicate.** Calling `sqlspec.add_config(cfg)` twice with the same instance logs a debug message and overwrites the previous entry; calling it with two configs that wrap the same DSN produces two pools. Hold one reference per logical bind.
- **No cross-bind transactions.** Each middleware owns one connection per request; `commit()` on the primary does not commit work on the analytics bind. If you need atomic cross-database semantics, you need explicit coordination (two-phase commit at the database level, an outbox table, or a saga pattern at the application layer).
- **The `SQLSpec` registry is not thread-safe for mutation.** `add_config` should be called once at application startup, before any worker accepts requests. Do not add configs from inside a request handler.
- **Per-bind `commit_mode` is intentional.** A read-only analytics bind should use `commit_mode="manual"` (no writes -> no commits needed); a primary write bind typically uses `autocommit`. See [commit-modes.md](./commit-modes.md).
- **Pool exhaustion at the wrong bind.** If the analytics pool is sized at 5 and a long-running report blocks all of them, requests that need *any* analytics query queue up. Size analytics pools for the worst-case concurrent slow query.
- **`extension_config` keys are framework-namespaced.** Settings under `extension_config["starlette"]` are not read by the litestar extension; settings under `extension_config["litestar"]` are not read by the starlette extension. You can declare both blocks in the same dict — only the loaded extension reads its block.

## Canonical References

- [litestar-sqlstack](https://github.com/cofin/litestar-sqlstack) — single-bind AsyncpgConfig demonstrating the baseline `SQLSpec()` + `add_config()` shape; the per-key fields are visible in its `extension_config["litestar"]` block.
- [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo) — single-bind OracleAsyncConfig; useful as the starting point before splitting into multiple binds.
