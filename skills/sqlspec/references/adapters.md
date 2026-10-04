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
| IBM Db2 | `"db2"` | `db2` | QMARK (`?`) | `helper` | Both | Db2 CLI / DBI |
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
| Native row streaming | All adapters except `duckdb` and `spanner` | `select_stream(..., native_only=True)` rejects unsupported adapters. ADBC, Arrow ODBC, `db2`, and `mssql_python` expose native stream implementations. |
| Native Arrow export | All adapters except `db2` and `pymssql` | Availability also requires PyArrow. `supports_arrow_streaming` is a separate capability and is not implied by native table export. For native columnar Arrow reads from Db2, use `arrow_odbc` with the IBM CLI/ODBC driver. |
| Native Arrow import | All adapters except `bigquery`, `db2`, and `pymssql` | Check `config.storage_capabilities()` at runtime. `load_from_records()` normalizes through Arrow. |
| ADK session/event and memory stores | Adapter-local `adk` packages, including PostgreSQL, CockroachDB, MySQL, SQLite, Oracle, IBM Db2, DuckDB, ADBC, Arrow ODBC, SQL Server, and Spanner families | BigQuery ships `BigQueryADKStore` only as an analytics-replica/telemetry path (not for live low-latency transactional session writes or memory stores). Verify the concrete store export for the selected adapter instead of inferring it from database support. |
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
| IBM Db2 | text | native (microsecond) | native | string | BLOB |

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

### Enterprise Relational (Oracle / IBM Db2)

- **oracledb**: Thin/Thick sync + async Oracle Database adapter with native JSON/OSON, LOB materialization defaults, and AQ/TxEventQ event transports.
- **db2**: Sync (`Db2SyncConfig`) and async (`Db2AsyncConfig`) IBM Db2 LUW 11.5+ adapter built on `ibm_db` (`ibm_db_dbi`). Pair with `arrow_odbc` when columnar Arrow reads are required.

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
- FlightSQL supports TLS/mTLS, RPC timeouts, message size, cookies, and headers via connection parameters (with native `db_kwargs` taking precedence).

### AsyncPG & PostgreSQL Extension Dialects

- Zero-copy JSON with `driver` strategy (no serialization overhead).
- Native pgvector support, custom codecs, per-query timeouts, and Cloud SQL / AlloyDB connector integration (`psycopg` also exposes null pools and JSON codecs; `psqlpy` supports dense-vector conversion).
- **Modular PostgreSQL extension probing**: on first connection, PostgreSQL adapters (`asyncpg`, `psycopg`, `psqlpy`) probe `pg_extension` for enabled extensions (`enable_pgvector=True` -> `"vector"`, `enable_paradedb=True` -> `"pg_search"`, `enable_pg_textsearch=True` -> `"pg_textsearch"`) via `build_postgres_extension_probe_names()` and `resolve_postgres_extension_state()`.
- When detected, the statement dialect promotes automatically from `"postgres"` to `"paradedb"` (`ParadeDB`), `"pg_textsearch"` (`PGTextSearch`, supporting the `<@>` BM25 ranking operator and pgvector operators), or `"pgvector"` (`PGVector`). All custom dialects are exported from `sqlspec.dialects` (`DB2`, `PGTextSearch`, `PGVector`, `ParadeDB`, `Spangres`, `Spanner`).

### Connection Parameter Aliases & DSN Normalization

Every adapter normalizes common `connection_config` parameter aliases and DSN strings (via adapter `build_connection_config` and `sqlspec.utils.config_tools` helpers `normalize_connection_config`, `parse_mysql_dsn`, and `parse_odbc_connection_string`):

- **PostgreSQL / CockroachDB (`asyncpg`, `psycopg`, `psqlpy`, `cockroach_*`)**: normalizes `dsn` / `conninfo` / `url` / `connection_string`, `database` / `dbname` / `db`, and `user` / `username` into the driver's native keyword arguments.
- **SQLite / DuckDB (`sqlite`, `aiosqlite`, `duckdb`)**: normalizes `database` / `path` / `uri` / `dsn` and strips `sqlite://` or `duckdb://` URI prefixes when appropriate.
- **MySQL (`asyncmy`, `aiomysql`, `pymysql`, `mysqlconnector`)**: parses `mysql://` DSNs (`parse_mysql_dsn`) and normalizes `user` / `username`, `password` / `passwd`, `database` / `db`.
- **IBM Db2 (`db2`)**: `Db2ConnectionParams` (`database`, `hostname`, `port`, `protocol`, `user`, `password`, `current_schema`, `security`, `ssl_server_certificate`, `authentication`, `connect_timeout`, `autocommit`, `dsn`, `extra`) renders IBM CLI keywords (`DATABASE`, `HOSTNAME`, `PORT`, `PROTOCOL`, `UID`, `PWD`, `CURRENTSCHEMA`, `SECURITY`, `SSLSERVERCERTIFICATE`, `AUTHENTICATION`, `CONNECTTIMEOUT`) or parses `KEY=VALUE;...` strings and `db2://...` URLs via `build_connection_config`.
- **OracleDB / PyMSSQL / MSSQL / Arrow ODBC / ADBC / BigQuery / Spanner**: normalizes DSN/URI aliases (`dsn` / `url` / `uri` / `connection_string`), user/password/database keys, and semicolon-delimited ODBC strings (`parse_odbc_connection_string`).

### DuckDB

