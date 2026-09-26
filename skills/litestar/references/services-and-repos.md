# Service Layer — Per-Stack Patterns

The service layer pattern in a Litestar app depends on your data-access stack. Pick the branch that matches your project and stay consistent — do not mix an `advanced-alchemy` repository service with a `sqlspec` driver call in the same Controller.

## Pick the branch for your stack

- **`advanced-alchemy`** → `SQLAlchemyAsyncRepositoryService` — opinionated ORM service with audit fields, filters, and pagination built in. Start here when you want a complete CRUD surface without writing `SELECT` statements.
- **`sqlspec`** → `SQLSpecAsyncService` (or `SQLSpecSyncService`) — first-party service base in `sqlspec.service` over explicit SQL or the `sql` builder. Start here for direct SQL control, 15+ driver adapters, cursor pagination, or Arrow / analytics integration. See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md).
- **raw SQLAlchemy** → `async_sessionmaker` + hand-rolled statements — start here only when you have an existing SQLAlchemy Core / ORM investment and explicitly do not want the repository abstraction.

## Branch A — `advanced-alchemy` repository service

`SQLAlchemyAsyncRepositoryService` is the opinionated default when `advanced-alchemy` is in the project. Subclassing provides a complete async CRUD surface, lifecycle hooks, automatic DTO conversion, filtering, and offset pagination.

```python
from __future__ import annotations

from typing import Any

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import ModelDictT, SQLAlchemyAsyncRepositoryService, is_dict

from app.db.models import UserModel


class UserRepository(SQLAlchemyAsyncRepository[UserModel]):
    """User database repository."""

    model_type = UserModel


class UserService(SQLAlchemyAsyncRepositoryService[UserModel]):
    """Handles database operations for users."""

    repository_type = UserRepository

    async def to_model_on_create(self, data: ModelDictT[UserModel]) -> ModelDictT[UserModel]:
        """Normalize incoming payload before insert."""
        data = await super().to_model_on_create(data)
        if is_dict(data) and "email" in data:
            data["email"] = str(data["email"]).lower().strip()
        return data

    async def authenticate(self, email: str, password: str) -> UserModel | None:
        """Verify credentials and return the user model when valid."""
        db_user = await self.get_one_or_none(email=email.lower().strip())
        if db_user is None or not db_user.verify_password(password):
            return None
        return db_user
```

### Methods you get for free

> [!WARNING]
> `list()` and `list_and_count()` are **deprecated** since `advanced-alchemy` 1.10.0 (scheduled for removal in 2.0.0). Always use `get_many()` and `get_many_and_count()`.

| Method | Signature / Return | Use case |
| --- | --- | --- |
| `get` | `get(item_id, *, id_attribute=..., statement=..., load=..., **kwargs) -> ModelT` | Fetch by primary key; raises `NotFoundError` if missing |
| `get_one` | `get_one(*filters, statement=..., load=..., **kwargs) -> ModelT` | Fetch single row by filter kwargs; raises `NotFoundError` if missing |
| `get_one_or_none` | `get_one_or_none(*filters, statement=..., load=..., **kwargs) -> ModelT \| None` | Fetch single row or `None` |
| `get_many` | `get_many(*filters, statement=..., load=..., order_by=..., **kwargs) -> Sequence[ModelT]` | Fetch rows matching filters without total count |
| `get_many_and_count` | `get_many_and_count(*filters, statement=..., count_with_window_function=..., **kwargs) -> tuple[Sequence[ModelT], int]` | Fetch `(rows, total)` — pair with `to_schema` for `OffsetPagination[T]` |
| `create` | `create(data, *, auto_commit=..., auto_expunge=..., auto_refresh=...) -> ModelT` | Insert single record from dict, model, `msgspec.Struct`, Pydantic model, or dataclass |
| `create_many` | `create_many(data, *, auto_commit=..., auto_expunge=...) -> Sequence[ModelT]` | Bulk insert multiple records |
| `update` | `update(data, item_id=None, *, attribute_names=..., id_attribute=..., with_for_update=...) -> ModelT` | Update single record by `item_id` (or ID embedded in `data`) |
| `update_many` | `update_many(data, *, auto_commit=..., auto_expunge=...) -> Sequence[ModelT]` | Bulk update multiple records |
| `upsert` | `upsert(data, item_id=None, *, match_fields=..., attribute_names=...) -> ModelT` | Insert or update matching `item_id` or `match_fields` |
| `upsert_many` | `upsert_many(data, *, match_fields=..., attribute_names=...) -> Sequence[ModelT]` | Bulk upsert |
| `get_or_upsert` | `get_or_upsert(*filters, match_fields=..., upsert=True, **kwargs) -> tuple[ModelT, bool]` | Return `(instance, created)` |
| `get_and_update` | `get_and_update(*filters, match_fields=..., **kwargs) -> tuple[ModelT, bool]` | Fetch matching row and apply updates, returning `(instance, updated)` |
| `delete` | `delete(item_id, *, id_attribute=..., load=...) -> ModelT` | Delete single row by primary key and return deleted instance |
| `delete_many` | `delete_many(item_ids, *, id_attribute=..., chunk_size=...) -> Sequence[ModelT]` | Bulk delete by primary keys |
| `delete_where` | `delete_where(*filters, sanity_check=True, **kwargs) -> Sequence[ModelT]` | Delete all rows matching filter expressions or column kwargs |
| `exists` | `exists(*filters, **kwargs) -> bool` | Cheap boolean existence check |
| `count` | `count(*filters, statement=..., **kwargs) -> int` | Row count with filters applied |
| `to_model` | `to_model(data, operation=None) -> ModelT` | Convert dict / DTO / Struct payload into ORM model instance |
| `to_schema` | `to_schema(data, total=None, filters=None, *, schema_type=...) -> ModelDTOT \| OffsetPagination[ModelDTOT]` | Convert single ORM row or sequence of rows into `msgspec.Struct`, Pydantic `BaseModel`, or `attrs` schema |

