# Troubleshooting

## Fixture not found

Confirm the exact plugin module is loaded:

```python
pytest_plugins = ["pytest_databases.docker.postgres"]
```

Then check the exhaustive matrix in [reference.md](reference.md). Do not infer
fixture names. In particular:

- Service-only plugins do not create a `*_connection` fixture.
- AlloyDB Omni, pgvector, and ParadeDB live in `pytest_databases.docker.postgres` (not `alloydb`); Azure/Azurite uses `pytest_databases.docker.azure_blob` and `azure_blob_*` (not `azurite`); Elasticsearch uses `pytest_databases.docker.elastic_search` (not `elasticsearch` or `ElasticSearch`); Dragonfly and KeyDB live in `pytest_databases.docker.redis`; SQLite has no 0.19.0 plugin.
- `elasticsearch_service` fails with `fixture 'elasticsearch8_service' not found` in 0.19.0; request `elasticsearch_8_service` or `elasticsearch_7_service` instead.
- `oracle_startup_connection` fails with `fixture 'oracle_23ai_startup_connection' not found` in 0.19.0; request `oracle_23ai_connection` or `oracle_18c_connection` instead.

## Client import fails

Install the backend extra when one exists. Even among service-only plugins:

- `pytest_databases.docker.redis` imports `redis` at module load time (`pip install "pytest-databases[redis]"`).
- `pytest_databases.docker.valkey` imports `valkey` at module load time (`pip install "pytest-databases[valkey]"`).
- `pytest_databases.docker.elastic_search` imports `elasticsearch7` at module load time for both v7 and v8 (`pip install "pytest-databases[elasticsearch7]"`).

Only these backends bundle and import no Python client dependency at all:

- MySQL
- MariaDB
- SQL Server
- YugabyteDB
- Dolt
- MinIO
- RustFS

For those backends, install and use the client already selected by the project.

## Container daemon is unavailable

Version 0.19.0 requires a Docker-compatible API. If `DOCKER_HOST` is set, the
Docker SDK uses it. Otherwise the package inspects the current Docker context;
when none is available, it falls back to the rootless Podman socket at
`unix:///run/user/<uid>/podman/podman.sock`.

Start the selected daemon and verify the current user can access its socket.

## Image or health check times out

Confirm the selected image supports the machine architecture and that the
container runtime can pull it. Override the backend-specific image fixture or
the shared `platform` fixture in `conftest.py`.

```python
import pytest


@pytest.fixture(scope="session")
def platform() -> str:
    return "linux/arm64"
```

The generic `platform` fixture is used by MySQL, Dolt, and BigQuery. When more
than one of those plugins is loaded, one override applies to all of them.

## Host port is already in use

Dynamic host ports are the default. Remove an unnecessary `*_port` override or
PostgreSQL-family port environment variable. If a fixed port is required,
assign a distinct port to each versioned service.

## Xdist workers interfere

Override the backend's exact isolation fixture to `"server"`. Consult
[xdist.md](xdist.md); Azure's fixture name differs from the common prefix, and
not every plugin exposes an isolation override.