- Native Apache Arrow support for `select_to_arrow()` and `load_from_arrow()`.
- Direct object-store routing for `load_from_storage()` and `select_to_storage()` (`s3://`, `gs://`, `gcs://`, `r2://`) when native DuckDB secrets are configured.
- `DuckDBExtensionConfig` separates install and load lifecycle: `install=True` forces an `install_extension()` call, `force_install=True` reinstalls, and `required=True` turns load/install failures from best-effort warnings into exceptions.

### BigQuery

- Uses `google-cloud-bigquery` job execution model.
- Recommends Storage Read API for large Arrow dataset extraction and `EXPORT DATA` (`enable_native_storage=True` default, plus `native_export_connection` for cross-cloud S3/Azure exports) for `select_to_storage()`.
- Supports explicit `STRUCT` parameters, typed empty arrays, and configurable Storage Write API stream modes (`storage_write_stream_type="PENDING" | "COMMITTED"`, defaulting to atomic `"PENDING"`).
- Parameter style `@name` requires NAMED_AT binding.

### CockroachDB

- Built-in retry logic for serialization conflicts (`40001`).
- Follower reads capability for reduced query latency and opt-in `enable_export_into` / `enable_import_into` storage bridge paths.
- Available in both asyncpg and psycopg variants.

### OracleDB

- Supports both sync and async modes via `oracledb` thin/thick client (async pools reject Thick mode before opening).
- Named parameter binding with `:name` style.
- Defaults `fetch_lobs=False`, which materializes supported LOBs as `str` or `bytes`. Set `fetch_lobs=True` only when code needs native LOB locators.
- Native JSON, `IS JSON` CLOB/BLOB, and OSON columns decode through metadata-aware handlers. Plain CLOB/BLOB values are never JSON-decoded by content heuristics.
- Event channels support opt-in `aq` and `txeventq`; `poll_queue` remains the Oracle default.

### IBM Db2 (`sqlspec.adapters.db2` & `sqlspec.dialects.db2`)

- Targets **Db2 for Linux, UNIX and Windows (LUW) 11.5+** (`SYSCAT` catalog reflection); Db2 for z/OS and Db2 for IBM i are not supported.
- Exports `Db2SyncConfig`, `Db2SyncDriver`, `Db2AsyncConfig`, `Db2AsyncDriver`, `Db2ConnectionParams`, `Db2PoolParams`, `Db2AsyncPoolParams`, `Db2DriverFeatures`, `Db2SyncDataDictionary`, `Db2AsyncDataDictionary`, `Db2VersionInfo`, `build_connection_config`, and `default_statement_config`.
- `Db2DriverFeatures` supports `enable_lowercase_column_names` (defaults to `True`, normalizing implicit uppercase `SYSCAT`/result column names while preserving quoted mixed-case names), `on_connection_create`, `json_serializer`, `json_deserializer`, `enable_events`, and `events_backend` (`"poll_queue"`).
- Ships first-party extension stores across sync and async configs:
  - **Litestar sessions**: `Db2SyncStore`, `Db2AsyncStore`, `Db2LitestarConfig` (`sqlspec.adapters.db2.litestar`)
  - **Events queue**: `Db2SyncEventQueueStore`, `Db2AsyncEventQueueStore`, `Db2EventsConfig` (`sqlspec.adapters.db2.events`)
  - **Google ADK**: `Db2SyncADKStore`, `Db2AsyncADKStore`, `Db2SyncADKMemoryStore`, `Db2AsyncADKMemoryStore` (`sqlspec.adapters.db2.adk`)
- **Built-in `db2` SQLGlot dialect (`sqlspec.dialects.db2.DB2`, `DB2Tokenizer`)**: renders `FETCH FIRST n ROWS ONLY` and `OFFSET m ROWS FETCH NEXT n ROWS ONLY` paging, `SYSIBM.SYSDUMMY1` for `SELECT` without `FROM`, special registers (`CURRENT TIMESTAMP`, `CURRENT DATE`, `CURRENT SCHEMA`, `CURRENT SERVER`, `CURRENT TIMEZONE`), labeled durations, `MERGE` upserts (`sql.upsert(..., dialect="db2")`), and translates query-builder row locks (`for_update()` -> `WITH RS USE AND KEEP UPDATE LOCKS`, `for_share()` -> `WITH RS USE AND KEEP SHARE LOCKS`, `skip_locked=True` -> `SKIP LOCKED DATA`). Do not install `db2-sqlglot-dialect` alongside SQLSpec (conflicts on the `db2` entry point and `sqlglot` version pin).
- **Linux `aarch64` / platform wheel note for `ibm-db>=3.3.0`**: `sqlspec[db2]` installs `ibm_db>=3.3.0`, which publishes prebuilt Linux wheels only for `manylinux_2_34` `x86_64` (bundled `clidriver` requires glibc 2.34+). On Linux `aarch64` or other platforms without prebuilt wheels, `pip`/`uv` builds `ibm_db` from source and requires `CLIDRIVER_VERSION=v11.5.9` or `IBM_DB_HOME` pointing at an existing Db2 client installation; multi-arch projects commonly guard `ibm-db>=3.3.0` with a platform marker (`platform_machine != 'aarch64'`).
- **Arrow ODBC Db2 support**: `arrow_odbc` also supports IBM Db2 through the IBM CLI/ODBC driver (detecting the `db2` dialect strictly from the ODBC driver name, defaulting `enable_lowercase_column_names=True`, and supporting Litestar, Events, and ADK stores).
