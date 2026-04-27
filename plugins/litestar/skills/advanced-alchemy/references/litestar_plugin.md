# Litestar Integration

## SQLAlchemy Plugin Configuration

```python
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    async_autocommit_before_send_handler,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from litestar import Litestar


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    before_send_handler=async_autocommit_before_send_handler,
)

app = Litestar(
    route_handlers=[...],
    plugins=[SQLAlchemyPlugin(config=db_config)],
)
```

## EngineConfig for Advanced Tuning

```python
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    EngineConfig,
)


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    engine_config=EngineConfig(
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=300,
        echo=False,
    ),
    before_send_handler=async_autocommit_before_send_handler,
)
```

## SQLAlchemy DTOs

Automatic serialization/deserialization from SQLAlchemy models:

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig
from app.db import models as m


class UserReadDTO(SQLAlchemyDTO[m.User]):
    config = SQLAlchemyDTOConfig(
        exclude={"hashed_password", "totp_secret"},
    )


class UserCreateDTO(SQLAlchemyDTO[m.User]):
    config = SQLAlchemyDTOConfig(
        include={"email", "name", "username"},
    )


class UserUpdateDTO(SQLAlchemyDTO[m.User]):
    config = SQLAlchemyDTOConfig(
        include={"name", "username"},
        partial=True,  # All fields become optional
    )
```

### DTO with Renamed Fields

```python
class UserReadDTO(SQLAlchemyDTO[m.User]):
    config = SQLAlchemyDTOConfig(
        exclude={"hashed_password"},
        rename_fields={"team_id": "teamId"},  # camelCase output
        rename_strategy="camel",  # or apply globally
    )
```

## Dependency Injection

### Providing Services via Dependencies

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from litestar.di import Provide


async def provide_user_service(
    db_session: AsyncSession,
) -> AsyncGenerator[UserService, None]:
    async with UserService.new(session=db_session) as service:
        yield service


app = Litestar(
    route_handlers=[...],
    plugins=[SQLAlchemyPlugin(config=db_config)],
    dependencies={"user_service": Provide(provide_user_service)},
)
```

### Using in Route Handlers

```python
from litestar import get, post, delete
from litestar.params import Parameter


@get("/users")
async def list_users(user_service: UserService) -> list[m.User]:
    return await user_service.list()


@get("/users/{user_id:uuid}")
async def get_user(
    user_service: UserService,
    user_id: UUID = Parameter(title="User ID"),
) -> m.User:
    return await user_service.get(user_id)


@post("/users")
async def create_user(
    user_service: UserService,
    data: dict,
) -> m.User:
    return await user_service.create(data)


@delete("/users/{user_id:uuid}")
async def delete_user(
    user_service: UserService,
    user_id: UUID,
) -> None:
    await user_service.delete(user_id)
```

## Route Handlers with DTOs

```python
from litestar import get, post, patch


@get("/users", return_dto=UserReadDTO)
async def list_users(user_service: UserService) -> list[m.User]:
    return await user_service.list()


@post("/users", dto=UserCreateDTO, return_dto=UserReadDTO)
async def create_user(user_service: UserService, data: m.User) -> m.User:
    return await user_service.create(data)


@patch("/users/{user_id:uuid}", dto=UserUpdateDTO, return_dto=UserReadDTO)
async def update_user(
    user_service: UserService,
    user_id: UUID,
    data: m.User,
) -> m.User:
    return await user_service.update(data, item_id=user_id)
```

## Session Management

The Litestar plugin automatically manages sessions:

- A new `AsyncSession` is created per request
- Sessions are injected as `db_session` dependency
- `before_send_handler` controls commit/rollback behavior:
  - `async_autocommit_before_send_handler` — auto-commits if no exception occurred
  - `async_autocommit_handler_maker(commit_on_redirect=False)` — customizable behavior

**Do not manually commit or close sessions** when using the plugin — it handles the lifecycle.

## Multiple Database Support

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin


primary_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/primary",
    before_send_handler=async_autocommit_before_send_handler,
)

analytics_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/analytics",
    before_send_handler=async_autocommit_before_send_handler,
    bind_key="analytics",
)

