# Operations, Listeners, and Serialization

High-level bulk/upsert operations and session-event listeners that sit above the repository layer, plus the msgspec-aware JSON encoder used across the library.

## `advanced_alchemy.operations`

Core exports (`__all__ = ("MergeStatement", "OnConflictUpsert", "validate_identifier")`). These are dialect-aware SQL building blocks — the repository and service layers (and the Litestar `store` / `session` backends) call them under the hood when you use `upsert()` / `upsert_many()` with `match_fields`.

### `OnConflictUpsert`

Cross-dialect native upsert — dispatches to PostgreSQL / SQLite / DuckDB `ON CONFLICT DO UPDATE`, MySQL / MariaDB `ON DUPLICATE KEY UPDATE`, or CockroachDB `ON CONFLICT`.

```python
from advanced_alchemy.operations import OnConflictUpsert
from sqlalchemy.ext.asyncio import AsyncSession

async def upsert_order(session: AsyncSession, order_table, values: dict) -> None:
    dialect_name = session.bind.dialect.name
    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        raise RuntimeError(f"native upsert unsupported for {dialect_name}")
    stmt = OnConflictUpsert.create_upsert(
        table=order_table,
        values=values,
        conflict_columns=["external_id"],
        update_columns=["status", "total"],
        dialect_name=dialect_name,
    )
    await session.execute(stmt)
```

`supports_native_upsert(dialect_name)` is the guard. Defaults to `False` for Oracle / SQL Server — fall back to `create_merge_upsert` there (see below).

### `MergeStatement` + `create_merge_upsert`

For Oracle and PostgreSQL 15+ (when `ON CONFLICT` is not desired), `OnConflictUpsert.create_merge_upsert(...)` returns a `(MergeStatement, additional_params)` tuple. The `additional_params` dict carries generated values (such as Oracle UUID primary keys) that must be merged into the bind parameter dict before `session.execute`.

```python
from advanced_alchemy.operations import OnConflictUpsert

merge_stmt, extra_params = OnConflictUpsert.create_merge_upsert(
    table=order_table,
    values={"external_id": "ord-42", "status": "paid", "total": 99},
    conflict_columns=["external_id"],
    update_columns=["status", "total"],
    dialect_name="oracle",
)
await session.execute(merge_stmt, {**extra_params, "external_id": "ord-42", "status": "paid", "total": 99})
```

### `validate_identifier`

Guardrail for dynamically-built identifiers — accepts only `[a-zA-Z_][a-zA-Z0-9_]*`. Pass `validate_identifiers=True` to `create_upsert` / `create_merge_upsert` when any identifier comes from config (never from user input, even validated).

## Session listeners (`advanced_alchemy._listeners`)

Listeners hook SQLAlchemy `before_flush` / `after_commit` / `after_rollback` events to keep FileObject storage, dogpile cache invalidation, and the `updated_at` column in sync with transaction lifecycle. They are registered automatically when you construct `SQLAlchemyAsyncConfig` / `SQLAlchemySyncConfig` — no manual wiring needed.

Exported listener classes:

- `SyncFileObjectListener` / `AsyncFileObjectListener` — commit / delete pending FileObject blobs on transaction commit; discard on rollback.
- `SyncCacheListener` / `AsyncCacheListener` / `CacheInvalidationListener` — bump model versions and invalidate entity cache keys after a successful commit (see `caching.md`).
- `touch_updated_timestamp` — `before_flush` function that bumps `updated_at` on dirty instances whose mapped class defines that column.

Disable a listener per-config:

```python
from advanced_alchemy.config import SQLAlchemyAsyncConfig

db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/app",
    enable_touch_updated_timestamp_listener=False,  # e.g. for import routines
)
```

Per-session override via `session.info["enable_file_object_listener"] = False` or `session.info["enable_cache_listener"] = False` is honored at listener-dispatch time.

## Serialization (`advanced_alchemy.utils.serialization`)

Library-wide JSON encoder / decoder — msgspec first, orjson fallback, stdlib `json` last. Used by the cache layer (`cache/serializers.py`), fixture loader (`utils/fixtures.py`), and the `JsonB` column type.

```python
from advanced_alchemy.utils.serialization import encode_json, decode_json

payload = encode_json({"id": "abc", "total": 99})  # str
parsed = decode_json(payload)                        # dict
```

The msgspec `Encoder` is configured with an `enc_hook` that serializes `datetime` / `date` / `Enum` / pydantic `BaseModel` by delegating to `_type_to_string`. For round-trippable encoding of `Decimal`, `UUID`, `bytes`, `set`, `timedelta`, use `encode_complex_type` / `decode_complex_type` — they wrap values in `{"__type__": ..., "value": ...}` markers.

## Common pitfalls

- **Upsert semantics are dialect-specific.** PostgreSQL / SQLite use `ON CONFLICT (cols) DO UPDATE SET ...`; MySQL uses `ON DUPLICATE KEY UPDATE` (requires a unique index, not an explicit conflict target); Oracle and PG15+ use `MERGE`. `OnConflictUpsert.create_merge_upsert` on Oracle will auto-generate UUID primary-key values for PKs whose `default.arg` is callable — remember to merge the returned `additional_params` into the execute bind dict.
- **Listener ordering matters.** Cache invalidation listeners read the final committed state; FileObject listeners schedule async I/O. Both defer work until `after_commit`, so a rollback correctly discards pending side effects.
- **`touch_updated_timestamp` respects explicit assignments** — if your code manually sets `instance.updated_at = ...` (import routines, backfills), the listener leaves it alone.

## Cross-references

- [`litestar-fullstack-inertia`](https://github.com/litestar-org/litestar-fullstack-inertia) — uses AA repositories + services with automatic listener wiring in production.
- `references/caching.md` — how `SyncCacheListener` / `AsyncCacheListener` coordinate with `CacheManager`.
- `references/types.md` — `FileObject` column type that `SyncFileObjectListener` tracks.
