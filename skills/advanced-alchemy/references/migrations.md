# Alembic Integration

## Metadata Registry

Advanced Alchemy uses `metadata_registry` for automatic model discovery by Alembic. Default-bind models use `metadata_registry.get()`. Import all model modules before migration autogeneration.

```python
from advanced_alchemy.base import metadata_registry

target_metadata = metadata_registry.get()
```

## Alembic env.py Configuration

When running migrations through `litestar database` or `alchemy`, `context.config` is an `AlembicCommandConfig` populated from `AlembicAsyncConfig` / `AlembicSyncConfig`. If your database also hosts tables managed by another subsystem (such as `litestar-saq` or `litestar-queues`), pass an `include_object` filter to `context.configure()` so autogenerate does not emit `DROP TABLE` statements for them:

```python
"""Alembic environment configuration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal, cast

from advanced_alchemy.base import metadata_registry
from alembic import context
from alembic.autogenerate import rewriter
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem
from app.db import models

if TYPE_CHECKING:
    from advanced_alchemy.alembic.commands import AlembicCommandConfig
    from sqlalchemy.engine import Connection

_ = models
config = cast("AlembicCommandConfig", context.config)
writer = rewriter.Rewriter()


def include_object(
    obj: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Exclude external worker queue tables from Alembic autogeneration."""
    return not (
        (name is not None and name.startswith("saq_"))
        or (type_ == "table" and name in {"task_queue", "task_queue_stats", "task_queue_ddl_version"})
    )


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=config.db_url,
        target_metadata=metadata_registry.get(config.bind_key),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=config.compare_type,
        version_table=config.version_table_name,
        version_table_pk=config.version_table_pk,
        user_module_prefix=config.user_module_prefix,
        render_as_batch=config.render_as_batch,
        process_revision_directives=writer,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations against an active connection."""
    context.configure(
        connection=connection,
        target_metadata=metadata_registry.get(config.bind_key),
        compare_type=config.compare_type,
        version_table=config.version_table_name,
        version_table_pk=config.version_table_pk,
        user_module_prefix=config.user_module_prefix,
        render_as_batch=config.render_as_batch,
        process_revision_directives=writer,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in async online mode."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = config.db_url
    connectable = cast(
        "AsyncEngine",
        config.engine
        or async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        ),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

## CLI Commands

### Advanced Alchemy Standalone CLI

```bash
# Generate migration
alchemy --config path.to.alchemy_config.config make-migrations -m "add user table"

# Apply all pending migrations
alchemy --config path.to.alchemy_config.config upgrade head

# Rollback one migration
alchemy --config path.to.alchemy_config.config downgrade -1
```

### Litestar Integration CLI

```bash
# Generate migration
litestar database make-migrations -m "add user table"

# Apply all pending migrations
litestar database upgrade

# Rollback last migration
litestar database downgrade

# Show current revision
litestar database show-current-revision
```

`litestar db ...` is also supported as a short alias in recent Litestar releases.

### Direct Alembic CLI

Use direct Alembic commands only when the application maintains a conventional
`alembic.ini` and `env.py` independently of Advanced Alchemy's config loader:

```bash
# Generate migration with message
alembic revision --autogenerate -m "add user table"

# Apply all migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history
```

## Multiple Database Support

Give each config a unique `bind_key`, metadata, and migration location:

```python
from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import AlembicAsyncConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig


primary_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/primary",
    bind_key="primary",
    metadata=metadata_registry.get("primary"),
    alembic_config=AlembicAsyncConfig(
        script_location="migrations/primary",
    ),
)

analytics_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/analytics",
    bind_key="analytics",
    metadata=metadata_registry.get("analytics"),
    alembic_config=AlembicAsyncConfig(
        script_location="migrations/analytics",
    ),
)
```

Target one configured database with `--bind-key`:

```bash
litestar database upgrade --bind-key analytics head
alchemy --config path.to.config upgrade --bind-key analytics head
```

The CLI does not infer a migration directory from `bind_key`; configure
`AlembicAsyncConfig(script_location=...)` explicitly.

## Migration Best Practices

- Always import all model modules in `env.py` before accessing `target_metadata`
- Use `--autogenerate` to detect schema changes, but review generated migrations before applying
- For production deployments, test migrations against a staging database first
- Use `litestar database stamp head` (or the standalone `alchemy` equivalent)
  to mark a fresh database as up-to-date without running migrations
- Keep migrations small and focused — one logical change per migration file

## Testing with Migrations

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from advanced_alchemy.base import orm_registry


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(orm_registry.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(orm_registry.metadata.drop_all)
    await engine.dispose()
```

For production-like test isolation, use `pytest-databases` with Docker-based database instances.
