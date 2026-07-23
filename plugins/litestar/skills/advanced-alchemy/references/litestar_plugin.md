# Litestar Integration

## SQLAlchemy Plugin Configuration

```python
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from litestar import Litestar


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    before_send_handler="autocommit",
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
    before_send_handler="autocommit",
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
from litestar.di import NamedDependency, Provide


async def provide_user_service(
    db_session: NamedDependency[AsyncSession],
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
from litestar.di import NamedDependency
from litestar.params import FromPath


@get("/users")
async def list_users(user_service: NamedDependency[UserService]) -> list[m.User]:
    return await user_service.get_many()


@get("/users/{user_id:uuid}")
async def get_user(
    user_service: NamedDependency[UserService],
    user_id: FromPath[UUID],
) -> m.User:
    return await user_service.get(user_id)


@post("/users")
async def create_user(
    user_service: NamedDependency[UserService],
    data: dict,
) -> m.User:
    return await user_service.create(data)


@delete("/users/{user_id:uuid}")
async def delete_user(
    user_service: NamedDependency[UserService],
    user_id: UUID,
) -> None:
    await user_service.delete(user_id)
```

## Route Handlers with DTOs

```python
from litestar import get, post, patch


@get("/users", return_dto=UserReadDTO)
async def list_users(user_service: NamedDependency[UserService]) -> list[m.User]:
    return await user_service.get_many()


@post("/users", dto=UserCreateDTO, return_dto=UserReadDTO)
async def create_user(user_service: NamedDependency[UserService], data: m.User) -> m.User:
    return await user_service.create(data)


@patch("/users/{user_id:uuid}", dto=UserUpdateDTO, return_dto=UserReadDTO)
async def update_user(
    user_service: NamedDependency[UserService],
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
  - unset — closes the session without committing or rolling back
  - `"autocommit"` — commits 2xx responses and rolls back other statuses
  - `"autocommit_include_redirects"` — also commits 3xx responses
  - `async_autocommit_handler_maker(...)` — custom commit/rollback statuses

Do not close request sessions manually. Commit explicitly when using the
default close-only handler; let an autocommit handler own the transaction when
one is configured.

## Multiple Database Support

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin


primary_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/primary",
    before_send_handler="autocommit",
    bind_key="primary",
    session_dependency_key="primary_session",
    engine_dependency_key="primary_engine",
)

analytics_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/analytics",
    before_send_handler="autocommit",
    bind_key="analytics",
    session_dependency_key="analytics_session",
    engine_dependency_key="analytics_engine",
)

app = Litestar(
    plugins=[SQLAlchemyPlugin(config=[primary_config, analytics_config])],
)
```

Access each session through its configured Litestar dependency key. `bind_key`
selects metadata and CLI configuration; it does not inject the session into a
service automatically.

## Session backend + session store

When you want Litestar server-side sessions persisted in your main database (instead of Redis or in-memory), Advanced Alchemy ships two integrations:

- `advanced_alchemy.extensions.litestar.session` — `SQLAlchemyAsyncSessionBackend` / `SQLAlchemySyncSessionBackend` plus the `SessionModelMixin` declarative mixin. This is the Litestar `ServerSideSessionBackend` implementation that stores raw session bytes, keyed by session ID.
- `advanced_alchemy.extensions.litestar.store` — `SQLAlchemyStore` (generic,
  supports both sync and async configs) plus `StoreModelMixin`. Register it
  under the `"sessions"` store name for Litestar's preferred store-based
  server-side sessions, or use it as a general `NamespacedStore`.

### When to use

Prefer `SQLAlchemyStore` registered as `stores={"sessions": session_store}`
when the application already uses Litestar's store-backed session
configuration. Use `SQLAlchemyAsyncSessionBackend` or
`SQLAlchemySyncSessionBackend` only when you need to wire a dedicated backend
directly into `SessionMiddleware`.

### Config wiring

```python
from functools import partial

from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.session import (
    SQLAlchemyAsyncSessionBackend,
    SessionModelMixin,
)
from litestar import Litestar
from litestar.middleware.session import SessionMiddleware
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
    middleware=[partial(SessionMiddleware, backend=session_backend)],
)
```

Do not use `session_backend.config.middleware` for a custom SQLAlchemy
backend. `ServerSideSessionConfig.middleware` installs Litestar's configured
built-in backend and ignores this backend instance.

### Table schema

`SessionModelMixin` extends `UUIDv7Base` (so you inherit `id: UUIDv7`) and declares:

- `session_id: Mapped[str]` — `String(255)`, unique constraint `uq_<table>_session_id` (Spanner uses a unique index `ix_<table>_session_id_unique` instead).
- `data: Mapped[bytes]` — `LargeBinary`.
- `expires_at: Mapped[datetime.datetime]` — indexed for expiry sweeps.
- `is_expired` hybrid property — comparable in both Python (`datetime.now(tz=utc) > expires_at`) and SQL (`func.now() > expires_at`).

`StoreModelMixin` is analogous with `key` + `namespace` instead of `session_id`, and `value` instead of `data`. Unique constraint is on `(key, namespace)`.

### Migration

Table creation is NOT automatic — both mixins are `__abstract__ = True`, and
you must (a) subclass with a concrete `__tablename__` against metadata that the
config sees, and (b) run `litestar database make-migrations`. Import the
concrete model before migration autogeneration.

### Common pitfalls

- **Expiry GC is not scheduled.** Both backends expose `delete_expired()` but do not run it automatically. Wire a periodic task (SAQ cron job, Litestar `on_startup` background task) that calls `await backend.delete_expired()` on a schedule, or run it on `get()` access for your own session keys — `backend.get()` already deletes a row when it finds it expired.
- **Session ID generation is Litestar's concern.** The `SQLAlchemyAsyncSessionBackend` truncates inbound session IDs to 255 chars (`SESSION_ID_MAX_LENGTH`) but does not generate them — that is handled by `ServerSideSessionConfig`'s cookie middleware.
- **Upsert path varies by dialect.** On PostgreSQL / SQLite / MySQL / DuckDB / CockroachDB the backend uses `OnConflictUpsert.create_upsert`; on Oracle it uses `MergeStatement`; elsewhere it falls back to SELECT-then-INSERT/UPDATE. PostgreSQL 15+ MERGE is currently disabled upstream via `_DISABLE_POSTGRES_MERGE` due to locking concerns — expect `ON CONFLICT` for all Postgres versions.
