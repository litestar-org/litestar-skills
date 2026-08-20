# SQLSpec ADK Extension

`sqlspec.extensions.adk` is the SQL-backed storage layer for Google's **Agent Development Kit (ADK)** session, event, and memory abstractions. ADK defines abstract services (`BaseSessionService`, `BaseMemoryService`, `BaseArtifactService`); SQLSpec ships session/event and memory implementations for supported adapters plus artifact service contracts for deployments that provide a concrete artifact metadata store.

## What ADK Is

Google's ADK is a Python framework for building LLM agents (`LlmAgent`, `Runner`, tool calls, structured events). ADK is storage-agnostic — you point it at a session service, memory service, and (optionally) an artifact service, and it persists state across turns. SQLSpec's `extensions.adk` module provides database-backed session and memory services, plus an artifact service when paired with a concrete artifact metadata store.

## Store Surface

All store classes live under `sqlspec.extensions.adk`. Each has an async base (used by async adapters) and a sync base (used by sync adapters):

| Store | Purpose | Service | Record type |
| --- | --- | --- | --- |
| `BaseAsyncADKStore` / `BaseSyncADKStore` | Conversation sessions + full event history | `SQLSpecSessionService` | `StoredSession`, `StoredEvent` |
| `BaseAsyncADKMemoryStore` / `BaseSyncADKMemoryStore` | Long-term memory entries searchable per user | `SQLSpecMemoryService`, `SQLSpecSyncMemoryService` | `StoredMemory` |
| `BaseAsyncADKArtifactStore` / `BaseSyncADKArtifactStore` | Versioned artifact **metadata** contract (content lives in object storage) | `SQLSpecArtifactService` (async store) | `StoredArtifact` |

All records are `TypedDict`s (see `sqlspec/extensions/adk/_types.py`, `memory/_types.py`, `artifact/_types.py`). Adapter support guarantees cover session/event and memory stores. Adapter-specific concrete artifact metadata stores are not part of the support matrix.

### Session store

Stores one row per session plus N rows per event. The full ADK `Event` is dumped via `event.model_dump(exclude_none=True, mode="json")` into a single JSON column (`event_data`); indexed scalars (`app_name`, `user_id`, `session_id`, `invocation_id`, `timestamp`) support filtering. Reconstruction uses `Event.model_validate()`.

### Memory store

Holds searchable memory entries extracted from completed sessions. The `SQLSpecMemoryService.add_session_to_memory(session)` method walks the events and writes one `StoredMemory` record per message with both structured `content_json` and flattened `content_text` (used for LIKE / FTS search).

### Bounded session reads and lists

Pass ADK's `GetSessionConfig` to bound event history when loading a transcript. SQLSpec also adds deterministic ordering and offset pagination to session lists:

```python
from google.adk.sessions.base_session_service import GetSessionConfig

session = await service.get_session(
    app_name="support-bot",
    user_id=user_id,
    session_id=session_id,
    config=GetSessionConfig(num_recent_events=200),
)
recent_sessions = await service.list_sessions(
    app_name="support-bot",
    user_id=user_id,
    order_by="update_time",
    descending=True,
    limit=20,
    offset=0,
)
```

`GetSessionConfig.after_timestamp` filters events after a Unix timestamp. `list_sessions()` accepts only `create_time` or `update_time` for `order_by`; a positive `offset` requires a finite `limit`.

### Artifact store

Persists artifact **metadata** when a deployment supplies a concrete metadata store. The metadata record tracks filename, version, MIME type, `canonical_uri`, and `custom_metadata`; bytes live in a `sqlspec.storage` backend via `artifact_storage_uri="s3://..."` or a registered storage alias. Versioning is append-only starting from `0`.

## Converters

`sqlspec.extensions.adk.converters` bridges ADK's Pydantic models (`Session`, `Event`) and the `TypedDict` database records:

- `session_to_record(session)` / `record_to_session(record, events)`
- `event_to_record(event, app_name, user_id, session_id)` / `record_to_event(record)`
- `filter_temp_state(state)` — strips `temp:`-prefixed keys so they never persist
- `split_scoped_state(state)` / `merge_scoped_state(...)` — normalise the `app:`, `user:`, `temp:` prefixes ADK uses to scope state
- `compute_update_marker(update_time)` — produces the same revision marker string ADK's built-in `StorageSession.get_update_marker()` emits, enabling optimistic-concurrency detection on `append_event`

Memory and artifact modules ship their own converter helpers (`sqlspec.extensions.adk.memory.converters`, e.g. `extract_content_text`, `record_to_memory_entry`, `session_to_memory_records`).

## Per-Adapter Store Implementations

Production adapters ship concrete session/event and memory stores from their `sqlspec.adapters.<adapter>.adk` package: `asyncpg`, `psycopg`, `psqlpy`, `cockroach_asyncpg`, `cockroach_psycopg`, `oracledb`, `sqlite`, `aiosqlite`, `duckdb`, `aiomysql`, `asyncmy`, `pymysql`, `mysqlconnector`, `spanner`, and `adbc`. Each contains both `<Adapter>ADKStore` (session/event) and `<Adapter>ADKMemoryStore` (memory).

Representative storage strategies:

| Adapter | JSON column type | Notable features |
| --- | --- | --- |
| `asyncpg` / `psycopg` | `JSONB` | GIN index on state, `FILLFACTOR 80` for HOT updates, FK cascade delete |
| `cockroach_asyncpg` / `cockroach_psycopg` | `JSONB` | Same surface as Postgres; tuned for Cockroach's MVCC |
| `oracledb` | `JSON` native (21c+), `BLOB` + `IS JSON` check (12c–20c), raw `BLOB` otherwise | Version-aware; `JSONStorageType` enum in the Oracle ADK package |
| `spanner` | JSON (`param_types.JSON`) or STRING fallback | Uses Spanner transactions; `param_types.JSON` when available |
| `duckdb` | `JSON` | Single-file analytics; syncs via sync driver |
| `sqlite` / `aiosqlite` | `TEXT` with JSON1 functions | Local dev; small footprint |
| `asyncmy` / `pymysql` / `mysqlconnector` | `JSON` | Uses MySQL's native JSON type |

BigQuery and the `mock` adapter do **not** ship an ADK store. BigQuery was removed from the ADK backend surface because the batch-oriented job model does not fit ADK's low-latency transactional session/event writes. Use Spanner for a Google-managed operational backend or an OLTP backend such as PostgreSQL, MySQL, Oracle, SQLite, or CockroachDB.

## Schema Expectations

Each store owns its DDL. Call `ensure_tables()` or `create_tables()` when bootstrapping directly, or use SQLSpec migrations for managed deployments. Table names are configurable via `extension_config["adk"]`:

- `session_table` (default `"adk_session"`)
- `events_table` (default `"adk_event"`)
- `app_state_table` (default `"adk_app_state"`)
- `user_state_table` (default `"adk_user_state"`)
- `metadata_table` (default `"adk_internal_metadata"`)
- `memory_table` (default `"adk_memory"`)
- `artifact_table` (default `"adk_artifact"`)
- `owner_id_column` — optional DDL fragment (e.g. `"tenant_id INTEGER REFERENCES tenants(id)"`) for owner scoping when the store call path supplies owner IDs

Migrations check that the selected adapter has the session and memory store classes before generating schema.

The ADK 2 migration `0002_reset_adk_tables` is destructive: it drops legacy ADK session, event, state, metadata, and memory tables before recreating the 2.0 schema. Back up ADK data before applying it to an existing deployment.

## Litestar Handler Pattern

The [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo) canonical app wires an ADK `LlmAgent` behind a Litestar handler using `SQLSpecSessionService` backed by `OracleAsyncADKStore`. The shape:

```python
from typing import TYPE_CHECKING

from sqlspec.adapters.oracledb import OracleAsyncConfig
from sqlspec.adapters.oracledb.adk import OracleAsyncADKStore
from sqlspec.extensions.adk import SQLSpecSessionService

if TYPE_CHECKING:
    from google.adk.sessions import Session


config = OracleAsyncConfig(
    connection_config={"dsn": "oracle+oracledb://app:app@oracle:1521/FREEPDB1"},
    extension_config={
        "adk": {
            "session_table": "adk_session",
            "events_table": "adk_event",
            "memory_table": "adk_memory",
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
    return await service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state={})
```

The ADK `Runner` then takes this `service` wherever it needs a `BaseSessionService`.

## Example: SessionStore in Use

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.adapters.asyncpg.adk import AsyncpgADKStore
from sqlspec.extensions.adk import SQLSpecSessionService


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"},
    extension_config={
        "adk": {
            "session_table": "adk_session",
            "events_table": "adk_event",
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

`SQLSpecSessionService` accepts async and sync stores. Sync store calls are bridged through SQLSpec's bounded async bridge because ADK's `BaseSessionService` interface is async. Memory has both `SQLSpecMemoryService` and `SQLSpecSyncMemoryService` surfaces.

## Maintenance & Pruning

`sqlspec.extensions.adk` provides retention helpers for sessions, events, memory, user state, and artifacts. They accept a compatible store or database config, except `prune_artifacts()`, which requires an `SQLSpecArtifactService` because it also removes content objects.

- `prune_sessions(target, idle_days=..., app_name=...)` / `prune_sessions_sync(...)`
- `prune_events(target, older_than_days=..., app_name=...)` / `prune_events_sync(...)`
- `prune_memory(target, older_than_days=..., app_name=..., scope=...)` / `prune_memory_sync(...)`
- `prune_artifacts(service, older_than_days=..., app_name=...)` / `prune_artifacts_sync(...)`
- `prune_user_state(target, idle_days=..., app_name=...)` / `prune_user_state_sync(...)`

Each function returns a `PruneReport` TypedDict with `deleted_count`, `elapsed_ms`, and `table`.

Use `scope="user"` or `scope="app"` with `prune_memory()` to limit retention to that memory scope; `scope="all"` covers both.

### CLI Commands

The `sqlspec` CLI includes ADK memory maintenance commands:

```bash
# Clean up memory older than 30 days
sqlspec adk memory cleanup --days 30

# Verify memory store integrity
sqlspec adk memory verify
```

## Public API Summary

Top-level exports from `sqlspec.extensions.adk`:

- `SQLSpecSessionService`, `SQLSpecMemoryService`, `SQLSpecSyncMemoryService`, `SQLSpecArtifactService`
- `BaseAsyncADKStore`, `BaseSyncADKStore`
- `BaseAsyncADKMemoryStore`, `BaseSyncADKMemoryStore`
- `BaseAsyncADKArtifactStore`, `BaseSyncADKArtifactStore`
- `StoredSession`, `StoredEvent`, `StoredMemory`, `StoredArtifact`
- `PruneReport`, `SessionOrderBy`
- `prune_sessions`, `prune_events`, `prune_memory`, `prune_artifacts`, `prune_user_state`
- `ADKConfig` (TypedDict describing `extension_config["adk"]`)

`SQLSpecSessionService.append_event()` uses the store's `append_event_and_update_state()` as the durable write boundary. The event insert, session state update, and app/user scoped-state upserts succeed together. `temp:` state is stripped before persistence; `app:` and `user:` state live in separate tables and are merged back when sessions load.

## Cross References

- [extensions.md](extensions.md) — the wider Litestar plugin surface.
- [storage.md](storage.md) — storage backends used for artifact content.
- [migrations.md](migrations.md) — how ADK tables get created via `include_extensions=["adk"]`.
- [vector-search.md](vector-search.md) — vector search and semantic retrieval for agent workflows.