### Operation lifecycle hooks

Override lifecycle hooks on `SQLAlchemyAsyncRepositoryService` to transform or validate data before persistence without polluting route handlers:

- `to_model_on_create(self, data: ModelDictT[ModelT]) -> ModelDictT[ModelT]`
- `to_model_on_update(self, data: ModelDictT[ModelT]) -> ModelDictT[ModelT]`
- `to_model_on_delete(self, data: ModelDictT[ModelT]) -> ModelDictT[ModelT]`
- `to_model_on_upsert(self, data: ModelDictT[ModelT]) -> ModelDictT[ModelT]`
- `to_model(self, data: ModelDictT[ModelT], operation: str | None = None) -> ModelT`

Inspect payloads with `is_dict(data)`, `is_msgspec_struct(data)`, `is_pydantic_model(data)`, or `is_dto_data(data)` from `advanced_alchemy.service`.

### Standalone usage with `Service.new(...)`

Outside Litestar request DI (CLI commands, SAQ/queue tasks, pytest fixtures), instantiate the service via the `.new()` async context manager using either an active `session` or your `SQLAlchemyAsyncConfig`:

```python
from app.config import alchemy
from app.domain.accounts.services import UserService


async def seed_admin_user(email: str) -> None:
    """Create an admin user inside a standalone service context."""
    async with UserService.new(config=alchemy) as users_service:
        if not await users_service.exists(email=email):
            await users_service.create({"email": email, "is_superuser": True}, auto_commit=True)
```

### `to_schema` variants

```python
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination

from app.domain.accounts.schemas import User
from app.domain.accounts.services import UserService


async def get_user_dto(service: UserService, user_id: Any) -> User:
    """Convert a single ORM row into a DTO schema."""
    db_user = await service.get(user_id)
    return service.to_schema(db_user, schema_type=User)


async def list_users_dto(
    service: UserService,
    filters: list[FilterTypes],
) -> OffsetPagination[User]:
    """Convert a page of ORM rows and total count into OffsetPagination[User]."""
    results, total = await service.get_many_and_count(*filters)
    return service.to_schema(results, total, filters=filters, schema_type=User)
```

`to_schema` inspects `filters` via `find_filter(LimitOffset, filters=filters)` to populate `limit`, `offset`, and `total` on `OffsetPagination[T]`. Never hand-roll pagination envelopes.

### When to drop to hand-written queries inside an `advanced-alchemy` service

Repository services cover ~90% of the data-access surface. Drop to hand-written SQLAlchemy inside the service class when:

