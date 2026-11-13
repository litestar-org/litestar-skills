---
name: pytest-databases
description: "Use when working with pytest_databases (v0.20.0b3+), Docker/Podman or embedded DB fixtures, PostgreSQL/pgvector/ParadeDB/AlloyDB Omni 18, MySQL/MariaDB/Dolt/Doltgres, Oracle 26ai/ADB-Free/SQL Server/Db2/Sybase/SQL Anywhere/Teradata, CockroachDB/YugabyteDB, MongoDB, Redis/Dragonfly/KeyDB/Valkey, Elasticsearch, BigQuery/Spanner/PubSub, GizmoSQL/Hardcharger/Snowflake, MinIO/RustFS/Azure Blob, Redpanda/RabbitMQ, LocalStack, Floci, or Cloudflare Miniflare. Not for mocked DBs."
---

# pytest-databases

`pytest-databases` (`>=0.20.0b3` / `0.20.0-beta.3`) provides session-scoped,
100% clientless container and embedded database/broker/emulator service
fixtures across 32 plugin modules (31 `pytest_databases.docker.*` modules and
`pytest_databases.embedded.postgres`). Load only the plugin modules the test
suite uses and connect with the project's existing driver using the
`*_service` fixture's `host`, `port`, and credentials (`v0.19.0` `*_connection`
and `*_client` fixtures remain available as lazy-import `DeprecationWarning`
shims).

## Code Style Rules

- Prefer `*_service` fixtures and construct the project's native driver
  (`asyncpg`, `psycopg`, `sqlspec`, etc.) from the service coordinates. Every
  `pytest_databases.docker.*` and `pytest_databases.embedded.*` module in
  `v0.20.0b3` starts and probes readiness with zero third-party database client
  imports.
- Type service fixtures with the service class exported from the same plugin
  module (for example `PostgresService`, `RedisService`, `MinioService`).
- Keep `pytest_plugins` declarations in the root `conftest.py` or a dedicated
  fixture plugin module; do not load unused backends globally.
- When overriding a fixture defined inside a `pytest_databases.docker.<mod>`
  plugin, either register `"pytest_databases.docker.<mod>"` before the local
  fixture module in `conftest.py` or give the project wrapper fixture a
  distinct name (such as `custom_alloydb_omni_service`) so pytest's plugin
  load order never shadows the override.

## Quick Reference

### Install and enable

```bash
uv add --group test "pytest-databases>=0.20.0b3"
```

In `conftest.py`:

```python
pytest_plugins = ["pytest_databases.docker.postgres"]
```

The core `pytest_databases` entry point registers:

- `container_runtime` (`ContainerRuntimeConfig` resolved across Docker and Podman)
- `container_client` and `docker_client` (`DockerClient`)
- `container_service` and `docker_service` (`ContainerService` / `DockerService`)
- CLI options `--container-runtime={auto,docker,podman}`, `--keep-containers`,
  and `--postgres-backend={docker,embedded}`

### Choose the fixture shape

| Need | Use |
| --- | --- |
| Service coordinates for the project's own client (recommended) | The backend's `*_service` fixture (`postgres_service`, `alloydb_omni_service`, `redis_service`, etc.) |
| A specific PostgreSQL-family release | `postgres_11_service`–`postgres_18_service`, `pgvector_13_service`–`pgvector_18_service`, `paradedb_15_service`–`paradedb_18_service`, `alloydb_omni_15_service`–`alloydb_omni_18_service` |
| Switchable Docker vs embedded PostgreSQL | `postgres_any_service` (controlled by `--postgres-backend`, `postgres_backend` ini, or `PYTEST_DATABASES_POSTGRES_BACKEND`) |
| Host-process PostgreSQL without Docker/Podman | `pytest_databases.embedded.postgres` (`embedded_postgres_service`, `EmbeddedPostgresService`) |
| Parallel worker isolation (`database`, `server`, or PostgreSQL `template`) | The backend's `xdist_*_isolation_level` fixture from [xdist.md](references/xdist.md) |
| Custom AlloyDB Omni GUCs or `docker_service.run(...)` flags | Override `alloydb_omni_command` (e.g. `build_alloydb_omni_command(extra_gucs=...)`) or define a distinct session fixture calling `docker_service.run(...)` |

