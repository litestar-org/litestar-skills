# SQLSpec Storage Integration

## Overview

SQLSpec provides adapter-specific storage implementations for Litestar session stores, event channel backends, and ADK session/event plus memory stores. Artifact service contracts are available under ADK, but adapter-specific concrete artifact metadata stores are deployment-provided. All integrations are configured through the `extension_config` dict on adapter configs.

---

## ADK Store Implementations

Each production adapter provides an `adk` package with session/event and memory stores for Google ADK workflows:

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.asyncpg.adk import AsyncpgADKMemoryStore, AsyncpgADKStore

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "adk": {
            "session_table": "adk_session",
            "events_table": "adk_event",
            "memory_table": "adk_memory",
            "memory_use_fts": True,
        }
    },
)

session_store = AsyncpgADKStore(config)
memory_store = AsyncpgADKMemoryStore(config)
await session_store.ensure_tables()
await memory_store.ensure_tables()
```

### Available ADK Stores

ADK-supported adapters are `asyncpg`, `psycopg`, `psqlpy`, `cockroach_asyncpg`, `cockroach_psycopg`, `aiomysql`, `asyncmy`, `mysqlconnector`, `pymysql`, `aiosqlite`, `sqlite`, `oracledb`, `duckdb`, `adbc`, and `spanner`. These stores handle:

- Session rows and event history for `SQLSpecSessionService`
- Memory rows for `SQLSpecMemoryService` / `SQLSpecSyncMemoryService`
- Adapter-specific JSON, FTS, and transaction optimizations

BigQuery is not an ADK backend. Use Spanner or an OLTP adapter for Google ADK session/event storage.

---

## Event Channel Backends

Each adapter provides an `events/store.py` module implementing event pub/sub storage:

```python
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "events": {
            "backend": "listen_notify",      # or "table_queue"
            "channel": "app_events",
        }
    },
)
```

### Backend Selection by Adapter

| Adapter | Recommended Backend | Notes |
| --- | --- | --- |
| AsyncPG / Psycopg / CockroachDB | `listen_notify` | Native PostgreSQL LISTEN/NOTIFY |
| OracleDB | `advanced_queue` | Oracle Advanced Queuing |
| All others | `table_queue` | Universal polling fallback |

See [events.md](events.md) for full pub/sub documentation.

---

## Litestar Session Store

Each adapter provides a `litestar/store.py` module for server-side session storage:

```python
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "commit_mode": "autocommit",
            "session_table": "sessions",
            "session_ttl": 3600,
        }
    },
)
```

### Available Session Stores

| Adapter | Store Class | Notes |
| --- | --- | --- |
| AsyncPG | `AsyncpgStore` | JSONB session data |
| Psycopg | `PsycopgStore` | JSONB session data |
| AioSQLite | `AiosqliteStore` | JSON text column |
| DuckDB | `DuckdbStore` | JSON column |
| SQLite | `SqliteStore` | JSON text column |
| BigQuery | `BigqueryStore` | JSON column |
| OracleDB | `OracledbStore` | CLOB/JSON column |
| All MySQL variants | Respective stores | JSON column |
| All CockroachDB variants | Respective stores | JSONB column |
| Spanner | `SpannerStore` | JSON column |
| PSQLPy | `PsqlpyStore` | JSONB session data |
| ADBC | `AdbcStore` | Varies by underlying driver |

---

## Configuration via extension_config

The `extension_config` dict on any adapter config is the unified entry point for all storage integrations:

```python
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        # Litestar framework integration
        "litestar": {
            "commit_mode": "autocommit",
            "session_table": "sessions",
            "correlation_header": "x-request-id",
        },
        # Starlette/FastAPI framework integration
        "starlette": {
            "commit_mode": "autocommit",
        },
        # Event channel configuration
        "events": {
            "backend": "listen_notify",
            "channel": "app_events",
        },
        # ADK session/event and memory stores
        "adk": {
            "session_table": "adk_session",
            "events_table": "adk_event",
            "memory_table": "adk_memory",
            "memory_use_fts": True,
        },
    },
)
```

Only include the keys for integrations you are using. Unused keys are ignored.