- You need a multi-table aggregate join that is awkward to express via repository filters.
- You are computing window functions, recursive CTEs, or `LATERAL` joins.
- You need vendor-specific SQL constructs (PostgreSQL `JSONB` operators, full-text ranking).
- A hot read path benefits from selecting only scalar columns via `self.repository.session`.

Always keep the query inside the service class — never leak `self.repository.session` into Controllers:

```python
from uuid import UUID

from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from sqlalchemy import select

from app.db.models import OrgMember, UserModel
from app.domain.accounts.repositories import UserRepository


class UserService(SQLAlchemyAsyncRepositoryService[UserModel]):
    """User service with custom query helper."""

    repository_type = UserRepository

    async def active_user_emails_by_org(self, org_id: UUID) -> list[str]:
        """Return active member emails for an organization."""
        stmt = (
            select(UserModel.email)
            .join(OrgMember)
            .where(
                OrgMember.org_id == org_id,
                UserModel.is_active.is_(True),
            )
        )
        result = await self.repository.session.execute(stmt)
        return list(result.scalars())
```

## Branch B — `sqlspec` async service

`SQLSpecAsyncService` (and its sync counterpart `SQLSpecSyncService`) is a **first-party class** shipped in `sqlspec.service` (and re-exported from `sqlspec.extensions.litestar`). Do not re-implement it in application code — subclass `SQLSpecAsyncService` directly or create a thin project base subclass when binding a default `config` or `SQLFileLoader`.

### Constructor and properties

```python
from sqlspec.service import SQLSpecAsyncService, SQLSpecSyncService
```

- `SQLSpecAsyncService(session: AsyncDriverAdapterBase | None = None, *, config: AsyncDatabaseConfig | NoPoolAsyncConfig | None = None, loader: SQLFileLoader | None = None)`
  - Exactly one of `session` (request-scoped driver injected by Litestar DI) or `config` (standalone mode for CLI/workers using `async with self.provide_session() as session:`) must be passed.
- Properties:
  - `self.session` / `self.driver` — the active `AsyncDriverAdapterBase` (raises `ImproperConfigurationError` if constructed with `config=` only; use `async with self.provide_session() as driver:` in that mode).
  - `self.config` — the configured database config (`None` when initialized with `session=`).
  - `self.loader` — optional `SQLFileLoader` for named SQL queries.

### Built-in `SQLSpecAsyncService` methods

| Method | Signature / Return | Use case |
| --- | --- | --- |
| `paginate` | `paginate(statement, /, *parameters, schema_type=None, count_with_window=False, session=None, **kwargs) -> OffsetPagination[SchemaT] \| CursorPagination[SchemaT]` | Inspects `*parameters` for `CursorFilter` vs `LimitOffsetFilter` and dispatches to cursor or limit-offset pagination |
| `paginate_limit_offset` | `paginate_limit_offset(statement, /, *parameters, schema_type=None, count_with_window=False, session=None, **kwargs) -> OffsetPagination[SchemaT]` | Executes `driver.select_with_total` and returns `OffsetPagination(items=..., limit=..., offset=..., total=...)` |
| `paginate_cursor` | `paginate_cursor(statement, /, *parameters, schema_type=None, session=None, **kwargs) -> CursorPagination[SchemaT]` | Keyset pagination using `CursorFilter` (`limit + 1` fetch + opaque HMAC-signed `next_cursor`) |
| `get_one` | `get_one(statement, /, *parameters, schema_type=None, error_message=None, session=None, **kwargs) -> SchemaT` | Fetches single row via `driver.select_one_or_none` and raises `sqlspec.exceptions.NotFoundError` when missing |
| `exists` | `exists(statement, /, *parameters, session=None, **kwargs) -> bool` | Returns `True` if at least one row matches (`LimitOffsetFilter(limit=1, offset=0)`) |
| `provide_session` | `provide_session(session=None) -> AbstractAsyncContextManager[AsyncDriverT]` | Yields an active driver session whether the service holds `session` or `config` |
| `begin_transaction` | `begin_transaction() -> _AsyncBeginTransactionContext` | Async context manager that commits on clean exit, rolls back on exception, and uses savepoints when nested |
| `begin` / `commit` / `rollback` | `await self.begin()`, `await self.commit()`, `await self.rollback()` | Manual transaction control on `self.session` |

### Driver methods available on `self.driver`

For direct writes and specialized reads, call `self.driver` (or `self.session`) inside service methods:

- `await self.driver.select(statement, *parameters, schema_type=...) -> list[SchemaT]`
- `await self.driver.select_one(statement, *parameters, schema_type=...) -> SchemaT`
- `await self.driver.select_one_or_none(statement, *parameters, schema_type=...) -> SchemaT | None`
- `await self.driver.select_value(statement, *parameters, value_type=...) -> T`
- `await self.driver.select_value_or_none(statement, *parameters, value_type=...) -> T | None`
- `await self.driver.select_with_total(statement, *parameters, schema_type=..., count_with_window=False) -> tuple[list[SchemaT], int]`
- `await self.driver.execute(statement, *parameters) -> SQLResult`
- `await self.driver.execute_many(statement, parameter_sets) -> SQLResult`

### Canonical `SQLSpecAsyncService` implementation

```python
from __future__ import annotations

from uuid import UUID

from sqlspec import sql
from sqlspec.core import CursorPagination, FilterTypes, OffsetPagination
from sqlspec.service import SQLSpecAsyncService

from app.domain.posts.schemas import Post, PostCreate, PostUpdate


class PostService(SQLSpecAsyncService):
    """Post domain service backed by SQLSpec."""

    async def list_posts(
        self,
        *filters: FilterTypes,
    ) -> OffsetPagination[Post] | CursorPagination[Post]:
        """List posts using limit-offset or cursor pagination depending on filters."""
        stmt = sql.select("id", "title", "body", "tenant_id", "created_at").from_("posts")
        return await self.paginate(stmt, *filters, schema_type=Post)

    async def get_post(self, post_id: UUID) -> Post:
        """Fetch a single post by ID or raise NotFoundError."""
        stmt = sql.select("id", "title", "body", "tenant_id", "created_at").from_("posts").where_eq("id", post_id)
        return await self.get_one(stmt, schema_type=Post, error_message=f"Post {post_id} not found")

    async def create_post(self, data: PostCreate) -> Post:
        """Insert a new post inside a transaction and return the hydrated schema."""
        stmt = (
            sql.insert("posts")
            .values(title=data.title, body=data.body, tenant_id=data.tenant_id)
            .returning("id", "title", "body", "tenant_id", "created_at")
        )
        async with self.begin_transaction():
            return await self.driver.select_one(stmt, schema_type=Post)

    async def update_post(self, post_id: UUID, data: PostUpdate) -> Post:
        """Update an existing post and return the updated row."""
        stmt = (
            sql.update("posts")
            .set(title=data.title, body=data.body)
            .where_eq("id", post_id)
            .returning("id", "title", "body", "tenant_id", "created_at")
        )
        async with self.begin_transaction():
            return await self.get_one(stmt, schema_type=Post, error_message=f"Post {post_id} not found")

    async def delete_post(self, post_id: UUID) -> None:
        """Delete a post by ID."""
        stmt = sql.delete("posts").where_eq("id", post_id)
        async with self.begin_transaction():
            await self.driver.execute(stmt)
```

### Config-Held `AsyncpgService(SQLSpecAsyncService[AsyncpgDriver])` pattern

In production applications that perform slow non-database work during a request (such as Argon2 password hashing, object-storage file uploads, external HTTP calls, or LLM/SSE streaming), holding an open database connection across the entire HTTP request lifecycle starves the connection pool under concurrency.

Instead of injecting a request-scoped driver session (`session=driver`), inject the `AsyncpgConfig` (`app_db`) and `SQLFileLoader` (`loader`) — both registered at `Scope.APP` in Dishka — into a `Scope.REQUEST` service subclass (`super().__init__(config=app_db, loader=loader)`). Each service operation acquires a pooled connection only for the millisecond duration of the SQL query or transaction via `async with self.provide_session() as session:` (or `async with self.begin_transaction() as session:`):

