# Xdist Parallel Testing

`pytest-databases` uses worker-aware service naming and logical namespaces.
Where exposed, an isolation fixture accepts exactly `"database"` or `"server"`.

- `"database"` shares a container and selects a worker-specific logical
  database/account where the backend implements one.
- `"server"` creates a worker-specific transient container.

The default is `"database"`. Use `"server"` for engines without safe logical
isolation or when tests mutate server-wide state.

## Exact isolation fixtures

| Plugin | Isolation fixture |
| --- | --- |
| Azure Blob | `azure_blob_xdist_isolation_level` |
| BigQuery | `xdist_bigquery_isolation_level` |
| CockroachDB | `xdist_cockroachdb_isolation_level` |
| Dolt | `xdist_dolt_isolation_level` |
| GizmoSQL | `xdist_gizmosql_isolation_level` |
| MariaDB | `xdist_mariadb_isolation_level` |
| MinIO | `xdist_minio_isolation_level` |
| MongoDB | `xdist_mongodb_isolation_level` |
| SQL Server | `xdist_mssql_isolation_level` |
| MySQL | `xdist_mysql_isolation_level` |
| PostgreSQL, pgvector, ParadeDB, AlloyDB Omni | `xdist_postgres_isolation_level` |
| Redis, Dragonfly, KeyDB | `xdist_redis_isolation_level` |
| RustFS | `xdist_rustfs_isolation_level` |
| Valkey | `xdist_valkey_isolation_level` |
| YugabyteDB | `xdist_yugabyte_isolation_level` |

Oracle and Spanner select worker-specific service/database names (`test_{worker_num}` or `test-db-{worker_num}`) internally. Elasticsearch does not expose an isolation fixture in 0.19.0 (though it assigns `database = worker_num or 0` on `ElasticsearchService`).

GizmoSQL and BigQuery always append `_{worker_num}` to their container names under xdist because their emulators do not provide multi-database logical isolation; overriding `xdist_gizmosql_isolation_level` or `xdist_bigquery_isolation_level` to `"server"` marks those worker containers transient (`transient=True`).

MinIO and RustFS suffix their default bucket names (`pytest-databases-{worker_num}`) and container names only when `xdist_minio_isolation_level` or `xdist_rustfs_isolation_level` is set to `"server"`.

## Override server isolation

```python
import pytest

from pytest_databases.types import XdistIsolationLevel


@pytest.fixture(scope="session")
def xdist_postgres_isolation_level() -> XdistIsolationLevel:
    return "server"
```

Keep the override session-scoped to match the package fixture.

## Worker helpers

```python
from pytest_databases.helpers import (
    get_xdist_worker_count,
    get_xdist_worker_id,
    get_xdist_worker_num,
)


def test_worker_identity() -> None:
    worker_id = get_xdist_worker_id()  # "gw0" under xdist; otherwise None
    worker_num = get_xdist_worker_num()  # 0 under gw0; otherwise None
    worker_count = get_xdist_worker_count()  # 1 without xdist
```

Use helpers only for test data or resources the package does not isolate
itself.
