# SQLSpec Storage

SQLSpec has two distinct storage concerns:

1. `sqlspec.storage` moves Arrow/row payloads between drivers and object stores.
2. Adapter `extension_config` controls the database tables used by ADK, Litestar sessions, and durable event queues.

Do not treat extension stores as `sqlspec.storage` backends.

## Object-Store Registry

`StorageRegistry` resolves a URI or registered alias to one of three backends:

| Backend | Use |
| --- | --- |
| `LocalStore` | Zero-dependency local filesystem access |
| `ObStoreBackend` | Preferred object-store implementation when `obstore` supports the URI |
| `FSSpecBackend` | Fallback and support for HTTP, HTTPS, FTP, SFTP, and SSH |

```python
from sqlspec.storage import StorageRegistry


registry = StorageRegistry()
registry.register_alias(
    "exports",
    "s3://analytics-bucket",
    base_path="daily",
)

store = registry.get("exports")
```

Install `sqlspec[obstore]` or `sqlspec[fsspec]` for cloud storage. Local paths always have the built-in local fallback. Pass `backend="local"`, `"obstore"`, or `"fsspec"` only when backend selection must be explicit.

## Storage Pipelines

`SyncStoragePipeline` and `AsyncStoragePipeline` implement staging, partition fan-out, cleanup, CSV/JSON/NDJSON/Arrow/Parquet payload handling, and telemetry. Driver methods such as `select_to_storage()` and `load_from_storage()` use the same bridge vocabulary:

- `StorageCapabilities` describes the selected driver's supported import/export paths.
- `StorageLoadRequest` describes a staging allocation.
- `StagedArtifact` carries cleanup and expiry metadata.
- `StorageBridgeJob` is a completed operation handle with `job_id`, `status`, and telemetry.

Check the adapter capability matrix before calling driver storage methods. A method existing on the shared driver base does not mean every adapter has a native or supported implementation.

## Bridge Diagnostics

```python
from sqlspec.storage import (
    get_storage_bridge_diagnostics,
    get_storage_bridge_metrics,
    reset_storage_bridge_metrics,
)


metrics = get_storage_bridge_metrics()
diagnostics = get_storage_bridge_diagnostics()
reset_storage_bridge_metrics()
```

The process-level metrics report bytes written and partitions created. Diagnostics add serializer-cache metrics. Treat them as in-process diagnostics, not a durable job registry.

## Extension-Table Storage

Put database-table settings under the matching extension block:

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    extension_config={
        "litestar": {
            "session_table": "litestar_session",
            "manage_schema": True,
        },
        "events": {
            "backend": "notify_queue",
            "queue_table": "sqlspec_event_queue",
            "manage_schema": True,
        },
        "adk": {
            "session_table": "adk_session",
            "events_table": "adk_event",
            "memory_table": "adk_memory",
            "manage_schema": True,
        },
    },
)
```

SQLSpec 0.56 validates backend-specific extension storage keys. Unknown keys and options that the selected backend cannot honor raise `ImproperConfigurationError`; they are not ignored.

Schema lifecycle controls are:

- `manage_schema`: reconcile the canonical extension schema.
- `create_schema`: allow creation when a table is absent.
- `run_migrations`: run the extension's migration lifecycle where supported.

Additive reconciliation creates missing tables and columns. Renames, drops, and incompatible type changes require an explicit migration.

Backend-specific tuning includes PostgreSQL table/autovacuum settings, MySQL and MariaDB table/index options, BigQuery partition settings, Spanner sharding/table/index options, CockroachDB session hash sharding and row TTL, SQLite PRAGMA profiles, and Oracle compression/partitioning/In-Memory/table options. Use only keys documented by the selected adapter.

## ADK and Framework Stores

Adapter-local `adk`, `events`, and `litestar` packages expose concrete database stores. Instantiate them only when integrating those systems directly; normal framework and ADK integrations construct them from the registered adapter config.

BigQuery does not provide an ADK session or memory backend. Artifact service protocols exist under the ADK extension, but SQLSpec does not claim a concrete artifact metadata store for every adapter.

## Cross References

- [adapters.md](adapters.md) — adapter and native capability matrix.
- [arrow.md](arrow.md) — Arrow result/export behavior.
- [bulk-ingest.md](bulk-ingest.md) — adapter-supported ingest paths.
- [events.md](events.md) — event transport and durable-queue semantics.
- [adk.md](adk.md) — ADK session and memory stores.
