# SQLSpec Arrow & ADBC Integration

## Overview

SQLSpec exposes Arrow through `select_to_arrow()` / `fetch_to_arrow()` for export and the storage bridge methods for ingest. The export call returns `ArrowResult`, not a bare `pyarrow.Table`.

Use Arrow for analytics, ETL, cross-database transfers, and native bulk ingest. Use row APIs for small request/response CRUD paths.

---

## select_to_arrow()

```python
arrow_result = await db_session.select_to_arrow(
    "SELECT * FROM large_dataset WHERE region = $1",
    region,
    return_format="table",
    native_only=False,
)

table = arrow_result.data
print(arrow_result.rows_affected)
```

Supported `return_format` values:

| Value | Payload |
| --- | --- |
| `"table"` | Single `pyarrow.Table` |
| `"batch"` | Single `pyarrow.RecordBatch` |
| `"batches"` | Iterator of `RecordBatch` objects |
| `"reader"` | `pyarrow.RecordBatchReader` |

Use `batch_size=` for batch and reader shapes. Use `arrow_schema=` to cast or stabilize schema. Set `native_only=True` when conversion fallback would hide a performance or memory bug.

### Native Export Paths

| Adapter | Export behavior |
| --- | --- |
| `adbc` | ADBC native Arrow reader/table path |
| `arrow_odbc` | ODBC Arrow batch reader path |
| `duckdb` | DuckDB native Arrow result path |
| `bigquery` | BigQuery native Arrow result path with configured job controls |
| `spanner` | Spanner native Arrow conversion path |
| `mssql_python` | SQL Server native Arrow/bulk-copy integration |
| `oracledb` | Oracle Arrow export path |
| Other adapters | Dict rows converted to Arrow unless `native_only=True` |

`config.supports_arrow_streaming` advertises adapters with native streamed Arrow export behavior. It is a capability flag, not a separate public `select_arrow_stream()` method.

---

## Row Streaming vs Arrow Results

Use `select_stream()` for row-by-row processing. Use `select_to_arrow(return_format="reader")` for Arrow batch pipelines.

```python
async with db_session.select_stream(
    "SELECT id, payload FROM events ORDER BY id",
    chunk_size=1_000,
    native_only=True,
) as stream:
    async for row in stream:
        await process_row(row)
```

Native row streaming and Arrow streaming are separate capabilities. An adapter can support one without the other.

---

## Ingest From Arrow

Use `load_from_arrow()` for inbound Arrow data.

```python
job = await target_session.load_from_arrow(
    "refined_analytics",
    arrow_result,
    overwrite=False,
)
print(job.telemetry["rows_processed"])
```

Native ingest routes through adapter-specific primitives: PostgreSQL `COPY`, DuckDB registration plus `INSERT ... SELECT`, ADBC `adbc_ingest`, Oracle direct path load when available, BigQuery load jobs or Storage Write API, Spanner mutations or Batch Write API, SQL Server `bulkcopy()`, `arrow_odbc` `bulk_insert_arrow`, SQLite transactional `executemany`, and MySQL `executemany` or gated `LOAD DATA LOCAL INFILE`.

See [bulk-ingest.md](bulk-ingest.md) for adapter gates and caveats.

---

## Cross-Database Arrow Pipeline

```python
source_result = await source_session.select_to_arrow(
    "SELECT * FROM events WHERE updated_at > $1",
    last_sync,
    return_format="table",
)

job = await target_session.load_from_arrow("events", source_result)
```

Guidance:

- Keep `ArrowResult` intact when passing between SQLSpec sessions.
- Use `return_format="reader"` for large exports that downstream code consumes in batches.
- Use `native_only=True` in tests for critical native paths so a conversion fallback cannot pass unnoticed.
- Use `load_from_records()` when data originates as Python records; it normalizes through Arrow and then uses the same ingest surface.

---

## Type Mapping

SQLSpec maps database values to Arrow through adapter-native metadata when available, otherwise through Python dict-row conversion.

| SQL Type | Typical Arrow Type |
| --- | --- |
| INTEGER / BIGINT | `int64` |
| REAL / DOUBLE | `float64` |
| VARCHAR / TEXT | `utf8` |
| BOOLEAN | `bool_` |
| DATE | `date32` |
| TIMESTAMP | `timestamp[us]` |
| DECIMAL | `decimal128` |
| BLOB / BYTEA | `binary` |
| JSON / JSONB | serialized string or adapter-native JSON representation |
| UUID | string unless adapter/native schema preserves UUID semantics |
