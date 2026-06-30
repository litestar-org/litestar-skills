# SQLSpec Native Bulk Ingest

## Overview

SQLSpec `v0.51.0` exposes native bulk ingest through three storage bridge methods:

- `load_from_arrow(table, source, *, overwrite=False)` -- load an Arrow table or coercible Arrow source.
- `load_from_storage(table, source, *, file_format, overwrite=False)` -- load a local path or cloud URI.
- `load_from_records(table, records, *, columns=None, overwrite=False)` -- load in-memory rows.

All three return `StorageBridgeJob`; inspect `job.telemetry["rows_processed"]`, `bytes_processed`, and adapter-specific `extra` metadata.

---

## load_from_records()

Use `load_from_records()` for Python records. Mapping rows infer columns from keys; positional rows require `columns=`.

```python
await driver.load_from_records(
    "orders",
    [{"id": 1, "total": 9.99}, {"id": 2, "total": 4.50}],
)

await driver.load_from_records(
    "orders",
    [(3, 1.0), (4, 2.0)],
    columns=["id", "total"],
)
```

Records normalize to Arrow and route through the adapter's `load_from_arrow()` path. Empty input, mismatched mapping keys, and positional width mismatches raise `ImproperConfigurationError`.

---

## Adapter Matrix

| Adapter | Native ingest path | Gate / caveat |
| --- | --- | --- |
| `asyncpg` | `COPY` via `copy_records_to_table` | Always on; atomic with exact row counts |
| `psycopg` sync/async | `COPY` streaming `write_row` | Always on; atomic with exact row counts |
| `psqlpy` | Binary `COPY` with `INSERT` fallback | Always on |
| `adbc` | `adbc_ingest` | Driver-dependent; Flight SQL may fall back per row |
| `duckdb` | register Arrow table, then `INSERT ... SELECT` | Single connection transaction |
| `sqlite` / `aiosqlite` | `executemany` in one `BEGIN IMMEDIATE` | Atomic when the driver owns the transaction |
| `oracledb` | Direct path load in Thin mode; `executemany` fallback | Set `enable_direct_path_load=False` to force fallback |
| `pymysql`, `asyncmy`, `aiomysql`, `mysqlconnector` | `executemany`; opt-in `LOAD DATA LOCAL INFILE` | Requires feature and connection local-infile gate |
| `bigquery` | Parquet load job; optional Storage Write API for appends | `enable_storage_write_api`; `overwrite=True` uses Parquet `WRITE_TRUNCATE` |
| `spanner` | `insert_or_update` mutations; optional Batch Write API | `enable_batch_write_api`; Batch Write commits groups independently |
| `mssql_python` | `cursor.bulkcopy()` | Driver-managed |
| `arrow_odbc` | `bulk_insert_arrow` | Driver-managed |

---

## Security Gates

MySQL `LOAD DATA LOCAL INFILE` reads client-side files. Enable it only when the server, connection, and SQLSpec adapter feature are all intentionally configured:

- `pymysql`, `aiomysql`: `connection_config={"local_infile": True}` plus `driver_features={"enable_local_infile_bulk_load": True}`.
- `asyncmy`: `allow_local_infile=True` is required before `local_infile=True` is honored.
- `mysqlconnector`: `connection_config={"allow_local_infile": True}` plus the feature flag. Honor `allow_local_infile_in_path` when set.

Oracle direct path load is the default in Thin mode when the connection exposes the Direct Path Load API. Thick-mode or unsupported connections fall back to `executemany()`.

BigQuery Storage Write API is append-only in this surface. `overwrite=True` uses a Parquet load job instead.

Spanner Batch Write API uses independently committed mutation groups. Treat it as high-throughput idempotent upsert behavior, not as a single transaction.

---

## Usage Rules

- Use `load_from_records()` for in-memory data instead of hand-written `execute_many()` loops when ingest volume matters.
- Use `load_from_arrow()` when the upstream step already produced Arrow.
- Use `load_from_storage()` for staged files and cloud URIs. BigQuery requires `gs://` staging for load paths.
- Check `config.storage_capabilities()` before building generic ingest tooling.
- Keep adapter gates in configuration. Do not pass invented per-call flags to `load_from_arrow()`.
