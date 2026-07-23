# Alembic Integration

## Metadata Registry

Advanced Alchemy uses `metadata_registry` for automatic model discovery by Alembic:

```python
from advanced_alchemy.base import metadata_registry

# Default-bind models use metadata_registry.get(). Import all model modules
# before migration autogeneration.
target_metadata = metadata_registry.get()
```

## Alembic env.py Configuration

Typical `env.py` setup with Advanced Alchemy:

```python
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from advanced_alchemy.base import metadata_registry

# Import all models so they register with metadata
from app.db import models  # noqa: F401

target_metadata = metadata_registry.get()


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async online mode."""
    config_section = context.config.get_section(context.config.config_ini_section, {})
    connectable = async_engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
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
