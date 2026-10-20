# Operations, Listeners, and Serialization

High-level bulk/upsert operations and session-event listeners that sit above the repository layer, plus the msgspec-aware JSON encoder used across the library.

## `advanced_alchemy.operations`

Core exports (`__all__ = ("MergeStatement", "OnConflictUpsert", "UpsertKind", "UpsertStrategy", "resolve_column_default", "resolve_upsert_strategy", "validate_identifier")`). These are dialect-aware SQL building blocks — the repository and service layers (and the Litestar `store` / `session` backends) call them under the hood when you use `upsert()` / `upsert_many()` with `match_fields`.

### `OnConflictUpsert` (Single-Row and Bulk)

Cross-dialect native upsert — dispatches to PostgreSQL / SQLite / DuckDB / CockroachDB `ON CONFLICT DO UPDATE` or MySQL / MariaDB `ON DUPLICATE KEY UPDATE`.

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

`supports_native_upsert(dialect_name)` returns `True` for `postgresql`, `sqlite`, `duckdb`, `cockroachdb`, `mysql`, and `mariadb`. It returns `False` for `oracle`, `mssql`, and `spanner+spanner` — use `create_merge_upsert` / `create_merge_many` or `create_insert_or_update_many` there.

#### Bulk Upsert Primitives (`create_upsert_many`, `create_merge_many`, `create_insert_or_update_many`)

Advanced Alchemy 1.12 adds native multi-row upsert statement builders used by `repository.upsert_many()`:

- `OnConflictUpsert.create_upsert_many(table, rows, conflict_columns, update_columns=None, dialect_name=None, validate_identifiers=False, model_type=None) -> Insert`
  - Builds a multi-row `INSERT ... ON CONFLICT (...) DO UPDATE` (PostgreSQL, SQLite, DuckDB, CockroachDB) or `INSERT ... ON DUPLICATE KEY UPDATE` (MySQL, MariaDB).
  - When `model_type` has an `updated_at` column that is not already in `update_columns` or `conflict_columns`, the `DO UPDATE` clause automatically sets `updated_at` to the current UTC timestamp.
- `OnConflictUpsert.create_merge_many(table, rows, conflict_columns, update_columns=None, dialect_name=None, validate_identifiers=False) -> MergeStatement`
  - Builds a multi-row `MERGE` statement for `oracle`, `postgresql` (15+), `cockroachdb`, and `mssql`.
  - Automatically populates missing primary-key or `default` values per row via `resolve_column_default`.
- `OnConflictUpsert.create_insert_or_update_many(table, rows) -> Insert`
  - Builds a Google Cloud Spanner `INSERT OR UPDATE` statement (`dml_strategy="insert_or_update"`), which supports `THEN RETURN` via `.returning(model_type)` when matching on the table's primary key.

### `MergeStatement` + `create_merge_upsert` / `create_merge_many`

`MergeStatement` compiles dialect-specific `MERGE INTO ... USING ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT ...` SQL for:

- **Oracle** (`"oracle"`): `SELECT ... FROM DUAL` for single-row merges, or `UNION ALL` subqueries across `FROM DUAL` for multi-row `create_merge_many`.
- **PostgreSQL 15+ / CockroachDB** (`"postgresql"`): `USING (VALUES (...)) AS src(...)`.
- **SQL Server** (`"mssql"`): `USING (VALUES (...)) AS src(...)` terminated with the T-SQL mandatory trailing semicolon (`;`).

For single-row merges, `OnConflictUpsert.create_merge_upsert(...)` returns a `(MergeStatement, additional_params)` tuple. The `additional_params` dict carries generated values (such as UUID primary keys) that must be merged into the bind parameter dict before `session.execute`:

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

### `resolve_upsert_strategy`, `UpsertStrategy`, and `resolve_column_default`

`resolve_upsert_strategy(table, match_fields, dialect) -> UpsertStrategy` inspects the table's primary key, `UniqueConstraint`s, and `Index(unique=True)` definitions against the active SQLAlchemy `Dialect` to select a cached `UpsertStrategy(kind, supports_returning, conflict_columns, dialect_name)` where `kind: UpsertKind = Literal["on_conflict", "merge", "insert_or_update", "fallback"]`:

- **`"on_conflict"`**: `postgresql`, `cockroachdb`, `sqlite`, `duckdb` (with `supports_returning=True` when the dialect supports `insert_executemany_returning`), and `mysql` / `mariadb` (`supports_returning=False`, and only when the table has a single unambiguous unique key matching `match_fields`).
- **`"merge"`**: `oracle` and `mssql` (`supports_returning=False`).
- **`"insert_or_update"`**: `spanner` / `spanner+spanner` (`supports_returning=True`, only when `match_fields` matches the primary key; non-PK unique columns resolve to `"fallback"`).
- **`"fallback"`**: Returned when `match_fields` does not match a provable non-partial, non-expression unique constraint/PK on the target dialect, or when MySQL/MariaDB has multiple unique keys where `ON DUPLICATE KEY UPDATE` could match an unintended constraint.

`resolve_column_default(arg)` evaluates a SQLAlchemy `ColumnDefault.arg` (returning `arg(None)` or `arg()` for callables, or the literal value otherwise).

### `validate_identifier`

Guardrail for dynamically-built identifiers — accepts only `[a-zA-Z_][a-zA-Z0-9_]*`. Pass `validate_identifiers=True` to `create_upsert`, `create_upsert_many`, `create_merge_upsert`, or `create_merge_many` when any identifier comes from config (never from user input, even validated).

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
    enable_touch_updated_timestamp_listener=False,
)
```

Per-session override via `session.info["enable_file_object_listener"] = False` or `session.info["enable_cache_listener"] = False` is honored at listener-dispatch time.

## Serialization (`advanced_alchemy.utils.serialization`)

Library-wide JSON encoder / decoder — msgspec first, orjson fallback, stdlib `json` last. Used by the cache layer (`cache/serializers.py`), fixture loader (`utils/fixtures.py`), and the `JsonB` column type.

```python
from advanced_alchemy.utils.serialization import decode_json, encode_json

payload: str = encode_json({"id": "abc", "total": 99})
parsed: dict = decode_json(payload)
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
