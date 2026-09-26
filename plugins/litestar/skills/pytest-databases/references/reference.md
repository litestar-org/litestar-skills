# Complete 0.19.0 Fixture Reference

Every plugin module below is published in the immutable `v0.19.0` tag. The
ready-client column is exhaustive: a blank entry means the package expects the
test suite to construct its own client from the service fixture.

## Plugin and provider matrix

| Integration | Plugin module | Service class | Service fixtures | Ready client/provider fixtures | Config & helper fixtures |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | `postgres` | `PostgresService` | `postgres_service`, `postgres_11_service`–`postgres_18_service` | `postgres_connection`, `postgres_11_connection`–`postgres_18_connection` | `postgres_host`, `postgres_user`, `postgres_password`, `postgres_port`, `postgres_11_port`–`postgres_18_port`, `postgres_image` |
| pgvector | `postgres` | `PostgresService` | `pgvector_service`, `pgvector_13_service`–`pgvector_18_service` | `pgvector_connection`, `pgvector_13_connection`–`pgvector_18_connection` | `pgvector_port`, `pgvector_13_port`–`pgvector_18_port`, `pgvector_image` |
| ParadeDB | `postgres` | `PostgresService` | `paradedb_service`, `paradedb_15_service`–`paradedb_18_service` | `paradedb_connection`, `paradedb_15_connection`–`paradedb_18_connection` | `paradedb_port`, `paradedb_15_port`–`paradedb_18_port`, `paradedb_image` |
| AlloyDB Omni | `postgres` | `PostgresService` | `alloydb_omni_service`, `alloydb_omni_15_service`–`alloydb_omni_17_service` | `alloydb_omni_connection`, `alloydb_omni_15_connection`–`alloydb_omni_17_connection` | `alloydb_omni_port`, `alloydb_omni_15_port`–`alloydb_omni_17_port`, `alloydb_omni_image` |
| CockroachDB | `cockroachdb` | `CockroachDBService` | `cockroachdb_service` | `cockroachdb_connection` | `cockroachdb_image`, `cockroachdb_driver_opts` |
| MySQL | `mysql` | `MySQLService` | `mysql_service`, `mysql_56_service`, `mysql_57_service`, `mysql_8_service`, `mysql_84_service`, `mysql_96_service` | — | `mysql_user`, `mysql_password`, `mysql_root_password`, `mysql_database`, `platform` |
| MariaDB | `mariadb` | `MariaDBService` | `mariadb_service`, `mariadb_113_service`, `mariadb_114_service`, `mariadb_122_service` | — | `mariadb_user`, `mariadb_password`, `mariadb_root_password`, `mariadb_database` |
| Dolt | `dolt` | `DoltService` | `dolt_service` | — | `dolt_user`, `dolt_password`, `dolt_root_password`, `dolt_database`, `platform` |
| Oracle | `oracle` | `OracleService` | `oracle_service`, `oracle_18c_service`, `oracle_23ai_service` | `oracle_18c_connection`, `oracle_23ai_connection`, `oracle_startup_connection`* | `oracle_18c_image`, `oracle_18c_service_name`, `oracle_23ai_image`, `oracle_23ai_service_name` |
| SQL Server | `mssql` | `MSSQLService` | `mssql_service` | — | `mssql_image`, `mssql_user`, `mssql_password`, `mssql_database` |
| YugabyteDB | `yugabyte` | `YugabyteService` | `yugabyte_service` | — | `yugabyte_image`, `yugabyte_user`, `yugabyte_password`, `yugabyte_database` |
| MongoDB | `mongodb` | `MongoDBService` | `mongodb_service` | `mongodb_connection`, `mongodb_database` | `mongodb_image` |
| Redis | `redis` | `RedisService` | `redis_service` | — | `redis_host`, `redis_port`, `redis_image` |
| Dragonfly | `redis` | `RedisService` | `dragonfly_service` | — | `dragonfly_host`, `dragonfly_port`, `dragonfly_image` |
| KeyDB | `redis` | `RedisService` | `keydb_service` | — | `keydb_host`, `keydb_port`, `keydb_image` |
| Valkey | `valkey` | `ValkeyService` | `valkey_service` | — | `valkey_host`, `valkey_port`, `valkey_image` |
| Elasticsearch 7/8 | `elastic_search` | `ElasticsearchService` | `elasticsearch_7_service`, `elasticsearch_8_service`, `elasticsearch_service`* | — | `elasticsearch_service_memory_limit` |
| BigQuery emulator | `bigquery` | `BigQueryService` | `bigquery_service` | `bigquery_client` | `bigquery_image`, `platform` |
| Spanner emulator | `spanner` | `SpannerService` | `spanner_service` | `spanner_connection` | `spanner_image` |
| GizmoSQL | `gizmosql` | `GizmoSQLService` | `gizmosql_service` | `gizmosql_connection` | `gizmosql_image`, `gizmosql_username`, `gizmosql_password` |
| Azure Blob/Azurite | `azure_blob` | `AzureBlobService` | `azure_blob_service` | `azure_blob_container_client`, `azure_blob_async_container_client` | `azure_blob_default_container_name`, `azurite_in_memory` |
| MinIO | `minio` | `MinioService` | `minio_service` | — | `minio_access_key`, `minio_secret_key`, `minio_secure`, `minio_default_bucket_name` |
| RustFS | `rustfs` | `RustfsService` | `rustfs_service` | — | `rustfs_access_key`, `rustfs_secret_key`, `rustfs_secure`, `rustfs_default_bucket_name` |

