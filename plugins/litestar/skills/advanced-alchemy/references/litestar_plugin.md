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

## EngineConfig & Custom Engine Instance

```python
from advanced_alchemy.extensions.litestar import (
    AlembicAsyncConfig,
    AsyncSessionConfig,
    EngineConfig,
    SQLAlchemyAsyncConfig,
)
from litestar.serialization import decode_json, encode_json


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    before_send_handler="autocommit",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    engine_config=EngineConfig(
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=300,
        echo=False,
        json_serializer=encode_json,
        json_deserializer=decode_json,
    ),
    alembic_config=AlembicAsyncConfig(
        version_table_name="ddl_version",
        script_config="app/db/migrations/alembic.ini",
        script_location="app/db/migrations",
    ),
)
```

If you construct a custom `AsyncEngine` directly via `create_async_engine(...)` (for example, to attach SQLAlchemy `"connect"` event listeners), pass `engine_instance=engine` to `SQLAlchemyAsyncConfig`.

## SQLAlchemy DTOs

Automatic serialization/deserialization from SQLAlchemy models:

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig
from app.db import models as m


class UserReadDTO(SQLAlchemyDTO[m.User]):
    """DTO for serializing user responses without security-sensitive fields."""

    config = SQLAlchemyDTOConfig(
        exclude={"hashed_password", "totp_secret"},
    )


class UserCreateDTO(SQLAlchemyDTO[m.User]):
    """DTO for deserializing user creation payloads."""

    config = SQLAlchemyDTOConfig(
        include={"email", "name", "username"},
    )


class UserUpdateDTO(SQLAlchemyDTO[m.User]):
    """DTO for partial user updates where all fields are optional."""

    config = SQLAlchemyDTOConfig(
        include={"name", "username"},
        partial=True,
    )
```

### DTO with Renamed Fields

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig
from app.db import models as m


class UserReadCamelDTO(SQLAlchemyDTO[m.User]):
    """DTO with camelCase field naming."""

    config = SQLAlchemyDTOConfig(
        exclude={"hashed_password"},
        rename_fields={"team_id": "teamId"},
        rename_strategy="camel",
    )
```

## Dependency Injection & Provider Helpers

Prefer the built-in provider generators in `advanced_alchemy.extensions.litestar.providers` (`create_service_provider`, `create_service_dependencies`, `create_filter_dependencies`) over hand-writing `AsyncGenerator` boilerplate for every service.

### Reusable Service Providers (`create_service_provider`)

Configure default relationship loading (`load_only`, `selectinload`, `joinedload`), custom `error_messages`, and `execution_options` once per service provider:

```python
from advanced_alchemy.extensions.litestar.providers import create_service_provider
from sqlalchemy.orm import joinedload, load_only, selectinload
from app import config, services
from app.db import models as m

provide_users_service = create_service_provider(
    services.UserService,
    config=config.alchemy,
    load=[
        load_only(
            m.User.id,
            m.User.email,
            m.User.name,
            m.User.is_active,
            m.User.is_superuser,
        ),
        selectinload(m.User.roles).options(joinedload(m.UserRole.role, innerjoin=True)),
    ],
    error_messages={
        "duplicate_key": "This user already exists.",
        "integrity": "User operation failed.",
    },
    execution_options={"populate_existing": True},
)
```

### Controller Wiring (`create_service_dependencies` & `create_filter_dependencies`)

Use `create_service_dependencies()` to register both a service provider and query filter dependencies in one dictionary, or combine `Provide(provide_users_service)` with `create_filter_dependencies({...})`. Always annotate the injected `filters: list[FilterTypes]` parameter with `Dependency(skip_validation=True)`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from advanced_alchemy.extensions.litestar.providers import (
    create_filter_dependencies,
    create_service_dependencies,
)
from advanced_alchemy.filters import CollectionFilter
from advanced_alchemy.service import schema_dump
from litestar import Controller, delete, get, patch, post
from litestar.di import Provide
from litestar.params import Dependency, Parameter
from app import schemas as s
from app import services
from app.db import models as m

if TYPE_CHECKING:
    from advanced_alchemy.filters import FilterTypes
    from advanced_alchemy.service import OffsetPagination


def provide_role_id_filter(
    role_ids: Annotated[list[UUID] | None, Parameter(query="roleIds")] = None,
) -> CollectionFilter[UUID]:
    """Provide an additional CollectionFilter parsed from ?roleIds=... query params."""
    return CollectionFilter(field_name="role_id", values=role_ids or [])


class TagController(Controller):
    """Controller using create_service_dependencies for service + filter DI."""

    path = "/api/tags"
    dependencies = create_service_dependencies(
        services.TagService,
        key="tags_service",
        load=[m.Tag.projects],
        filters={
            "id_filter": UUID,
            "created_at": True,
            "updated_at": True,
            "sort_field": "name",
            "sort_order": "asc",
            "search": "name,slug,description",
            "search_ignore_case": True,
            "pagination_type": "limit_offset",
            "pagination_size": 20,
        },
    ) | {"role_id_filter": Provide(provide_role_id_filter, sync_to_thread=False)}

    @get(path="/")
    async def list_tags(
        self,
        tags_service: services.TagService,
        filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
    ) -> OffsetPagination[s.Tag]:
        results, total = await tags_service.get_many_and_count(*filters)
        return tags_service.to_schema(results, total, filters=filters, schema_type=s.Tag)

    @post(path="/")
    async def create_tag(
        self,
        tags_service: services.TagService,
        data: s.TagCreate,
    ) -> s.Tag:
        db_obj = await tags_service.create(data)
        return tags_service.to_schema(db_obj, schema_type=s.Tag)

    @patch(path="/{tag_id:uuid}")
    async def update_tag(
        self,
        tags_service: services.TagService,
        data: s.TagUpdate,
        tag_id: UUID,
    ) -> s.Tag:
        update_payload = schema_dump(data, exclude_unset=True)
        db_obj = await tags_service.update(update_payload, item_id=tag_id)
        return tags_service.to_schema(db_obj, schema_type=s.Tag)

    @delete(path="/{tag_id:uuid}")
    async def delete_tag(
        self,
        tags_service: services.TagService,
        tag_id: UUID,
    ) -> None:
        await tags_service.delete(tag_id)
