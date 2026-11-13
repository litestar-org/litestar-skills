# Xdist Parallel Testing

In `v0.20.0b3`, most Docker providers default their `xdist_*_isolation_level` fixture to `"database"`, sharing one container per session and isolating `pytest-xdist` workers into per-worker databases, schemas, buckets, or prefixes. Exceptions: `bigquery`, `sqlanywhere`, and `teradata` default to `"server"`; `embedded.postgres` defaults to `"template"`; `docker.elastic_search` does not expose an xdist isolation fixture.

- `"database"` (default for most Docker providers): shares one container across workers and provisions a worker-specific logical namespace (`pytest_databases_<worker_num>`, Oracle schema `APP_<worker_num>`, Redis/Valkey DB index, or S3/bucket/topic prefix).
- `"server"` (default for `bigquery`, `sqlanywhere`, `teradata`): launches a dedicated transient container per worker (`_<worker_num>`).
- `"template"` (PostgreSQL family & `embedded.postgres` only; default for `embedded.postgres`): builds and fingerprints a migrated template database once under a `filelock` (`PostgresService.ensure_template`) and clones per-worker databases via `CREATE DATABASE ... TEMPLATE ...` (`PostgresService.create_worker_database_from_template`).

## Exact isolation fixtures

| Plugin | Isolation fixture | Default | Supported values |
| --- | --- | --- | --- |
| PostgreSQL, pgvector, ParadeDB, AlloyDB Omni | `xdist_postgres_isolation_level` | `"database"` | `"database"`, `"server"`, `"template"` |
| Embedded PostgreSQL | `xdist_embedded_postgres_isolation_level` | `"template"` | `"database"`, `"server"`, `"template"` |
| Azure Blob | `azure_blob_xdist_isolation_level` | `"database"` | `"database"`, `"server"` |
| BigQuery | `xdist_bigquery_isolation_level` | `"server"` | `"database"`, `"server"` |
| Cloudflare | `xdist_cloudflare_isolation_level` | `"database"` | `"database"`, `"server"` |
| CockroachDB | `xdist_cockroachdb_isolation_level` | `"database"` | `"database"`, `"server"` |
| Db2 | `xdist_db2_isolation_level` | `"database"` | `"database"`, `"server"` |
| Dolt | `xdist_dolt_isolation_level` | `"database"` | `"database"`, `"server"` |
| Doltgres | `xdist_doltgres_isolation_level` | `"database"` | `"database"`, `"server"` |
| Floci | `xdist_floci_isolation_level` | `"database"` | `"database"`, `"server"` |
| GizmoSQL | `xdist_gizmosql_isolation_level` | `"database"` | `"database"`, `"server"` |
| Hardcharger | `xdist_hardcharger_isolation_level` | `"database"` | `"database"`, `"server"` |
| LocalStack | `xdist_localstack_isolation_level` | `"database"` | `"database"`, `"server"` |
| MariaDB | `xdist_mariadb_isolation_level` | `"database"` | `"database"`, `"server"` |
| MinIO | `xdist_minio_isolation_level` | `"database"` | `"database"`, `"server"` |
| MongoDB | `xdist_mongodb_isolation_level` | `"database"` | `"database"`, `"server"` |
| SQL Server | `xdist_mssql_isolation_level` | `"database"` | `"database"`, `"server"` |
| MySQL | `xdist_mysql_isolation_level` | `"database"` | `"database"`, `"server"` |
| Oracle / ADB-Free | `xdist_oracle_isolation_level` | `"database"` | `"database"`, `"server"` |
| Pub/Sub | `xdist_pubsub_isolation_level` | `"database"` | `"database"`, `"server"` |
| RabbitMQ | `xdist_rabbitmq_isolation_level` | `"database"` | `"database"`, `"server"` |
| Redis, Dragonfly, KeyDB | `xdist_redis_isolation_level` | `"database"` | `"database"`, `"server"` |
| Redpanda | `xdist_redpanda_isolation_level` | `"database"` | `"database"`, `"server"` |
| RustFS | `xdist_rustfs_isolation_level` | `"database"` | `"database"`, `"server"` |
| Snowflake | `xdist_snowflake_isolation_level` | `"database"` | `"database"`, `"server"` |
| Spanner | `xdist_spanner_isolation_level` | `"database"` | `"database"`, `"server"` |
| SQL Anywhere | `xdist_sqlanywhere_isolation_level` | `"server"` | `"database"`, `"server"` |
| Sybase ASE | `xdist_sybase_isolation_level` | `"database"` | `"database"`, `"server"` |
| Teradata Vantage | `xdist_teradata_isolation_level` | `"server"` | `"database"`, `"server"` |
| Valkey | `xdist_valkey_isolation_level` | `"database"` | `"database"`, `"server"` |
| YugabyteDB | `xdist_yugabyte_isolation_level` | `"database"` | `"database"`, `"server"` |

## PostgreSQL `"template"` isolation example

```python  # pragma: prerelease-example
from pathlib import Path
import pytest
from pytest_databases.types import PostgresXdistIsolationLevel


@pytest.fixture(scope="session")
def xdist_postgres_isolation_level() -> PostgresXdistIsolationLevel:
    return "template"


@pytest.fixture(scope="session")
def postgres_template_setup() -> str:
    return "CREATE TABLE IF NOT EXISTS items (id serial PRIMARY KEY, name text NOT NULL);"


@pytest.fixture(scope="session")
def postgres_template_fingerprint_sources() -> list[Path]:
    return [Path("migrations")]
```