\* **Known 0.19.0 alias caveats**:

- `oracle_startup_connection` depends on `oracle_23ai_startup_connection`, which 0.19.0 does not define. Request `oracle_23ai_connection` or `oracle_18c_connection` instead.
- `elasticsearch_service` depends on `elasticsearch8_service` (missing underscore), which 0.19.0 does not define. Request `elasticsearch_8_service` or `elasticsearch_7_service` directly (or define an `elasticsearch8_service` bridge fixture in `conftest.py`). Also note that `pytest_databases.docker.elastic_search` imports `elasticsearch7` at module load time for both v7 and v8.

There is no built-in plugin module in 0.19.0 for SQLite, standalone DuckDB (DuckDB/SQLite over Arrow Flight SQL is served by `gizmosql`), ClickHouse, OpenSearch, Neo4j/Memgraph, ScyllaDB/Cassandra, Google Cloud Storage, Kafka/Redpanda, RabbitMQ, or Db2. For custom containers, use the core `docker_service.run(...)` fixture.

## Service dataclass attributes and properties

Every service class inherits `host: str`, `port: int`, and `container: Container` from `ServiceContainer`. Backend-specific fields vary by module:

| Service class | Extra fields and properties |
| --- | --- |
| `PostgresService` | `database: str`, `user: str`, `password: str` |
| `CockroachDBService` | `database: str`, `driver_opts: dict[str, Any]` |
| `MySQLService`, `MariaDBService`, `DoltService` | `db: str`, `user: str`, `password: str` |
| `OracleService` | `user: str`, `password: str`, `system_password: str`, `service_name: str` |
| `MSSQLService` | `user: str`, `password: str`, `database: str`, `.connection_string: str` |
| `YugabyteService` | `database: str`, `user: str`, `password: str` |
| `MongoDBService` | `username: str`, `password: str`, `database: str` |
| `RedisService`, `ValkeyService` | `db: int` |
| `ElasticsearchService` | `scheme: str`, `user: str`, `password: str`, `database: int` |
| `BigQueryService` | `project: str`, `dataset: str`, `credentials: Credentials`, `.endpoint: str`, `.client_options: ClientOptions` |
| `SpannerService` | `credentials: Credentials`, `project: str`, `database_name: str`, `instance_name: str`, `.endpoint: str`, `.client_options: ClientOptions` |
| `GizmoSQLService` | `username: str`, `password: str`, `.uri: str` (`grpc+tls://{host}:{port}`) |
| `AzureBlobService` | `connection_string: str`, `account_url: str`, `account_key: str`, `account_name: str` |
| `MinioService`, `RustfsService` | `endpoint: str`, `access_key: str`, `secret_key: str`, `secure: bool` |

## PostgreSQL-family port fixtures

Version 0.19.0 adds optional host-port fixtures:

| Family | Default fixture | Versioned fixtures |
| --- | --- | --- |
| PostgreSQL | `postgres_port` | `postgres_11_port`–`postgres_18_port` |
| pgvector | `pgvector_port` | `pgvector_13_port`–`pgvector_18_port` |
| ParadeDB | `paradedb_port` | `paradedb_15_port`–`paradedb_18_port` |
| AlloyDB Omni | `alloydb_omni_port` | `alloydb_omni_15_port`–`alloydb_omni_17_port` |

When unset, Docker chooses a free host port. Each fixture reads the uppercase
equivalent environment variable, such as `POSTGRES_18_PORT` or
`ALLOYDB_OMNI_17_PORT`.

## Installation extras

| Extra | Bundled client dependency |
| --- | --- |
| `postgres` | `psycopg>=3` |
| `cockroachdb` | `psycopg` |
| `oracle` | `oracledb` |
| `mongodb` | `pymongo` |
| `redis`, `dragonfly`, `keydb` | `redis` (imported by `pytest_databases.docker.redis`) |
| `valkey` | `valkey` (imported by `pytest_databases.docker.valkey`) |
| `elasticsearch7`, `elasticsearch8` | `elasticsearch7` / `elasticsearch` (`elastic_search.py` imports `elasticsearch7` at load time) |
| `bigquery` | `google-cloud-bigquery` |
| `spanner` | `google-cloud-spanner` |
| `gizmosql` | `adbc-driver-flightsql`, `pyarrow` |
| `azure-storage` | `azure-storage-blob` |
| `mysql`, `mariadb`, `mssql`, `yugabyte` | None; install the project's chosen client separately |

Dolt, MinIO, and RustFS have no dedicated extra in 0.19.0. Their service
fixtures use core dependencies; install the application client separately.
