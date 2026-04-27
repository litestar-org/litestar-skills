# SQLSpec ADK Extension

`sqlspec.extensions.adk` is the SQL-backed storage layer for Google's **Agent Development Kit (ADK)** session, memory, and artifact abstractions. ADK defines abstract services (`BaseSessionService`, `BaseMemoryService`, `BaseArtifactService`); SQLSpec ships concrete SQL-backed implementations that plug into any adapter.

## What ADK Is

Google's ADK is a Python framework for building LLM agents (`LlmAgent`, `Runner`, tool calls, structured events). ADK is storage-agnostic — you point it at a session service, memory service, and (optionally) an artifact service, and it persists state across turns. SQLSpec's `extensions.adk` module provides those three services backed by a real database rather than in-memory dicts.

## The Three Stores

All store classes live under `sqlspec.extensions.adk`. Each has an async base (used by async adapters) and a sync base (used by sync adapters):

| Store | Purpose | Service | Record type |
| --- | --- | --- | --- |
| `BaseAsyncADKStore` / `BaseSyncADKStore` | Conversation sessions + full event history | `SQLSpecSessionService` | `SessionRecord`, `EventRecord` |
| `BaseAsyncADKMemoryStore` / `BaseSyncADKMemoryStore` | Long-term memory entries searchable per user | `SQLSpecMemoryService`, `SQLSpecSyncMemoryService` | `MemoryRecord` |
| `BaseAsyncADKArtifactStore` / `BaseSyncADKArtifactStore` | Versioned artifact **metadata** (content lives in object storage) | `SQLSpecArtifactService` | `ArtifactRecord` |

All records are `TypedDict`s (see `sqlspec/extensions/adk/_types.py`, `memory/_types.py`, `artifact/_types.py`) so mypyc can compile the service layer without pulling in Pydantic at runtime.

### Session store

Stores one row per session plus N rows per event. The full ADK `Event` is dumped via `Event.model_dump_json(exclude_none=True)` into a single JSON column (`event_json`); a small number of indexed scalars (`session_id`, `invocation_id`, `author`, `timestamp`) are extracted for query performance. Reconstruction uses `Event.model_validate_json()`.

### Memory store

Holds searchable memory entries extracted from completed sessions. The `SQLSpecMemoryService.add_session_to_memory(session)` method walks the events and writes one `MemoryRecord` per message with both structured `content_json` and flattened `content_text` (used for LIKE / FTS search).

### Artifact store

Persists artifact **metadata** (filename, version, MIME type, `canonical_uri`, `custom_metadata`). The bytes live in a `sqlspec.storage` backend — `SQLSpecArtifactService` is constructed with `artifact_storage_uri="s3://..."` (or any URI the registry can resolve), and uses that for content reads/writes. Versioning is append-only starting from `0`.

## Converters

`sqlspec.extensions.adk.converters` bridges ADK's Pydantic models (`Session`, `Event`) and the `TypedDict` database records:

- `session_to_record(session)` / `record_to_session(record, events)`
- `event_to_record(event)` / `record_to_event(record)`
- `filter_temp_state(state)` — strips `temp:`-prefixed keys so they never persist
- `split_scoped_state(state)` / `merge_scoped_state(...)` — normalise the `app:`, `user:`, `temp:` prefixes ADK uses to scope state
- `compute_update_marker(update_time)` — produces the same revision marker string ADK's built-in `StorageSession.get_update_marker()` emits, enabling optimistic-concurrency detection on `append_event`

Memory and artifact modules ship their own converter helpers (`sqlspec.extensions.adk.memory.converters`, e.g. `extract_content_text`, `record_to_memory_entry`, `session_to_memory_records`).

## Per-Adapter Store Implementations

Fourteen adapters ship a concrete `adk/store.py`: `asyncpg`, `psycopg`, `psqlpy`, `cockroach_asyncpg`, `cockroach_psycopg`, `oracledb`, `sqlite`, `aiosqlite`, `duckdb`, `asyncmy`, `pymysql`, `mysqlconnector`, `spanner`, `adbc`. Each contains both `<Adapter>ADKStore` (session/event) and `<Adapter>ADKMemoryStore` (memory).

Representative storage strategies:

| Adapter | JSON column type | Notable features |
| --- | --- | --- |
| `asyncpg` / `psycopg` | `JSONB` | GIN index on state, `FILLFACTOR 80` for HOT updates, FK cascade delete |
| `cockroach_asyncpg` / `cockroach_psycopg` | `JSONB` | Same surface as Postgres; tuned for Cockroach's MVCC |
| `oracledb` | `JSON` native (21c+), `BLOB` + `IS JSON` check (12c–20c), raw `BLOB` otherwise | Version-aware; `JSONStorageType` enum in `sqlspec.adapters.oracledb.adk.store` |
| `spanner` | JSON (`param_types.JSON`) or STRING fallback | Uses Spanner transactions; `param_types.JSON` when available |
| `duckdb` | `JSON` | Single-file analytics; syncs via sync driver |
| `sqlite` / `aiosqlite` | `TEXT` with JSON1 functions | Local dev; small footprint |
| `asyncmy` / `pymysql` / `mysqlconnector` | `JSON` | Uses MySQL's native JSON type |

BigQuery and the `mock` adapter do **not** ship an ADK store; point those workloads at one of the adapters above.

## Schema Expectations

Each store owns its DDL. The shipped migration under `sqlspec/extensions/litestar/migrations/0001_create_session_table.py` delegates to the adapter's store class for the `CREATE TABLE` — call `store._get_create_table_sql()` (or `ensure_tables()`) when bootstrapping outside of migrations. Table names are configurable via `extension_config["adk"]`:

- `session_table` (default `"adk_sessions"`)
- `events_table` (default `"adk_events"`)
- `memory_table` (default `"adk_memory_entries"`)
- `artifact_table` (default `"adk_artifact_versions"`)
- `owner_id_column` — optional DDL fragment (e.g. `"tenant_id INTEGER REFERENCES tenants(id)"`) for multi-tenant foreign keys

## Litestar Handler Pattern

The [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo) canonical app wires an ADK `LlmAgent` behind a Litestar handler using `SQLSpecSessionService` backed by `OracleAsyncADKStore`. The shape:

```python
from typing import TYPE_CHECKING

from sqlspec.adapters.oracledb import OracleAsyncConfig
from sqlspec.adapters.oracledb.adk.store import OracleAsyncADKStore
from sqlspec.extensions.adk import SQLSpecSessionService

if TYPE_CHECKING:
    from google.adk.sessions import Session


config = OracleAsyncConfig(
    connection_config={"dsn": "oracle+oracledb://app:app@oracle:1521/FREEPDB1"},
    extension_config={
        "adk": {
            "session_table": "adk_sessions",
            "events_table": "adk_events",
            "memory_table": "adk_memory_entries",
        }
    },
)


async def bootstrap_session_service() -> SQLSpecSessionService:
    store = OracleAsyncADKStore(config)
    await store.ensure_tables()
    return SQLSpecSessionService(store)


async def get_or_create_session(
    service: SQLSpecSessionService, app_name: str, user_id: str, session_id: str
) -> "Session":
    existing = await service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
    if existing is not None:
        return existing
    return await service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id, state={}
    )
```

The ADK `Runner` then takes this `service` wherever it needs a `BaseSessionService`.

## Example: SessionStore in Use

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.asyncpg.adk.store import AsyncpgADKStore
from sqlspec.extensions.adk import SQLSpecSessionService


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"},
    extension_config={
        "adk": {
            "session_table": "adk_sessions",
            "events_table": "adk_events",
            "owner_id_column": "tenant_id INTEGER REFERENCES tenants(id)",
        }
    },
)


async def new_conversation(tenant_id: int, user_id: str) -> str:
    store = AsyncpgADKStore(config)
    await store.ensure_tables()
    service = SQLSpecSessionService(store)

    session = await service.create_session(
        app_name="support-bot",
        user_id=user_id,
        state={"tenant_id": tenant_id, "channel": "web"},
    )
    return session.id
```

Synchronous adapters (`SqliteADKStore`, `DuckdbADKStore`, `OracleSyncADKStore`, etc.) use `SQLSpecSyncMemoryService` for the memory surface; session storage itself is async-only because the upstream ADK `BaseSessionService` interface is async.

## Public API Summary

Top-level exports from `sqlspec.extensions.adk`:

- `SQLSpecSessionService`, `SQLSpecMemoryService`, `SQLSpecSyncMemoryService`, `SQLSpecArtifactService`
- `BaseAsyncADKStore`, `BaseSyncADKStore`
- `BaseAsyncADKMemoryStore`, `BaseSyncADKMemoryStore`
- `BaseAsyncADKArtifactStore`, `BaseSyncADKArtifactStore`
- `SessionRecord`, `EventRecord`, `MemoryRecord`, `ArtifactRecord`
- `ADKConfig` (TypedDict describing `extension_config["adk"]`)

## Cross References

- [extensions.md](extensions.md) — the wider Litestar plugin surface.
- [storage.md](storage.md) — storage backends used for artifact content.
- [migrations.md](migrations.md) — how ADK tables get created via `include_extensions=["adk"]`.
