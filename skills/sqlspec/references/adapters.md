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
| MSSQL Python | `"mssql_python"` | `tsql` | QMARK (`?`) | `helper` | Both | SQL Server native |
| MysqlConnector | `"mysqlconnector"` | `mysql` | PYFORMAT (`%s`) | `helper` | Both | MySQL native |
| OracleDB | `"oracledb"` | `oracle` | NAMED_COLON (`:name`) | `helper` | Both | Oracle DB API |
| PSQLPy | `"psqlpy"` | `postgres` | NUMERIC (`$1`) | `helper` | Yes | Rust-backed |
| Psycopg | `"psycopg"` | `postgres` | PYFORMAT (`%s`) | `helper` | Both | psycopg adapt |
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
| Row streaming with `select_stream()` / `fetch_stream()` | `asyncpg`, `cockroach_asyncpg`, `psycopg`, `cockroach_psycopg`, `psqlpy`, `pymysql`, `aiomysql`, `asyncmy`, `mysqlconnector`, `sqlite`, `aiosqlite`, `oracledb`, `bigquery` | `adbc`, `duckdb`, `mssql_python`, `arrow_odbc`, and `spanner` use eager fallback only. Use `native_only=True` when fallback would violate memory bounds. |
| Arrow export with native `select_to_arrow()` override | `adbc`, `arrow_odbc`, `duckdb`, `bigquery`, `spanner`, `mssql_python`, `oracledb` | Other adapters use the base dict-to-Arrow conversion for `select_to_arrow()`; `native_only=True` raises there. `config.supports_arrow_streaming` is a streaming capability flag, not a separate API. |
| Native ingest through `load_from_arrow()` / `load_from_records()` | PostgreSQL family, MySQL family, SQLite family, `adbc`, `duckdb`, `oracledb`, `bigquery`, `spanner`, `mssql_python`, `arrow_odbc` | `load_from_records()` normalizes to Arrow first. MySQL local-infile, Oracle direct path load, BigQuery Storage Write API, and Spanner Batch Write API have explicit gates. |
| ADK session/event and memory stores | `asyncpg`, `psycopg`, `psqlpy`, `cockroach_asyncpg`, `cockroach_psycopg`, `aiomysql`, `asyncmy`, `mysqlconnector`, `pymysql`, `aiosqlite`, `sqlite`, `oracledb`, `duckdb`, `adbc`, `spanner` | BigQuery and `mssql_python` are not ADK backends. Artifact service contracts exist, but concrete adapter artifact metadata stores are deployment-provided. |
| Cloud job/session controls | `bigquery`, `spanner` | BigQuery controls live in `BigQueryConfig.driver_features`; Spanner controls live in `SpannerSyncConfig.driver_features`, per-call kwargs, and `provide_session()` / `provide_read_session()`. |

---

## Transaction Detection Patterns

Each adapter MUST override `_connection_in_transaction()`. The detection method varies by driver:

| Adapter | Detection Pattern |
| --- | --- |
| AsyncPG / CockroachDB Asyncpg | `self.connection.is_in_transaction()` |
| Psycopg / CockroachDB Psycopg | `self.connection.info.transaction_status != IDLE` |
| SQLite / AioSQLite | `self.connection.in_transaction` |
| DuckDB | `self.connection.begin()` state tracking |
| OracleDB | `self.connection.autocommit` check |
| AsyncMy / PyMySQL / MysqlConnector | Server status flag inspection |
| BigQuery | Always `False` (jobs are atomic) |
| Spanner | Session-level transaction tracking |
| ADBC | Always `False` (explicit BEGIN, no introspection) |
| PSQLPy | Connection status enum check |

```python
class MyAdapterDriver(SyncDriverAdapterBase):
    def _connection_in_transaction(self) -> bool:
        # AsyncPG: return self.connection.is_in_transaction()
        # SQLite: return self.connection.in_transaction
        # Psycopg: return self.connection.info.transaction_status != IDLE
        ...
```

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

## Standardized core.py Functions

Each adapter's `core.py` module exports these helpers:

| Function | Purpose | Signature |
| --- | --- | --- |
| `collect_rows` | Extract rows from cursor | `(data, description) -> tuple[list[dict], list[str]]` |
| `resolve_rowcount` | Get affected row count | `(cursor) -> int` |
| `normalize_execute_parameters` | Prepare single params | `(params) -> Any` |
| `normalize_execute_many_parameters` | Prepare batch params | `(params) -> Any` |
| `build_connection_config` | Transform raw config | `(config) -> dict` |
| `raise_exception` | Map to SQLSpec exceptions | `(error) -> NoReturn` |

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

## Driver Implementation Guide

### Required Methods

```python
class MyDriver(SyncDriverAdapterBase):
    dialect: DialectType = "mydialect"

    def with_cursor(self, connection: Any) -> Any:
        """Return context manager for cursor."""

    def handle_database_exceptions(self) -> "AbstractContextManager[None]":
        """Exception handling context."""

    def begin(self) -> None:
        """Begin transaction."""

    def commit(self) -> None:
        """Commit transaction."""

    def rollback(self) -> None:
        """Rollback transaction."""

    def dispatch_special_handling(self, cursor: Any, statement: "SQL") -> None:
        """Hook for database-specific operations (COPY, bulk ops)."""

    def dispatch_execute(self, cursor: Any, statement: "SQL") -> "ExecutionResult":
        """Execute single statement."""
```

---

## Specific Adapter Notes

### ADBC

- Returns `False` for `_connection_in_transaction()` since ADBC uses explicit `BEGIN` and does not expose reliable transaction state.
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
- Oracle Advanced Queuing support for event channels.
