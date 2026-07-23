# Supported Database Patterns

Use the fixture shape that 0.19.0 actually provides. A service fixture exposes
connection coordinates and a live `container`; a ready-client fixture creates
the vendor client for you.

## Ready-client pattern: PostgreSQL

The PostgreSQL plugin installs `psycopg>=3` and returns synchronous
`psycopg.Connection` objects.

```python
import psycopg

pytest_plugins = ["pytest_databases.docker.postgres"]


def test_postgres_connection(
    postgres_connection: psycopg.Connection,
) -> None:
    row = postgres_connection.execute(
        "SELECT current_database()"
    ).fetchone()

    assert row is not None
```

Use `postgres_service` when the project uses a different client:

```python
import psycopg

from pytest_databases.docker.postgres import PostgresService


def test_project_connection(
    postgres_service: PostgresService,
) -> None:
    connection_info = (
        f"postgresql://{postgres_service.user}:"
        f"{postgres_service.password}@{postgres_service.host}:"
        f"{postgres_service.port}/{postgres_service.database}"
    )
    with psycopg.connect(connection_info) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
```

The same module provides PostgreSQL 11–18, pgvector 13–18, ParadeDB 15–18,
and AlloyDB Omni 15–17 service, connection, and host-port fixtures. See
[reference.md](reference.md) for exact names.

## Service-only pattern: MySQL

Version 0.19.0 provides service coordinates but no ready MySQL client fixture.
Choose the client already used by the project and construct it from
`MySQLService`.

```python
from pytest_databases.docker.mysql import MySQLService

pytest_plugins = ["pytest_databases.docker.mysql"]


def test_mysql_coordinates(mysql_service: MySQLService) -> None:
    assert mysql_service.host
    assert mysql_service.port > 0
    assert mysql_service.db
```

Pass these attributes to the project's MySQL client in the integration test.
Apply the same pattern to MariaDB, Dolt, SQL Server, YugabyteDB, Redis,
Dragonfly, KeyDB, Valkey, MinIO, and RustFS. The package validates those
services without forcing a Python client dependency.

## Ready vendor clients

Use the provided client fixture when it matches the project's stack:

- `bigquery_client`
- `spanner_connection`
- `mongodb_connection` and function-scoped `mongodb_database`
- `azure_blob_container_client`
- `azure_blob_async_container_client`
- `gizmosql_connection`
- `cockroachdb_connection`
- `oracle_18c_connection` and `oracle_23ai_connection`

The published `oracle_startup_connection` alias has an unresolved fixture
dependency in 0.19.0; see [reference.md](reference.md) before using it.

MinIO and RustFS expose S3-compatible service coordinates but no bundled S3
client. Use `boto3`, `minio`, or the client already present in the project.

## Services added in 0.18.0–0.19.0

Version 0.18.0 added:

- `dolt_service`
- `rustfs_service` and `rustfs_default_bucket_name`
- `mysql_96_service`
- `mariadb_113_service`, `mariadb_114_service`, and
  `mariadb_122_service`
- the underlying Docker container on every service object through
  `ServiceContainer.container`

Version 0.19.0 added host-port controls and version-specific PostgreSQL-family
providers:

- PostgreSQL 11–18
- pgvector 13–18
- ParadeDB 15–18
- AlloyDB Omni 15–17

Each versioned PostgreSQL-family service has matching `*_connection` and
`*_port` fixtures.
