# SQLSpec Migrations

SQLSpec ships a native database migration runner that reuses the `SQLFileLoader`, the query builder, and the configured driver — no Alembic dependency. Migrations are plain SQL files (or Python files with `up()` / `down()` coroutines) keyed by **timestamp versions** (`YYYYMMDDHHmmss`) to avoid merge conflicts between branches. A single `ddl_migrations` tracking table records which versions ran, when, and for how long.

## Concept: sqlspec vs Alembic

Alembic targets SQLAlchemy metadata diffs and drives autogeneration off ORM models. SQLSpec's runner is adapter-agnostic and knows nothing about ORMs: each migration is raw SQL (or Python returning SQL strings) and the runner executes it through your configured driver. That means you get multi-dialect execution (PostgreSQL, Oracle, SQLite, DuckDB, BigQuery, Spanner, MySQL) from the same codebase, and you can ship extension-provided migrations alongside your own.

## CLI Surface

The canonical command group is `sqlspec` (wired up in `sqlspec/cli.py`). When Litestar is installed, the same command group is exposed as `litestar db <subcommand>` via `sqlspec.extensions.litestar.cli`.

| Command | Purpose |
| --- | --- |
| `sqlspec database init` | Scaffold the migrations directory + README |
| `sqlspec database create-migration -m "msg"` | Generate a timestamped migration file |
| `sqlspec database upgrade [revision]` | Apply pending migrations up to `head` or target |
| `sqlspec database downgrade [revision]` | Revert to a target revision |
| `sqlspec database show-current-revision` | Print the applied head version |
| `sqlspec database stamp <revision>` | Mark the DB at a revision without running SQL |
| `sqlspec database fix` | Convert legacy timestamp versions to sequential |
| `sqlspec database squash START:END -m "msg"` | Collapse a range of migrations into one |
| `sqlspec database show-config` | List all configs with migrations enabled |

```bash
# Create a new migration
sqlspec database create-migration -m "add users table"

# Apply everything
sqlspec database upgrade

# Apply up to a specific version
sqlspec database upgrade 20251011120000

# Preview without applying
sqlspec database upgrade --dry-run
```

The group also recognises `--bind-key <name>` (pick one config from a multi-config project), `--include` / `--exclude` (filter by bind key), `--no-auto-sync`, and `--use-logger` / `--summary` (structured logging instead of Rich console output). See `sqlspec/cli.py` for the full option matrix.

## Migration File Format

Two formats are supported. Both live under `migrations/` (configurable via `migration_config["script_location"]`).

### SQL format

```sql
-- name: migrate-20251011120000-up
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- name: migrate-20251011120000-down
DROP TABLE orders;
```

The runner uses `SQLFileLoader` to parse named queries in the file. Query names follow `migrate-{version}-up` / `migrate-{version}-down`, and the filename pattern is `{version}_{description}.sql` (e.g., `20251011120000_create_orders_table.sql`).

### Python format

```python
"""Create orders table migration."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlspec.migrations.context import MigrationContext

__all__ = ("down", "up")


async def up(context: "MigrationContext | None" = None) -> "list[str]":
    return [
        """
        CREATE TABLE orders (
            id BIGINT PRIMARY KEY,
            customer_id BIGINT NOT NULL,
            total NUMERIC(12, 2) NOT NULL,
            placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ]


async def down(context: "MigrationContext | None" = None) -> "list[str]":
    return ["DROP TABLE orders"]
```

Python migrations receive a `MigrationContext` that exposes `context.config` (the active SQLSpec config) and `context.extension_config` (the resolved extension blocks). This is how the shipped Litestar session migration picks a dialect-specific `CREATE TABLE` from the store class — see `sqlspec/extensions/litestar/migrations/0001_create_session_table.py`.

## Version Tracking

The runner stores applied versions in a tracking table (default name `ddl_migrations`, overridable via `migration_config["version_table_name"]`). `sqlspec.migrations.tracker.AsyncMigrationTracker` / `SyncMigrationTracker` own the schema and expose:

- `ensure_tracking_table(driver)` — create the table if missing; auto-migrate the schema if columns have been added upstream.
- `record_migration(driver, version, description, duration_ms, applied_by)` — insert a row when an upgrade succeeds.
- `get_current_version(driver)` — return the latest applied version (or `None`).
- `get_applied_migrations(driver)` — full list with timestamps, durations, and authors.

`sqlspec.migrations.version.MigrationVersion` models both version formats (`VersionType.SEQUENTIAL` for legacy `0001`-style, `VersionType.TIMESTAMP` for UTC timestamps) and orders mixed sets correctly so legacy migrations always sort before timestamp ones.

## Per-Adapter Migration Overlays

Some adapters ship dialect-specific migration helpers (e.g. Oracle needs different DDL for JSON columns depending on server version). `sqlspec/adapters/oracledb/migrations.py` is one such module — the runner automatically picks up adapter migration hooks when the config's module matches.

Extensions that bundle their own migrations are opt-in via `migration_config["include_extensions"]`. Shipped extensions with migrations:

- **`litestar`** — `sqlspec/extensions/litestar/migrations/` (one migration, `0001_create_session_table.py`, which delegates to the adapter's `litestar/store.py` for dialect-specific DDL).
- **`adk`** — creates the ADK session/event/memory/artifact tables. See [adk.md](adk.md).
- **`events`** — creates the table-queue fallback used by non-PostgreSQL adapters.

When `include_extensions` lists a name, `BaseMigrationCommands._discover_extension_migrations()` resolves the package path and includes its migration directory in the runner's search path.

## Litestar Plugin Integration

`SQLSpecPlugin` hooks the migration CLI into Litestar's own `litestar` command. After `include_extensions=["litestar"]`, the Litestar CLI exposes the full `db` group:

```python
from litestar import Litestar

from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.litestar import SQLSpecPlugin


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    migration_config={
        "script_location": "db/migrations",
        "version_table_name": "ddl_migrations",
        "include_extensions": ["litestar"],
    },
    extension_config={
        "litestar": {"commit_mode": "autocommit", "session_table": "litestar_session"},
    },
)

app = Litestar(route_handlers=[], plugins=[SQLSpecPlugin(config=config)])
```

```bash
# With the plugin installed, the CLI group appears under litestar
litestar db upgrade
litestar db create-migration -m "add order status enum"
litestar db show-current-revision
```

The CLI wiring is in `sqlspec/extensions/litestar/cli.py` (`database_group` is a `LitestarGroup` registered via `add_migration_commands`).

## Match Your Stack Callout

- If the project already uses **Alembic** through `advanced-alchemy` or bare SQLAlchemy, do **not** layer `sqlspec database upgrade` on top of it. Pick one runner per project. Mixing means two tracking tables (`alembic_version` and `ddl_migrations`), two sources of truth for "head", and no cross-runner locking.
- If you are new to the project, or you need heterogeneous adapters (e.g., PostgreSQL + DuckDB + Oracle) managed together, SQLSpec's runner is the simpler choice.
- Migrate from Alembic by stamping the SQLSpec tracking table at the Alembic head with `sqlspec database stamp <version>` and translating the Alembic revision graph into timestamped SQL files.

## Example: Full Configuration + Upgrade

```python
from pathlib import Path

from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"},
    migration_config={
        "script_location": Path("db/migrations"),
        "version_table_name": "ddl_migrations",
        "include_extensions": ["litestar"],
        "strict_ordering": True,
        "transactional": True,
    },
    extension_config={
        "litestar": {"commit_mode": "autocommit", "session_table": "litestar_session"},
    },
)
```

```bash
# Inside the project root
sqlspec database init db/migrations
sqlspec database create-migration -m "initial schema"
# (edit the generated file)
sqlspec database upgrade
sqlspec database show-current-revision
```

`strict_ordering=True` makes the runner refuse out-of-order migrations (useful when branches merge unevenly across environments); pair it with `--no-auto-sync` on the CLI to disable automatic reconciliation of renamed versions.

## Common Pitfalls

- **Split-brain with Alembic** — if any service in the repo still runs Alembic, a SQLSpec upgrade will silently add a second `ddl_migrations` table and leave Alembic's `alembic_version` untouched. Audit `migration_config` and `alembic.ini` before shipping.
- **Stale tracking table after manual edits** — if someone ran raw `DROP TABLE` against a migrated object, `show-current-revision` will still report the old head. Use `sqlspec database stamp <version>` to re-align after manual cleanup.
- **Timestamp vs sequential confusion** — legacy `0001`-style filenames are still supported and sort before timestamp versions. `sqlspec database fix` converts timestamp migrations to sequential format when you want a clean monotonic series for a release tag.
- **Extension migrations not discovered** — extensions are only scanned when listed in `include_extensions` (or when their `extension_config` key is present and not excluded). If the Litestar session table isn't being created, check that `migration_config["include_extensions"]` lists `"litestar"` **and** `extension_config["litestar"]` is set.
- **Transactional DDL on adapters that don't support it** — `transactional=True` is the default only for PostgreSQL, SQLite, and DuckDB. MySQL, Oracle, and BigQuery skip transaction wrapping (their DDL auto-commits anyway). Do not rely on rollback-on-failure there — always keep migrations idempotent.

## Public API Summary

Top-level exports in `sqlspec.migrations.__init__`:

- `AsyncMigrationCommands`, `SyncMigrationCommands`, `create_migration_commands`
- `AsyncMigrationRunner`, `SyncMigrationRunner`, `create_migration_runner`
- `AsyncMigrationTracker`, `SyncMigrationTracker`
- `SQLFileLoader`, `PythonFileLoader`, `BaseMigrationLoader`, `get_migration_loader`
- `MigrationSquasher`, `SquashPlan`
- `create_migration_file`, `drop_all`, `get_author`

Projects rarely touch these directly — the CLI in `sqlspec.cli` and the Litestar CLI integration are the normal entry points.

## Cross References

[litestar-sqlstack](https://github.com/cofin/litestar-sqlstack) is the canonical example of a Litestar + SQLSpec app that uses the native migration runner end-to-end (init, create, upgrade, downgrade, squash). Inspect its `migrations/` directory and its `migration_config` block for a reference setup.

- [adapters.md](adapters.md) — full adapter registry and parameter-style matrix.
- [extensions.md](extensions.md) — Litestar plugin and commit modes.
- [adk.md](adk.md) — ADK session / memory / artifact extensions and their migrations.