```python
from __future__ import annotations

from uuid import UUID

from dishka import Provider, Scope, provide
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
from sqlspec.loader import SQLFileLoader
from sqlspec.service import SQLSpecAsyncService

from app.domain.accounts.schemas import User, UserCreate
from app.lib.crypt import hash_password


class AsyncpgService(SQLSpecAsyncService[AsyncpgDriver]):
    """Base config-held SQLSpec service in app.lib.service."""

    def __init__(self, app_db: AsyncpgConfig, loader: SQLFileLoader) -> None:
        super().__init__(config=app_db, loader=loader)


class AccountService(AsyncpgService):
    """Account domain service in app.domain.accounts.services."""

    async def get_user(self, user_id: UUID) -> User:
        """Fetch a user using a short-lived pooled session."""
        assert self.loader is not None
        return await self.get_one(
            self.loader.get_sql("accounts-get-user"),
            user_id=user_id,
            schema_type=User,
            error_message=f"User {user_id} not found",
        )

    async def register_user(self, data: UserCreate) -> User:
        """Hash password outside the DB connection, then insert in a short-lived session."""
        assert self.loader is not None
        password_hash = await hash_password(data.password)
        async with self.provide_session() as session:
            return await session.select_one(
                self.loader.get_sql("accounts-insert-user"),
                email=data.email.lower().strip(),
                password_hash=password_hash,
                schema_type=User,
            )


class DatabaseProvider(Provider):
    """Dishka provider wiring Scope.APP config/loader and Scope.REQUEST services."""

    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def provide_loader(self) -> SQLFileLoader:
        """Load and cache SQL files once at application scope."""
        return SQLFileLoader()

    account_service = provide(AccountService)
```

Built-in helpers on `SQLSpecAsyncService` (`self.paginate`, `self.paginate_limit_offset`, `self.paginate_cursor`, `self.get_one`, `self.exists`, `self.begin_transaction`) automatically call `self.provide_session()` internally when initialized with `config=app_db`, while multi-statement operations use `async with self.provide_session() as session:` or `async with self.begin_transaction() as session:` explicitly.

Pick `sqlspec` when you want direct SQL or fluent `sql` query construction, target multiple database backends (15+ adapters including AsyncPG, Psycopg, DuckDB, SQLite/Aiosqlite, Oracle, BigQuery, Spanner), need built-in HMAC-signed cursor pagination, or stream Arrow results for analytics. See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) for DI provider factories and named SQL file loading.

## Branch C — raw SQLAlchemy with manual sessions

If the project predates `advanced-alchemy` (or intentionally avoids it), wrap `AsyncSession` in a thin service class. Resolve the session via `Provide()` or Dishka — never instantiate sessions inside a handler.

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post


class PostService:
    """Thin service over raw SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many_and_count(self, limit: int, offset: int) -> tuple[list[Post], int]:
        """Return a page of posts and total row count."""
        stmt = select(Post).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())
        total = await self._session.scalar(select(func.count()).select_from(Post))
        return rows, total or 0

    async def get_one_or_none(self, post_id: UUID) -> Post | None:
        """Return a single post by ID or None."""
        return await self._session.scalar(select(Post).where(Post.id == post_id))
```

No automatic `to_schema` is provided here — convert ORM models to DTOs explicitly at the service or handler boundary using `msgspec.convert(..., type=PostSchema, from_attributes=True)`.

## When to pick which

| Stack choice | Pick this when | Avoid this when |
| --- | --- | --- |
| `advanced-alchemy` service (`SQLAlchemyAsyncRepositoryService`) | You want an opinionated ORM service with audit fields, soft-delete, lifecycle hooks, filters, and offset pagination built in | The project is `sqlspec`-only or raw SQLAlchemy; you need multi-adapter support beyond SQLAlchemy dialects |
| `sqlspec` service (`SQLSpecAsyncService`) | You want explicit SQL or `sql` builder queries, 15+ driver adapters, built-in offset + cursor pagination, or Arrow streams | You want ORM unit-of-work identity maps, relationship lazy/eager loading, or model-driven Alembic autogenerate |
| raw SQLAlchemy with `async_sessionmaker` | You have an existing SQLAlchemy Core / ORM codebase and explicitly do not want `advanced-alchemy` | You are starting a new Litestar project — `advanced-alchemy` and `sqlspec` eliminate boilerplate |

## Cross-references

- Custom exceptions raised by `get` / `get_one`: [exceptions.md](exceptions.md)
- Filter dependencies and pagination (per-stack): [filters-and-pagination.md](filters-and-pagination.md)
- DTO conversion via `to_schema`: [dtos.md](dtos.md)
- Sibling skill for deeper `advanced-alchemy` patterns (audit bases, Alembic): [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md)
- Sibling skill for deeper `sqlspec` patterns (driver adapters, Arrow, query builder): [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md)