See [reference.md](references/reference.md) for the complete `v0.20.0b3`
module, service class, and fixture matrix.

<workflow>

## Workflow

1. Install `"pytest-databases>=0.20.0b3"` in the `test` dependency group (no
   driver extras are required for `*_service` fixtures).
2. Add only the required `pytest_databases.docker.<module>` (or
   `pytest_databases.embedded.postgres`) entries to `pytest_plugins`.
3. Consume the typed `*_service` fixture and pass its `host`, `port`, `user`,
   `password`, and `database` to the project's database config or client.
4. Override session-scoped configuration fixtures (`*_image`, `*_port`,
   `*_password`, `postgres_template_options`) in `conftest.py`; see
   [config.md](references/config.md).
5. For `pytest-xdist`, keep the default isolation level (usually `"database"`),
   use `"template"` on PostgreSQL/AlloyDB Omni when cloning a migrated template
   database across workers, or override to `"server"` when each worker requires
   an isolated container.

</workflow>

<guardrails>

## Guardrails

- **Clientless-first in `v0.20.0b3`**: All 32 plugin modules start and verify
  readiness using stdlib wire probes, HTTP checks, or in-container CLI tools.
  Legacy `v0.19.0` `*_connection` and `*_client` fixtures emit
  `DeprecationWarning` on use and lazy-import their driver inside the fixture.
- **AlloyDB Omni 18 defaults & custom GUCs**: `alloydb_omni_service`,
  `alloydb_omni_17_service`, and `alloydb_omni_18_service` automatically pass
  `alloydb_omni_command` (`build_alloydb_omni_command(include_textsearch=True)`),
  which preloads `pg_textsearch`, sets `shm_size="512m"`, and executes
  `ALLOYDB_OMNI_INIT_SQL` (`vector`, `alloydb_scann`, `google_ml_integration`,
  `alloydb_ai_nl`, `pg_textsearch`). AlloyDB Omni 15/16 use
  `alloydb_omni_legacy_command` without `pg_textsearch`. Override
  `alloydb_omni_command` (or `ALLOYDB_OMNI_COMMAND`) when adding custom GUCs.
- **Use exact `pytest_databases.docker.*` module names**: AlloyDB Omni,
  pgvector, and ParadeDB live in `pytest_databases.docker.postgres`; Dragonfly
  and KeyDB live in `pytest_databases.docker.redis`; Oracle 26ai (`oracle_26ai_service`,
  with `oracle_23ai_service` kept as a deprecated alias), 18c, and Autonomous
  Database (`oracle_adb_service`) live in `pytest_databases.docker.oracle`;
  Azurite lives in `pytest_databases.docker.azure_blob`; Elasticsearch 7/8/9
  lives in `pytest_databases.docker.elastic_search`; Floci AWS/GCP/Azure/OCI
  live in `pytest_databases.docker.floci`; Hardcharger lives in
  `pytest_databases.docker.hardcharger`; Teradata lives in
  `pytest_databases.docker.teradata`.
- **Avoid plugin load-order fixture shadowing**: When a helper module declares
  `pytest_plugins = ("pytest_databases.docker.postgres",)`, pytest loads the
  child plugin *after* the helper module. Name custom wrapper fixtures
  distinctly (for example `custom_alloydb_omni_service`) so the upstream
  `alloydb_omni_service` does not overwrite them.
- **Do not hand-roll container teardown**: `ContainerService` labels containers
  with a deterministic digest of `session.config.rootpath` (plus optional
  `PYTEST_DATABASES_NAMESPACE`) and sweeps stale containers from prior crashed
  runs automatically unless `--keep-containers` or
  `PYTEST_DATABASES_KEEP_CONTAINERS=1` is set.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Installed version is `pytest-databases>=0.20.0b3`.
