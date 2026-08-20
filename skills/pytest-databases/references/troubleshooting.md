# Troubleshooting

## Fixture not found

Confirm the exact plugin module is loaded:

```python
pytest_plugins = ["pytest_databases.docker.postgres"]
```

Then check the exhaustive matrix in [reference.md](reference.md). Do not infer
fixture names. In particular, service-only plugins do not create a
`*_connection` fixture, Azure uses `azure_blob_*`, and SQLite has no 0.19.0
plugin.

## Client import fails

Install the backend extra when one exists. Some services intentionally bundle
no client dependency:

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
