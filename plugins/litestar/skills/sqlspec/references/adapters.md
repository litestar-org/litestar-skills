# SQLSpec Adapter & Driver Registry

## Full Adapter Registry

| Adapter | Registry Key | Dialect | Parameter Style | JSON Strategy | Async | Type Converter |
| --- | --- | --- | --- | --- | --- | --- |
| ADBC | `"adbc"` | dynamic | varies by driver | `helper` | No | Arrow-native |
| AioMySQL | `"aiomysql"` | `mysql` | QMARK input (`?`) → PYFORMAT execution (`%s`) | `helper` | Yes | MySQL native |
| AioSQLite | `"aiosqlite"` | `sqlite` | QMARK (`?`) | `helper` | Yes | Python stdlib |
| Arrow ODBC | `"arrow_odbc"` | dynamic | QMARK (`?`) | `helper` | No | Arrow-native |
| AsyncMy | `"asyncmy"` | `mysql` | PYFORMAT (`%s`) | `helper` | Yes | MySQL native |
| AsyncPG | `"asyncpg"` | `postgres` | NUMERIC (`$1`) | `driver` | Yes | asyncpg codecs |
| BigQuery | `"bigquery"` | `bigquery` | NAMED_AT (`@name`) | `helper` | No | BQ type mapping |
| CockroachDB Asyncpg | `"cockroach_asyncpg"` | `postgres` | NUMERIC (`$1`) | `driver` | Yes | asyncpg codecs |
| CockroachDB Psycopg | `"cockroach_psycopg"` | `postgres` | PYFORMAT (`%s`) | `helper` | Yes | psycopg adapt |
| DuckDB | `"duckdb"` | `duckdb` | QMARK (`?`) | `helper` | No | Arrow-native |
| MSSQL Python | `"mssql_python"` | `tsql` | QMARK (`?`) | `helper` | No | SQL Server native |
| MysqlConnector | `"mysqlconnector"` | `mysql` | PYFORMAT (`%s`) | `helper` | Both | MySQL native |
| OracleDB | `"oracledb"` | `oracle` | NAMED_COLON (`:name`) | `helper` | Both | Oracle DB API |
| PSQLPy | `"psqlpy"` | `postgres` | NUMERIC (`$1`) | `helper` | Yes | Rust-backed |
| Psycopg | `"psycopg"` | `postgres` | PYFORMAT (`%s`) | `helper` | Both | psycopg adapt |
| PyMSSQL | `"pymssql"` | `tsql` | PYFORMAT (`%s`) input, positional execution | `helper` | No | SQL Server native |
| PyMySQL | `"pymysql"` | `mysql` | PYFORMAT (`%s`) | `helper` | No | MySQL native |
| Spanner | `"spanner"` | `spanner` | NAMED_AT (`@name`) | `helper` | No | Spanner proto |
| SQLite | `"sqlite"` | `sqlite` | QMARK (`?`) | `helper` | No | Python stdlib |

### JSON Strategy

- **`driver`**: The database driver handles JSON serialization natively (AsyncPG, CockroachDB Asyncpg). Zero overhead.
- **`helper`**: SQLSpec serializes JSON values before binding. Works universally.

---

## Capability Snapshot

Check the adapter config flags before building generic tooling:

| Capability | Native adapters | Caveats |
| --- | --- | --- |
| Native row streaming | All adapters except `duckdb` and `spanner` | `select_stream(..., native_only=True)` rejects unsupported adapters. ADBC, Arrow ODBC, and `mssql_python` expose native stream implementations in 0.56. |
| Native Arrow export | All adapters except `pymssql` | Availability also requires PyArrow. `supports_arrow_streaming` is a separate capability and is not implied by native table export. |
| Native Arrow import | All adapters except `bigquery` and `pymssql` | Check `config.storage_capabilities()` at runtime. `load_from_records()` normalizes through Arrow. |
| ADK session/event and memory stores | Adapter-local `adk` packages, including PostgreSQL, CockroachDB, MySQL, SQLite, Oracle, DuckDB, ADBC, and Spanner families | BigQuery is not an ADK backend. Verify the concrete store export for the selected adapter instead of inferring it from database support. |
| Event transports | PostgreSQL: `notify`, `notify_queue`, `poll_queue`; Oracle: `aq`, `txeventq`, `poll_queue`; others: `poll_queue` | Retired names `listen_notify`, `listen_notify_durable`, and `table_queue` raise configuration errors. |
| Cloud job/session controls | `bigquery`, `spanner` | BigQuery controls live in `BigQueryConfig.driver_features`; Spanner controls live in `SpannerSyncConfig.driver_features`, per-call kwargs, and `provide_session()` / `provide_read_session()`. |

