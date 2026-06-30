# SQLSpec Driver Method Reference

## Overview

All database interactions go through driver adapters. Async adapters extend `AsyncDriverAdapterBase`; sync adapters extend `SyncDriverAdapterBase`. The public method surface is parallel: async drivers use `await`, sync drivers do not.

Use the current method names. `select_many()` and `copy_from_arrow()` are not public SQLSpec APIs in `v0.51.0`.

Bind normal query parameters as variadic positional arguments. Use `await db_session.select("... WHERE id = $1", user_id, schema_type=User)`, not `await db_session.select(..., [user_id], ...)`. Keep list or tuple containers for real batch/data payloads such as `execute_many()` parameter sets or `load_from_records()` rows.

---

## Query Methods

### select() / fetch() -- Multiple Rows

Return a list of rows. `fetch()` is an alias for users coming from asyncpg-style naming.

```python
users = await db_session.select(
    "SELECT * FROM users WHERE active = $1",
    True,
    schema_type=User,
)
```

When `schema_type` is omitted, rows are dicts. `schema_type` supports Pydantic models, dataclasses, msgspec structs, attrs classes, and TypedDicts.

### select_one() -- Single Row (Strict)

Return exactly one row. SQLSpec maps the no-row case to `NotFoundError`; multiple rows remain a `ValueError` from result cardinality validation.

```python
user = await db_session.select_one(
    "SELECT * FROM users WHERE id = $1",
    user_id,
    schema_type=User,
)
```

### select_one_or_none() -- Single Row (Optional)

Return one row or `None`. More than one row raises `ValueError`.

```python
user = await db_session.select_one_or_none(
    "SELECT * FROM users WHERE email = $1",
    email,
    schema_type=User,
)
```

### select_value() / select_value_or_none() -- Scalar Values

Use `value_type=` to narrow and coerce the returned scalar.

```python
count = await db_session.select_value(
    "SELECT COUNT(*) FROM users WHERE active = $1",
    True,
    value_type=int,
)
```

### select_with_total() -- Pagination

Return rows plus total count for pagination. Use `count_with_window=True` only when the target dialect and query shape support the window-count path.

```python
users, total = await db_session.select_with_total(
    "SELECT * FROM users WHERE active = $1 ORDER BY name LIMIT $2 OFFSET $3",
    True,
    20,
    40,
    schema_type=User,
)
```

### select_stream() / fetch_stream() -- Row Streaming

Return a context-managed row stream fetched in chunks. Use `native_only=True` when eager fallback would be incorrect for memory use.

```python
async with db_session.select_stream(
    "SELECT id, payload FROM events ORDER BY id",
    chunk_size=1_000,
    native_only=True,
) as stream:
    async for row in stream:
        await process(row)
```

Native row streaming support is discoverable via `config.supports_native_row_streaming`.

Native paths:

- `psycopg` / `cockroach_psycopg`: server-side named cursors.
- `asyncpg` / `cockroach_asyncpg`: cursors inside a stream-owned transaction.
- `pymysql`, `aiomysql`, `asyncmy`: `SSCursor`.
- `mysqlconnector`: unbuffered cursors.
- `sqlite`, `aiosqlite`, `oracledb`: chunked `fetchmany()`.
- `psqlpy`: server-side cursor with `array_size`.
- `bigquery`: page-wise result iteration.

Eager fallback only: `adbc`, `duckdb`, `mssql_python`, `arrow_odbc`, and `spanner`.

Lifetime rules:

- Close or exhaust the stream before issuing another statement on the same connection.
- PostgreSQL-family streams open their own transaction or savepoint and close it when the stream closes.
- MySQL unbuffered cursors drain remaining rows when closed mid-iteration.
- BigQuery `page_size` is advisory.
- Oracle streams return raw driver values for LOB columns.
- If iteration raises on PostgreSQL drivers, roll back before reusing the connection.

### select_to_arrow() / fetch_to_arrow() -- Arrow Result

Return an `ArrowResult`, not a bare `pyarrow.Table`. Use `return_format=` to choose `table`, `batch`, `batches`, or `reader`.

