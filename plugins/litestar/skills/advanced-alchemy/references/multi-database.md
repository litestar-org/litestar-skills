# Multi-Database Configuration

This reference describes how Advanced Alchemy supports applications that talk to more than one database in the same process — for example a primary OLTP store plus a read-only analytics warehouse, or a tenant database plus a shared identity database. The mechanism is the same across every framework integration: pass a list of configs to the extension class, give each one a `bind_key`, and look configs up by that key when you need a specific session. Per-framework injection wiring (how the right session ends up in a handler signature) is covered in the framework guides.

## The Bind-Key Model

Each `SQLAlchemyAsyncConfig` (or `SQLAlchemySyncConfig`) carries a `bind_key: str | None = None` field. When you pass a sequence of configs to the framework extension (the `AdvancedAlchemy` class, also re-exported as `SQLAlchemyPlugin` in some integrations), the extension stores them in a `dict[str, SQLAlchemyAsyncConfig | SQLAlchemySyncConfig]` keyed by `bind_key`. A config with `bind_key=None` is mapped under the literal string `"default"`.

The extension validates that every key is unique. From the upstream source:

```python
unique_bind_keys = {config.bind_key for config in self.config}

if len(unique_bind_keys) != len(self.config):
    msg = "Please ensure that each config has a unique name..."
    raise ImproperConfigurationError(msg)
```

This catches the common mistake of forgetting to set `bind_key` on the second config (both default to `None`, both map to `"default"`, the dict only retains one).

## Registering Multiple Configs

```python
from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
    EngineConfig,
)

primary = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@primary:5432/orders",
    commit_mode="autocommit",
    engine_config=EngineConfig(pool_size=20, max_overflow=10),
    # bind_key omitted -> stored under "default"
)

analytics = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://reader:reader@warehouse:5432/analytics",
    commit_mode="manual",  # read-only; no commits expected
    engine_config=EngineConfig(pool_size=5, max_overflow=2),
    bind_key="analytics",
)

extension = AdvancedAlchemy(config=[primary, analytics])
```

The `config=` parameter accepts either a single config or a `Sequence` of configs. The signature from the upstream source:

```python
def __init__(
    self,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig
        | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
    app: Starlette | None = None,
) -> None:
    ...
```

`extensions.fastapi`, `extensions.sanic`, and the other framework modules expose the same constructor shape — the `Starlette` annotation is just the most general ASGI type.

## Looking Up a Config by Key

The extension exposes `get_config(key)` and a pair of `provide_session(key)` / `provide_engine(key)` factories that return callables for the specified bind:

```python
# Address the analytics bind
analytics_config = extension.get_config("analytics")

# Construct a session-provider callable for that bind
get_analytics_session = extension.provide_session(key="analytics")

# Construct an engine-provider callable for that bind
get_analytics_engine = extension.provide_engine(key="analytics")
```

When `key=None` and only one config is registered, the extension falls back to that single config — convenient for tests and for incremental adoption (start with one, add a second later without rewriting call sites that already pass `None`).

The framework guides show how to wire these provider callables into per-framework dependency systems; the lookup primitive itself is the same everywhere.

## Async + Sync in the Same Application

Mixing config flavors is supported — the extension keeps `SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` in the same `_mapped_configs` dict. A common shape: async primary (asyncpg) plus sync analytics (psycopg) because the analytics queries run inside a threadpool.

```python
from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)

primary = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@primary:5432/orders",
    commit_mode="autocommit",
)

analytics = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://reader:reader@warehouse:5432/analytics",
    commit_mode="manual",
    bind_key="analytics",
)

extension = AdvancedAlchemy(config=[primary, analytics])
```

`extension.get_async_config(key)` and `extension.get_sync_config(key)` are type-narrowing variants of `get_config` for callers that need the static type to reflect the flavor.

## Pooling Considerations

Each config owns its own `EngineConfig` and therefore its own SQLAlchemy connection pool. Pools are not shared across binds — sizing each one is independent:

- The primary write database typically needs a larger pool sized to peak request concurrency.
- A read-only replica or analytics warehouse usually needs a smaller pool because queries are heavier and less frequent.
- Pool recycle (`pool_recycle`) should be set per-database to match the upstream `wal_sender_timeout` / `idle_in_transaction_session_timeout` of each instance.

```python
primary = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://...",
    engine_config=EngineConfig(
        pool_size=20,
        max_overflow=10,
        pool_recycle=300,
    ),
)

analytics = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://...",
    engine_config=EngineConfig(
        pool_size=5,
        max_overflow=2,
        pool_recycle=1800,  # warehouse keeps connections longer
    ),
    bind_key="analytics",
)
```

For read-replica routing within a single logical database (one primary, multiple read replicas of the same data), use [replicas.md](./replicas.md) instead — `RoutingConfig` is the right tool there, not `bind_key`.

## Sync Bridge

The sync flavor uses the same multi-config registry. Construct sync configs and pass them in the same list:

```python
from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    SQLAlchemySyncConfig,
)

primary = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://app:app@primary:5432/orders",
    commit_mode="autocommit",
)
posts = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://app:app@posts:5432/blog",
    commit_mode="autocommit",
    bind_key="posts",
)
extension = AdvancedAlchemy(config=[primary, posts])
```

## Metadata and Migrations

`bind_key` also drives Alembic's table-to-engine routing. When you declare a model, point its declarative base or its `__table_args__["info"]` at the same bind key so Alembic knows which engine to emit DDL against during migrations. See [migrations.md](./migrations.md) for the multi-bind Alembic configuration.

## Common Pitfalls

- **Forgetting to set `bind_key` on the second config.** Both configs default to `bind_key=None` -> both map to `"default"` -> the extension raises `ImproperConfigurationError` with the "unique name" message. Always set `bind_key` explicitly when you have more than one config.
- **No cross-bind transactions.** Sessions are per-config; `session.commit()` on the primary does not commit work on the analytics bind. If you need atomic cross-database semantics, you need explicit coordination (two-phase commit at the database level, an outbox table, or a saga pattern at the application layer).
- **Models bound to the wrong key.** A model declared against the primary `MetaData` cannot be queried through the analytics session — SQLAlchemy will look for the table on the wrong engine. Use a separate declarative base per bind, or set the `info={"bind_key": "..."}` on `__table_args__`.
- **Migrations run against the default bind only.** The `alchemy database upgrade` CLI iterates configured binds, but it's easy to forget to add a new bind to the Alembic config. Always update Alembic when you add a new `SQLAlchemyAsyncConfig`.
- **Pool exhaustion at the wrong bind.** If the analytics pool is sized at 5 and a long-running report blocks all of them, requests that need *any* analytics query queue up. Size analytics pools for the worst-case concurrent slow query, not the average.
- **Different `commit_mode` per bind is intentional.** A read-only analytics bind should use `commit_mode="manual"` (no writes -> no commits needed); a primary write bind typically uses `autocommit`. See [commit-modes.md](./commit-modes.md).

## Canonical References

- [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) — single-bind primary configuration; useful as the baseline before splitting binds.
- [litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia) — same baseline shape; per-bind pool tuning for the primary database.
