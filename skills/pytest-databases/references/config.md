# Configuration

Configuration is fixture-first. Override the package's session-scoped fixture
with the same name in `conftest.py`.

## Override fixtures

```python
import pytest


@pytest.fixture(scope="session")
def postgres_password() -> str:
    return "test-password"


@pytest.fixture(scope="session")
def postgres_image() -> str:
    return "postgres:18-alpine"
```

Image selection is configured by overriding the backend's image fixture in
`conftest.py`.

## Environment-backed fixtures

Version 0.19.0 explicitly reads these environment variable families:

| Plugin | Environment variables |
| --- | --- |
| Core Docker client | `DOCKER_HOST` |
| PostgreSQL | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_11_PORT`–`POSTGRES_18_PORT` |
| pgvector | `PGVECTOR_PORT`, `PGVECTOR_13_PORT`–`PGVECTOR_18_PORT` |
| ParadeDB | `PARADEDB_PORT`, `PARADEDB_15_PORT`–`PARADEDB_18_PORT` |
| AlloyDB Omni | `ALLOYDB_OMNI_PORT`, `ALLOYDB_OMNI_15_PORT`–`ALLOYDB_OMNI_17_PORT` |
| MySQL | `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE` |
| MariaDB | `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_ROOT_PASSWORD`, `MARIADB_DATABASE` |
| Dolt | `DOLT_USER`, `DOLT_PASSWORD`, `DOLT_ROOT_PASSWORD`, `DOLT_DATABASE` |
| MinIO | `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_SECURE`, `MINIO_DEFAULT_BUCKET_NAME` |
| RustFS | `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY`, `RUSTFS_SECURE`, `RUSTFS_DEFAULT_BUCKET_NAME` |

Other configuration values are fixture overrides. For example, override
`oracle_23ai_image`, `bigquery_image`, or `mssql_password` directly in
`conftest.py`.

## Host-port pinning

Leave port fixtures as `None` to use dynamic host ports. Pin a port only for a
runtime constraint:

```python
import pytest


@pytest.fixture(scope="session")
def pgvector_18_port() -> int:
    return 55432
```

The environment equivalent is `PGVECTOR_18_PORT=55432`.

If a container with the generated name is already running, its existing
mapping wins. Start a clean test session when verifying a new pin.