app = Litestar(
    plugins=[SQLAlchemyPlugin(config=[primary_config, analytics_config])],
)
```

Access the secondary session via `bind_key` in your service configuration.

## Session backend + session store

When you want Litestar server-side sessions persisted in your main database (instead of Redis or in-memory), Advanced Alchemy ships two integrations:

- `advanced_alchemy.extensions.litestar.session` — `SQLAlchemyAsyncSessionBackend` / `SQLAlchemySyncSessionBackend` plus the `SessionModelMixin` declarative mixin. This is the Litestar `ServerSideSessionBackend` implementation that stores raw session bytes, keyed by session ID.
- `advanced_alchemy.extensions.litestar.store` — `SQLAlchemyStore` (generic, supports both sync and async configs) plus `StoreModelMixin`. This is a generic `NamespacedStore` for Litestar's response-cache / rate-limit / arbitrary-value needs, keyed by `(key, namespace)`.

### When to use

Pick the session backend when you want `ServerSideSessionConfig` persistence colocated with your domain data — auditable, transactional, same backup strategy. Pick `SQLAlchemyStore` when you want a key/value store backed by SQLAlchemy for Litestar's `stores` registry (caching `@get` responses, rate-limit buckets, password-reset tokens).

### Config wiring

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.session import (
    SQLAlchemyAsyncSessionBackend,
    SessionModelMixin,
)
from litestar import Litestar
from litestar.middleware.session.server_side import ServerSideSessionConfig


class AppSession(SessionModelMixin):
    __tablename__ = "app_session"


db_config = SQLAlchemyAsyncConfig(connection_string="postgresql+asyncpg://localhost/app")

session_backend = SQLAlchemyAsyncSessionBackend(
    config=ServerSideSessionConfig(max_age=3600),
    alchemy_config=db_config,
    model=AppSession,
)

app = Litestar(
    route_handlers=[],
    plugins=[SQLAlchemyPlugin(config=db_config)],
    middleware=[session_backend.config.middleware],
)
```

### Table schema

`SessionModelMixin` extends `UUIDv7Base` (so you inherit `id: UUIDv7`) and declares:

- `session_id: Mapped[str]` — `String(255)`, unique constraint `uq_<table>_session_id` (Spanner uses a unique index `ix_<table>_session_id_unique` instead).
- `data: Mapped[bytes]` — `LargeBinary`.
- `expires_at: Mapped[datetime.datetime]` — indexed for expiry sweeps.
- `is_expired` hybrid property — comparable in both Python (`datetime.now(tz=utc) > expires_at`) and SQL (`func.now() > expires_at`).

`StoreModelMixin` is analogous with `key` + `namespace` instead of `session_id`, and `value` instead of `data`. Unique constraint is on `(key, namespace)`.

### Migration

Table creation is NOT automatic — both mixins are `__abstract__ = True`, and you must (a) subclass with a concrete `__tablename__` against a metadata registry that Alembic sees, and (b) generate a migration via `alembic revision --autogenerate`. The `UUIDv7Base` parent is already registered on the default metadata, so once the concrete subclass is imported at Alembic env time it will be picked up.

### Common pitfalls

- **Expiry GC is not scheduled.** Both backends expose `delete_expired()` but do not run it automatically. Wire a periodic task (SAQ cron job, Litestar `on_startup` background task) that calls `await backend.delete_expired()` on a schedule, or run it on `get()` access for your own session keys — `backend.get()` already deletes a row when it finds it expired.
- **Session ID generation is Litestar's concern.** The `SQLAlchemyAsyncSessionBackend` truncates inbound session IDs to 255 chars (`SESSION_ID_MAX_LENGTH`) but does not generate them — that is handled by `ServerSideSessionConfig`'s cookie middleware.
- **Upsert path varies by dialect.** On PostgreSQL / SQLite / MySQL / DuckDB / CockroachDB the backend uses `OnConflictUpsert.create_upsert`; on Oracle it uses `MergeStatement`; elsewhere it falls back to SELECT-then-INSERT/UPDATE. PostgreSQL 15+ MERGE is currently disabled upstream via `_DISABLE_POSTGRES_MERGE` due to locking concerns — expect `ON CONFLICT` for all Postgres versions.