- [ ] `pytest_plugins` names an existing module from
      [reference.md](references/reference.md).
- [ ] Service fixtures are typed with the matching `*Service` dataclass.
- [ ] Custom `docker_service.run(...)` wrappers use a distinct fixture name so
      child `pytest_plugins` do not shadow them.
- [ ] Configuration overrides and CLI flags match
      [config.md](references/config.md).
- [ ] Xdist overrides use the backend's exact isolation fixture name from
      [xdist.md](references/xdist.md).

</validation>

<example>

## Example: Customizing AlloyDB Omni 18 via `docker_service.run(...)`

```python  # pragma: prerelease-example
from collections.abc import Generator
import pytest
from pytest_databases import DockerService
from pytest_databases.docker.postgres import (
    PostgresService,
    build_alloydb_omni_command,
    create_worker_database,
    exec_psql,
)
from pytest_databases.helpers import get_xdist_worker_num, tcp_port_open
from pytest_databases.types import ServiceContainer

pytest_plugins = ("pytest_databases.docker.postgres",)

CUSTOM_ALLOYDB_COMMAND = build_alloydb_omni_command(
    extra_gucs={
        "google_columnar_engine.enabled": "off",
        "max_connections": "500",
    }
)


@pytest.fixture(scope="session")
def custom_alloydb_omni_service(
    docker_service: DockerService,
    alloydb_omni_image: str,
    postgres_host: str,
    postgres_user: str,
    postgres_password: str,
    alloydb_omni_port: int | None,
) -> Generator[PostgresService, None, None]:
    def check(service_container: ServiceContainer) -> bool:
        exit_code, output = exec_psql(
            service_container.container,
            user=postgres_user,
            password=postgres_password,
            database="postgres",
            sql="SELECT 1",
            tuples_only=True,
        )
        return (
            exit_code == 0 and output.strip() == b"1" and tcp_port_open(service_container.host, service_container.port)
        )

    worker_num = get_xdist_worker_num()
    db_name = f"pytest_databases_{worker_num}" if worker_num is not None else "pytest_databases"
    with docker_service.run(
        image=alloydb_omni_image,
        command=CUSTOM_ALLOYDB_COMMAND,
        check=check,
        container_host=postgres_host,
        container_port=5432,
        name="alloydb-omni",
        env={"POSTGRES_PASSWORD": postgres_password},
        shm_size="512m",
        timeout=90,
        pause=0.5,
        host_port=alloydb_omni_port,
    ) as service:
        create_worker_database(
            service.container,
            user=postgres_user,
            password=postgres_password,
            db_name=db_name,
        )
        yield PostgresService(
            host=service.host,
            port=service.port,
            container=service.container,
            database=db_name,
            user=postgres_user,
            password=postgres_password,
        )
```

</example>

---

## References Index

- [Supported database patterns](references/databases.md) — service-first,
  AlloyDB Omni 18, embedded Postgres, and cloud/broker emulator examples.
- [Complete fixture matrix](references/reference.md) — exact `v0.20.0b3`
  modules, service classes, service fixtures, and helper fixtures.
- [Xdist parallel testing](references/xdist.md) — `"database"`, `"server"`, and
  PostgreSQL `"template"` isolation levels.
- [Configuration](references/config.md) — CLI flags, environment variables,
  runtime resolution, and fixture overrides.
- [Troubleshooting](references/troubleshooting.md) — runtime, plugin load
  order, 4Kn storage, and port failures.
- [Litestar testing](../litestar-testing/SKILL.md) — integrate container-backed
  services with Litestar test clients and dependency overrides.

## Official References

- <https://pypi.org/project/pytest-databases/0.20.0b3/>
- <https://github.com/litestar-org/pytest-databases>
- <https://github.com/litestar-org/pytest-databases/tree/main/src/pytest_databases/docker>
- <https://github.com/litestar-org/pytest-databases/tree/main/src/pytest_databases/embedded>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Testing](../litestar-styleguide/references/testing.md)
- [Python](../litestar-styleguide/references/python.md)
