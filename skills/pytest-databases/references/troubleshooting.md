# Troubleshooting

## Fixture override is ignored (plugin load-order shadowing)

When a local helper module (such as `tests/database.py`) declares `pytest_plugins = ("pytest_databases.docker.postgres",)`, pytest loads the child plugin *after* `tests/database.py`. Defining a fixture in `tests/database.py` with the exact same name as an upstream fixture (for example `alloydb_omni_service`) allows the child plugin's fixture to overwrite the local definition.

Fix this in one of two ways:

1. Give the custom service fixture in `tests/database.py` a project-specific name (such as `custom_alloydb_omni_service`) and request it from `app_db`, or
2. Register `"pytest_databases.docker.postgres"` in the root `conftest.py` *before* `"tests.database"`.

## `pg_textsearch library not loaded` on AlloyDB Omni 18

`alloydb_omni_service`, `alloydb_omni_17_service`, and `alloydb_omni_18_service` in `v0.20.0b3` automatically pass `alloydb_omni_command` (`build_alloydb_omni_command(include_textsearch=True)`), which includes `pg_textsearch` in `shared_preload_libraries`. This error occurs only when using AlloyDB Omni 15/16 (`alloydb_omni_legacy_command`), overriding `alloydb_omni_command` / `ALLOYDB_OMNI_COMMAND` without `pg_textsearch`, or invoking `docker_service.run(...)` manually without `build_alloydb_omni_command()`:

```text
-c shared_preload_libraries=g_stats,google_columnar_engine,google_job_scheduler,google_ml_integration,google_storage,pg_stat_statements,pg_textsearch
```

## Container runtime resolution error

`v0.20.0b3` resolves container runtimes via `resolve_container_runtime()`:

1. Inspects `--container-runtime`, `PYTEST_DATABASES_CONTAINER_RUNTIME`, `CONTAINER_RUNTIME`, or `container_runtime` ini (`auto`, `docker`, `podman`).
2. Checks `PYTEST_DATABASES_CONTAINER_RUNTIME_ENDPOINT`, `DOCKER_HOST`, `CONTAINER_HOST`, active Docker context, `/var/run/docker.sock`, Podman connection JSON files (`~/.config/containers/podman-connections.json`, `~/.local/share/containers/podman/connections.json`), rootless Podman (`/run/user/<uid>/podman/podman.sock`), and rootful Podman (`/run/podman/podman.sock`).

Ensure the Docker or Podman socket is running and accessible in your execution environment.

## 4Kn filesystem / `overlayfs` Direct I/O errors (Oracle ADB-Free & Db2)

On hosts backed by 4096-byte logical sector storage (`dm-crypt` / `ext4` with `overlay2`), `v0.20.0b3` enables the required Direct I/O workarounds by default:

- `oracle_adb_filesystemio_options` defaults to `"NONE"` (rewriting `SPFILE` before startup so `ORA-27072` / `ORA-00202` does not occur).
- `db2_4k_device_support` defaults to `True` (`DB2_4K_DEVICE_SUPPORT=ON` and `DB2_DIRECT_IO=NO`).

## Azure Blob default container already exists

In `v0.20.0b3`, `azure_blob_service` pre-creates `azure_blob_default_container_name` (consistent with `minio_service`, `rustfs_service`, and `bigquery_service`). Calling `container_client.create_container()` on the default container will raise `ResourceExistsError`.
