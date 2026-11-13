# Supported Database Patterns

In `v0.20.0b3`, every provider is 100% clientless at startup and readiness check time. Consume the `*_service` fixture and construct the project's own database, cache, storage, or message broker client from its coordinates.

## Service-first pattern: PostgreSQL & AlloyDB Omni 18

```python
import asyncpg
from pytest_databases.docker.postgres import PostgresService

pytest_plugins = ["pytest_databases.docker.postgres"]


async def test_alloydb_omni_18(
    alloydb_omni_service: PostgresService,
) -> None:
    conn = await asyncpg.connect(
        host=alloydb_omni_service.host,
        port=alloydb_omni_service.port,
        user=alloydb_omni_service.user,
        password=alloydb_omni_service.password,
        database=alloydb_omni_service.database,
    )
    try:
        assert await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()
```

`pytest_databases.docker.postgres` provides:

- PostgreSQL 11–18 (`postgres_service`, `postgres_11_service`–`postgres_18_service`, default `postgres:18`)
- pgvector 13–18 (`pgvector_service`, `pgvector_13_service`–`pgvector_18_service`, default `pgvector/pgvector:pg18`)
- ParadeDB 15–18 (`paradedb_service`, `paradedb_15_service`–`paradedb_18_service`, default `paradedb/paradedb:latest-pg18`)
- AlloyDB Omni 15–18 (`alloydb_omni_service`, `alloydb_omni_15_service`–`alloydb_omni_18_service`, default `gcr.io/alloydb-omni/alloydbomni:18`)

### Preloading `pg_textsearch` and customizing GUCs on AlloyDB Omni 18

`alloydb_omni_service`, `alloydb_omni_17_service`, and `alloydb_omni_18_service` automatically launch with `alloydb_omni_command` (`build_alloydb_omni_command(include_textsearch=True)`), `shm_size="512m"`, and `ALLOYDB_OMNI_INIT_SQL`, which preloads `pg_textsearch` and initializes `vector`, `alloydb_scann`, `google_ml_integration`, `alloydb_ai_nl`, and `pg_textsearch`. (`alloydb_omni_15_service` and `alloydb_omni_16_service` use `alloydb_omni_legacy_command`, which omits `pg_textsearch`.) To add or override postmaster GUCs, override `alloydb_omni_command` (or set `ALLOYDB_OMNI_COMMAND`):

```python  # pragma: prerelease-example
import pytest
from pytest_databases.docker.postgres import build_alloydb_omni_command


@pytest.fixture(scope="session")
def alloydb_omni_command() -> list[str]:
    return build_alloydb_omni_command(
        extra_gucs={
            "google_columnar_engine.enabled": "off",
            "max_connections": "500",
        }
    )
```

## Embedded PostgreSQL (no container daemon required)

`pytest_databases.embedded.postgres` runs a local PostgreSQL cluster using `pgembed` (Python `>=3.12`) or `pgserver` (`<3.12`) or a host `PG_BIN_DIR` over a stdlib wire-protocol client:

```python  # pragma: prerelease-example
from pytest_databases.embedded.postgres import EmbeddedPostgresService

pytest_plugins = ["pytest_databases.embedded.postgres"]


def test_embedded_postgres(
    embedded_postgres_service: EmbeddedPostgresService,
) -> None:
    assert embedded_postgres_service.port > 0
    assert embedded_postgres_service.database
```

## S3-compatible object storage: MinIO & RustFS

`MinioService` (Chainguard `cgr.dev/chainguard/minio:latest`) and `RustfsService` (`rustfs/rustfs:latest`) pre-create their default bucket via stdlib AWS SigV4 HTTP calls without sidecar containers and expose `.endpoint_url` and `.ensure_bucket(name)`.

## Cloud, analytics, & broker emulators in 0.20.0b3

- **Oracle Autonomous Database Free (`oracle_adb_service`)**: Extracts mTLS wallets to `oracle_adb_wallet_dir` and applies `oracle_adb_filesystemio_options="NONE"` by default so 4Kn/overlayfs hosts work out of the box.
- **IBM Db2 (`db2_service`)**: Applies `db2_4k_device_support=True` (`DB2_4K_DEVICE_SUPPORT=ON` / `DB2_DIRECT_IO=NO`) by default.
- **Sybase ASE (`sybase_service`) & SAP SQL Anywhere (`sqlanywhere_service`)**: Clientless TDS/SQL Anywhere containers (`sqlanywhere_service` defaults to `"server"` xdist isolation).
- **Teradata Vantage (`teradata_service`, `teradata_external_service`)**: BYO container (`TERADATA_IMAGE`) or external endpoint (`TERADATA_EXTERNAL_HOST`) with clientless TCP readiness and `connection_config`.
- **Doltgres (`doltgres_service`)**: PostgreSQL-wire Dolt (`dolthub/doltgresql:latest`).
- **Hardcharger (`hardcharger_service`)**: DuckDB Chargewire HTTP/Arrow analytics server (`ghcr.io/gizmodata/hardcharger:latest`).
- **Snowflake (`snowflake_service`)**: Embucket Snowflake REST v1 emulator (`embucket/embucket:0.2.2`).
- **Floci (`floci_aws_service`, `floci_gcp_service`, `floci_az_service`, `floci_oci_service`)**: Lightweight GraalVM native multi-cloud emulators (`4566` gateway; GCP compat proxy optional).
- **LocalStack / MiniStack (`localstack_service`)**: Tokenless `ministackorg/ministack:latest` default (LocalStack opt-in via `LOCALSTACK_IMAGE` + optional `LOCALSTACK_AUTH_TOKEN`).
- **Cloudflare (`cloudflare_service`)**: Miniflare 5 local explorer + R2 S3 SigV4 endpoint for KV, R2, and D1.
- **Redpanda (`redpanda_service`), RabbitMQ (`rabbitmq_service`), Pub/Sub (`pubsub_service`)**: Clientless message broker fixtures with dynamic host port discovery.
