# Complete 0.19.0 Fixture Reference

Every plugin module below is published in the immutable `v0.19.0` tag. The
ready-client column is exhaustive: a blank entry means the package expects the
test suite to construct its own client from the service fixture.

## Plugin and provider matrix

| Integration | Plugin module | Service class | Service fixtures | Ready client/provider fixtures |
| --- | --- | --- | --- | --- |
| PostgreSQL | `postgres` | `PostgresService` | `postgres_service`, `postgres_11_service`–`postgres_18_service` | `postgres_connection`, `postgres_11_connection`–`postgres_18_connection` |
| pgvector | `postgres` | `PostgresService` | `pgvector_service`, `pgvector_13_service`–`pgvector_18_service` | `pgvector_connection`, `pgvector_13_connection`–`pgvector_18_connection` |
| ParadeDB | `postgres` | `PostgresService` | `paradedb_service`, `paradedb_15_service`–`paradedb_18_service` | `paradedb_connection`, `paradedb_15_connection`–`paradedb_18_connection` |
| AlloyDB Omni | `postgres` | `PostgresService` | `alloydb_omni_service`, `alloydb_omni_15_service`–`alloydb_omni_17_service` | `alloydb_omni_connection`, `alloydb_omni_15_connection`–`alloydb_omni_17_connection` |
| CockroachDB | `cockroachdb` | `CockroachDBService` | `cockroachdb_service` | `cockroachdb_connection` |
| MySQL | `mysql` | `MySQLService` | `mysql_service`, `mysql_56_service`, `mysql_57_service`, `mysql_8_service`, `mysql_84_service`, `mysql_96_service` | — |
| MariaDB | `mariadb` | `MariaDBService` | `mariadb_service`, `mariadb_113_service`, `mariadb_114_service`, `mariadb_122_service` | — |
| Dolt | `dolt` | `DoltService` | `dolt_service` | — |
| Oracle | `oracle` | `OracleService` | `oracle_service`, `oracle_18c_service`, `oracle_23ai_service` | `oracle_18c_connection`, `oracle_23ai_connection`, `oracle_startup_connection` |
| SQL Server | `mssql` | `MSSQLService` | `mssql_service` | — |
| YugabyteDB | `yugabyte` | `YugabyteService` | `yugabyte_service` | — |
| MongoDB | `mongodb` | `MongoDBService` | `mongodb_service` | `mongodb_connection`, `mongodb_database` |
| Redis | `redis` | `RedisService` | `redis_service` | — |
| Dragonfly | `redis` | `RedisService` | `dragonfly_service` | — |
| KeyDB | `redis` | `RedisService` | `keydb_service` | — |
| Valkey | `valkey` | `ValkeyService` | `valkey_service` | — |
| Elasticsearch 7/8 | `elastic_search` | `ElasticsearchService` | `elasticsearch_service`, `elasticsearch_7_service`, `elasticsearch_8_service` | — |
| BigQuery emulator | `bigquery` | `BigQueryService` | `bigquery_service` | `bigquery_client` |
| Spanner emulator | `spanner` | `SpannerService` | `spanner_service` | `spanner_connection` |
| GizmoSQL | `gizmosql` | `GizmoSQLService` | `gizmosql_service` | `gizmosql_connection` |
| Azure Blob/Azurite | `azure_blob` | `AzureBlobService` | `azure_blob_service` | `azure_blob_container_client`, `azure_blob_async_container_client` |
| MinIO | `minio` | `MinioService` | `minio_service` | — |
| RustFS | `rustfs` | `RustfsService` | `rustfs_service` | — |

There is no SQLite plugin in 0.19.0. A blank ready-client cell is intentional;
construct the project's chosen client from the corresponding service object.

`oracle_startup_connection` is published, but it depends on a fixture named
`oracle_23ai_startup_connection` that 0.19.0 does not define. Prefer
`oracle_23ai_connection` unless the test suite supplies that dependency.

## PostgreSQL-family port fixtures

Version 0.19.0 adds optional host-side port fixtures:

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
| `redis`, `dragonfly`, `keydb` | `redis` |
| `valkey` | `valkey` |
| `elasticsearch7`, `elasticsearch8` | Matching Elasticsearch client |
| `bigquery` | `google-cloud-bigquery` |
| `spanner` | `google-cloud-spanner` |
| `gizmosql` | `adbc-driver-flightsql`, `pyarrow` |
| `azure-storage` | `azure-storage-blob` |
| `mysql`, `mariadb`, `mssql`, `yugabyte` | None; install the project's chosen client separately |

Dolt, MinIO, and RustFS have no dedicated extra in 0.19.0. Their service
fixtures use core dependencies; install the application client separately.