```python
arrow_result = await db_session.select_to_arrow(
    "SELECT * FROM large_dataset WHERE region = $1",
    region,
    return_format="reader",
    batch_size=10_000,
)
```

Adapters without native Arrow export use dict-to-Arrow conversion. Add `native_only=True` only when the selected adapter has a native Arrow override and fallback would hide a performance or memory bug.

---

## DML Methods

### execute() -- Single Statement

Execute a statement and return `SQLResult`.

```python
result = await db_session.execute(
    "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id",
    "Alice",
    "alice@example.com",
)
print(result.rows_affected)
print(result.last_inserted_id)
```

### execute_many() -- Batch DML

Execute one statement with multiple parameter sets. Use tuple/list parameters for positional styles and mapping parameters for named styles.

```python
result = await db_session.execute_many(
    "INSERT INTO users (name, email) VALUES ($1, $2)",
    [
        ("Alice", "alice@example.com"),
        ("Bob", "bob@example.com"),
    ],
)
print(result.rows_affected)
```

For high-volume ingest, prefer `load_from_records()` or `load_from_arrow()` when the adapter supports native ingest.

---

## Storage Bridge Methods

### load_from_arrow()

Load an Arrow table or coercible Arrow source into a target table through the adapter's native ingest path.

```python
job = await db_session.load_from_arrow("orders", arrow_result, overwrite=False)
print(job.telemetry["rows_processed"])
```

### load_from_storage()

Load a staged artifact, local path, or cloud URI into a target table.

```python
job = await db_session.load_from_storage(
    "orders",
    "gs://bucket/orders.parquet",
    file_format="parquet",
)
```

### load_from_records()

Normalize in-memory mapping or positional records into Arrow, then route through `load_from_arrow()`.

```python
await db_session.load_from_records(
    "orders",
    [{"id": 1, "total": 9.99}, {"id": 2, "total": 4.50}],
)

await db_session.load_from_records(
    "orders",
    [(3, 1.0), (4, 2.0)],
    columns=["id", "total"],
)
```

Empty records, mismatched mapping keys, and positional width mismatches raise `ImproperConfigurationError`.

---

## Transaction Methods

### begin() / commit() / rollback()

Use explicit transaction control only when a higher-level session or framework commit mode is not managing the transaction.

```python
await db_session.begin()
try:
    await db_session.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", 100, from_id)
    await db_session.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", 100, to_id)
    await db_session.commit()
except Exception:
    await db_session.rollback()
    raise
```

### provide_session() Context Manager

Use `SQLSpec.provide_session(config)` or `config.provide_session()` for lifecycle scoping. Framework integrations usually provide this per request.

```python
async with config.provide_session() as session:
    await session.execute("INSERT INTO logs (msg) VALUES ($1)", "started")
```

---

## Method Summary

| Method | Returns | Notes |
| --- | --- | --- |
| `select()` / `fetch()` | `list[T]` or `list[dict]` | Multiple rows |
| `select_one()` / `fetch_one()` | `T` or `dict` | No row becomes `NotFoundError`; multiple rows raise `ValueError` |
| `select_one_or_none()` / `fetch_one_or_none()` | `T \| dict \| None` | Optional row |
| `select_value()` / `fetch_value()` | Scalar | Optional `value_type=` coercion |
| `select_value_or_none()` / `fetch_value_or_none()` | Scalar or `None` | Optional scalar |
| `select_with_total()` / `fetch_with_total()` | `tuple[list[T], int]` | Pagination |
| `select_stream()` / `fetch_stream()` | `SyncRowStream` / `AsyncRowStream` | Context-managed chunk stream |
| `select_to_arrow()` / `fetch_to_arrow()` | `ArrowResult` | `return_format="table" \| "batch" \| "batches" \| "reader"` |
| `execute()` | `SQLResult` | Check `rows_affected`, `last_inserted_id`, `metadata` |
| `execute_many()` | `SQLResult` | Batch parameters |
| `load_from_arrow()` | `StorageBridgeJob` | Native ingest where supported |
| `load_from_storage()` | `StorageBridgeJob` | Staged files/cloud URIs |
| `load_from_records()` | `StorageBridgeJob` | Records normalized through Arrow |