```

When controller modules use `from __future__ import annotations` and place `FilterTypes` or `OffsetPagination` inside `if TYPE_CHECKING:`, register them in `signature_namespace` on `Litestar` or `AppConfig`:

```python
from advanced_alchemy import filters, repository, service
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination

app_config.signature_namespace.update(
    {
        "filters": filters,
        "repository": repository,
        "service": service,
        "FilterTypes": FilterTypes,
        "OffsetPagination": OffsetPagination,
    },
)
```

## Route Handlers with DTOs

```python
from litestar import get, post, patch


@get("/users", return_dto=UserReadDTO)
async def list_users(user_service: UserService) -> list[m.User]:
    return await user_service.get_many()


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
  - unset — closes the session without committing or rolling back
  - `"autocommit"` — commits 2xx responses and rolls back other statuses
  - `"autocommit_include_redirects"` — also commits 3xx responses
  - `async_autocommit_handler_maker(...)` — custom commit/rollback statuses

Do not close request sessions manually. Commit explicitly when using the
default close-only handler; let an autocommit handler own the transaction when
one is configured.

## Exception Handling & Status-Code Key Gotcha

By default (`set_default_exception_handler=True`), `SQLAlchemyInitPlugin` maps `RepositoryError` to `exception_to_http_response` (`NotFoundError` → `404 NotFoundException`, `DuplicateKeyError` / `IntegrityError` / `ForeignKeyError` → `409 ConflictError`, other `RepositoryError` subclasses → `500 InternalServerException`).

**Gotcha:** `SQLAlchemyInitPlugin.on_app_init` checks:

```python
if configure_exception_handler and not any(
    isinstance(exc, int) or issubclass(exc, RepositoryError) for exc in app_config.exception_handlers
):
    app_config.exception_handlers.update({RepositoryError: exception_to_http_response})
```

If `Litestar(exception_handlers={...})` contains **any integer status-code key** (such as `500`, `404`, or `HTTP_500_INTERNAL_SERVER_ERROR`), `isinstance(exc, int)` evaluates to `True` and `SQLAlchemyInitPlugin` **skips** registering `RepositoryError: exception_to_http_response`. Unhandled `NotFoundError` and `DuplicateKeyError` exceptions then surface as `500 Internal Server Error` instead of `404` / `409`.

Whenever your Litestar application registers integer status-code exception handlers, explicitly include `RepositoryError: exception_to_http_response`:

```python
from advanced_alchemy.exceptions import RepositoryError
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.exception_handler import exception_to_http_response
from litestar import Litestar
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR


app = Litestar(
    route_handlers=[...],
    plugins=[SQLAlchemyPlugin(config=db_config)],
    exception_handlers={
        HTTP_500_INTERNAL_SERVER_ERROR: custom_500_handler,
        RepositoryError: exception_to_http_response,
    },
)
```

## Dishka Integration

When a Litestar project uses Dishka (`dishka.integrations.litestar`) for dependency injection instead of Litestar's built-in `Provide`, keep `SQLAlchemyPlugin(config=db_config)` registered for engine/session lifecycle (`before_send_handler`), type encoders, and CLI commands, and resolve the plugin-managed request session inside a `Scope.REQUEST` Dishka `Provider` via `db_config.provide_session(request.app.state, request.scope)`:

```python
from dishka import Provider, Scope, from_context, make_async_container, provide
from dishka.integrations.litestar import FromDishka, inject, setup_dishka
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from litestar import Litestar, Request, get
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import UserService

db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    before_send_handler="autocommit",
)


class DatabaseProvider(Provider):
    """Dishka provider bridging Litestar's plugin-managed request session."""

    scope = Scope.REQUEST
    request = from_context(provides=Request, scope=Scope.REQUEST)

    @provide
    def provide_session(self, request: Request) -> AsyncSession:
        return db_config.provide_session(request.app.state, request.scope)

    @provide
    def provide_user_service(self, session: AsyncSession) -> UserService:
        return UserService(session=session)


@get("/users")
@inject
async def list_users(user_service: FromDishka[UserService]) -> list[dict[str, str]]:
    users = await user_service.get_many()
    return [{"id": str(u.id), "email": u.email} for u in users]


container = make_async_container(DatabaseProvider())
app = Litestar(
    route_handlers=[list_users],
    plugins=[SQLAlchemyPlugin(config=db_config)],
)
setup_dishka(container, app)
```

Using `db_config.provide_session(request.app.state, request.scope)` ensures Dishka services share the exact request-scoped `AsyncSession` inspected by `before_send_handler`.

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