---

## Type Converter Behavior

| Adapter | UUID | datetime | Decimal | JSON | bytes |
| --- | --- | --- | --- | --- | --- |
| AsyncPG | native UUID | native | text | native jsonb | native bytea |
| Psycopg | text adapt | text adapt | numeric adapt | jsonb adapt | bytea adapt |
| DuckDB | string cast | native | native | string | native blob |
| SQLite | string | ISO-8601 string | string | string | blob |
| BigQuery | string | BQ TIMESTAMP | BQ NUMERIC | BQ JSON | BQ BYTES |
| OracleDB | RAW(16) | DATE/TIMESTAMP | NUMBER | CLOB/JSON | RAW/BLOB |

---

## When to Choose Which Adapter

### PostgreSQL

- **asyncpg**: Best throughput, native JSON/UUID, and PostgreSQL COPY ingest. Use for high-performance async apps.
- **psycopg**: Broadest compatibility, sync + async, PgBouncer-friendly. Use when you need sync or connection pooling.
- **psqlpy**: Rust-backed async driver. Use when you want Rust performance with Python ergonomics.
- **cockroach_asyncpg / cockroach_psycopg**: CockroachDB-specific. Built-in retry logic for serialization conflicts (`40001`), follower reads.

### MySQL

- **asyncmy**: Async MySQL with good performance. Use for async applications.
- **pymysql**: Pure Python sync driver. Use for simple scripts or when C extensions are unavailable.
- **mysqlconnector**: Oracle's official connector. Use when vendor support matters.

### SQLite

- **sqlite**: Sync stdlib driver. Use for local apps, CLIs, embedded use.
- **aiosqlite**: Async wrapper around stdlib. Use when you need async with SQLite.

### Cloud / Analytical

- **bigquery**: Google BigQuery jobs API. Use Storage Read API for large Arrow datasets.
- **spanner**: Google Cloud Spanner with proto-based types. Globally distributed.
- **duckdb**: In-process OLAP. Native Arrow, zero-copy transfers.
- **adbc**: Apache Arrow Database Connectivity. Use for Arrow-first pipelines.

### Testing

- **sqlite / aiosqlite**: Use for local integration tests that need a real SQL engine.
- **driver fakes**: Use project-local fakes for unit tests that should not exercise SQLSpec's adapter layer.

---

## Specific Adapter Notes

### ADBC

- Optimized for Arrow framework transfers; prefer `select_to_arrow()` over row-based methods.

### AsyncPG

- Zero-copy JSON with `driver` strategy (no serialization overhead).
- Native pgvector support and Cloud SQL connector integration.
- Highest throughput PostgreSQL adapter in benchmarks.

### DuckDB

- Native Apache Arrow support for `select_to_arrow()` and `load_from_arrow()`.
- Best for in-memory analytics and local OLAP workloads.
- `DuckDBExtensionConfig` separates install and load lifecycle: `install=True` forces an `install_extension()` call, `force_install=True` reinstalls, and `required=True` turns load/install failures from best-effort warnings into exceptions.

### BigQuery

- Uses `google-cloud-bigquery` job execution model.
- Recommends Storage Read API for large Arrow dataset extraction.
- Parameter style `@name` requires NAMED_AT binding.

### CockroachDB

- Built-in retry logic for serialization conflicts (`40001`).
- Follower reads capability for reduced query latency.
- Available in both asyncpg and psycopg variants.

### OracleDB

- Supports both sync and async modes via `oracledb` thin/thick client.
- Named parameter binding with `:name` style.
- Defaults `fetch_lobs=False`, which materializes supported LOBs as `str` or `bytes`. Set `fetch_lobs=True` only when code needs native LOB locators.
- Native JSON, `IS JSON` CLOB/BLOB, and OSON columns decode through metadata-aware handlers. Plain CLOB/BLOB values are never JSON-decoded by content heuristics.
- Event channels support opt-in `aq` and `txeventq`; `poll_queue` remains the Oracle default.
