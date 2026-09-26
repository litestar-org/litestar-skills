# Service Layer Patterns

## Service Types

| Service | Use Case |
| --- | --- |
| `SQLAlchemyAsyncRepositoryService` / `SQLAlchemySyncRepositoryService` | Full CRUD service with lifecycle hooks |
| `SQLAlchemyAsyncRepositoryReadService` / `SQLAlchemySyncRepositoryReadService` | Read-only variant (`get_many`, `get`, `count`, `exists`) |
| `SQLAlchemyAsyncQueryService` / `SQLAlchemySyncQueryService` | Read-only service wrapper around arbitrary SQL queries |

```python
from advanced_alchemy.service import (
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncQueryService,
    SQLAlchemySyncRepositoryReadService,
    SQLAlchemySyncRepositoryService,
)
```

## Basic Service

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from app.db import models as m


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    """Service for user operations."""

    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    match_fields = ["email"]
```

## Lifecycle Hooks

Transform data before persistence (`to_model_on_create`, `to_model_on_update`, `to_model_on_upsert`, `to_model_on_delete`). These are the primary extension points:

```python
from advanced_alchemy.service import ModelDictT


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    match_fields = ["email"]

    async def to_model_on_create(self, data: ModelDictT[m.User]) -> ModelDictT[m.User]:
        """Normalize or hash fields before creation."""
        if isinstance(data, dict) and "password" in data:
            data["hashed_password"] = await hash_password(data.pop("password"))
        return data

    async def to_model_on_update(self, data: ModelDictT[m.User]) -> ModelDictT[m.User]:
        """Normalize or hash fields before updating."""
        if isinstance(data, dict) and "password" in data:
            data["hashed_password"] = await hash_password(data.pop("password"))
        return data

    async def to_model_on_upsert(self, data: ModelDictT[m.User]) -> ModelDictT[m.User]:
        """Normalize or hash fields before upserting."""
        return await self.to_model_on_create(data)
```

## Helper Utilities

```python
from advanced_alchemy.service import (
    SchemaDumpConfig,
    is_dict_with_field,
    is_dict_without_field,
    schema_dump,
)

data = schema_dump(create_schema)
data = schema_dump(create_schema, config=SchemaDumpConfig(exclude_none=True))

if is_dict_with_field(data, "password"):
    data["hashed_password"] = hash_password(data.pop("password"))

if is_dict_without_field(data, "slug"):
    data["slug"] = slugify(data["title"])
```

Set `schema_dump_config` on a service class to change the default conversion behavior for schema-like inputs. Pass `schema_dump_config=` to `create()`, `create_many()`, `update()`, `update_many()`, `upsert()`, `upsert_many()`, `get_or_upsert()`, or `get_and_update()` for a single operation.

```python
from advanced_alchemy.service import SchemaDumpConfig


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    schema_dump_config = SchemaDumpConfig(exclude_unset=True, exclude_none=True)


user = await service.update(
    data=patch_schema,
    item_id=user_id,
    schema_dump_config=SchemaDumpConfig(exclude_none=True, exclude_defaults=True),
)
```

## Common Service Operations

Use `get_many()` and `get_many_and_count()`. The older `list()` and
`list_and_count()` methods remain as deprecation wrappers only until 2.0. The
same rename applies to repositories, query repositories, memory repositories,
and cache-manager list helpers.

```python
from advanced_alchemy.filters import LimitOffset

user = await service.create({"email": "test@example.com", "name": "Test"})

user = await service.get(user_id)
user = await service.get_one_or_none(id=user_id)
user = await service.get_one_or_none(email="test@example.com")

users = await service.get_many()
users, count = await service.get_many_and_count(LimitOffset(limit=20, offset=0))

user = await service.update({"name": "New Name"}, item_id=user_id)
user = await service.upsert({"email": "test@example.com", "name": "Test"})

await service.delete(user_id)
await service.delete_many([user_id, user_model])

exists = await service.exists(email="test@example.com")
count = await service.count()
```

## Filtering

```python
from advanced_alchemy.filters import (
    CollectionFilter,
    LimitOffset,
    OrderBy,
    SearchFilter,
)

users, count = await service.get_many_and_count(
    LimitOffset(limit=20, offset=0),
    OrderBy(field_name="created_at", sort_order="desc"),
    SearchFilter(field_name="name", value="John", ignore_case=True),
)

users = await service.get_many(
    CollectionFilter(field_name="id", values=[id1, id2, id3]),
)
```

### Custom Filtered Methods

```python
from advanced_alchemy.filters import BooleanFilter, FilterTypes
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from app.db import models as m


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    """User service with custom filtered queries."""

    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo

    async def list_active_users(self, *filters: FilterTypes) -> list[m.User]:
        """Fetch active users matching additional criteria."""
        custom_filters: list[FilterTypes] = [
            BooleanFilter(field_name="is_active", value=True),
        ]
        custom_filters.extend(filters)
        return await self.get_many(*custom_filters)
```

## Pagination Pattern

```python
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.service.pagination import OffsetPagination


@get("/users")
async def list_users(
    service: UserService,
    limit: int = 20,
    offset: int = 0,
) -> OffsetPagination[UserSchema]:
    filters = [LimitOffset(limit=limit, offset=offset)]
    results, total = await service.get_many_and_count(*filters)
    return service.to_schema(results, total, filters=filters, schema_type=UserSchema)
```

## Loader Options for Eager Loading

Override default lazy loading for specific queries:

```python
from sqlalchemy.orm import selectinload, undefer_group

user = await service.get(
    user_id,
    load=[selectinload(m.User.roles)],
)

user = await service.get(
    user_id,
    load=[undefer_group("security_sensitive")],
)
```

## Row Locking

For critical sections requiring pessimistic locking (`SELECT ... FOR UPDATE`), pass `with_for_update=True` (or a `ForUpdateArg` / `dict` of flags) to `service.get_one()`, `service.get_one_or_none()`, `service.update()`, `service.upsert()`, `service.get_or_upsert()`, `service.get_and_update()`, or `service.repository.get()`:

```python
user = await service.get_one(id=user_id, with_for_update=True)
user.balance -= amount
await service.update(user)
```

## Explicit Session Access

When you need direct SQLAlchemy session operations:

```python
from uuid import UUID
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from app.db import models as m


class PaymentService(SQLAlchemyAsyncRepositoryService[m.Payment]):
    """Payment service with explicit session flush."""

    class Repo(SQLAlchemyAsyncRepository[m.Payment]):
        model_type = m.Payment

    repository_type = Repo

    async def process_payment(self, payment_id: UUID) -> m.Payment:
        """Process payment and flush state without immediate commit."""
        payment = await self.repository.get(payment_id, with_for_update=True)
        payment.status = "processed"
        await self.repository.session.flush()
        return payment
```

## Composite Service Pattern

For operations spanning multiple models, use lazy-loaded related services that share the same session:

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from app.db import models as m


class OrderService(SQLAlchemyAsyncRepositoryService[m.Order]):
    """Order service composing item and payment services."""

    class Repo(SQLAlchemyAsyncRepository[m.Order]):
        model_type = m.Order

    repository_type = Repo

    @property
    def item_service(self) -> OrderItemService:
        """Lazy-loaded service sharing the same session."""
        if not hasattr(self, "_item_service"):
            self._item_service = OrderItemService(session=self.repository.session)
        return self._item_service

    @property
    def payment_service(self) -> PaymentService:
        """Lazy-loaded payment service sharing the same session."""
        if not hasattr(self, "_payment_service"):
            self._payment_service = PaymentService(session=self.repository.session)
        return self._payment_service

    async def create_order_with_items(
        self,
        order_data: dict,
        items: list[dict],
    ) -> m.Order:
        """Create order and child items atomically."""
        order = await self.create(order_data)
        for item in items:
            item["order_id"] = order.id
            await self.item_service.create(item)
        return order
```

## Custom Service Methods

```python
from uuid import UUID
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from litestar.exceptions import PermissionDeniedException
from app.db import models as m


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    """User service with custom domain operations."""

    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo

    async def get_by_email(self, email: str) -> m.User | None:
        """Find user by email address."""
        return await self.get_one_or_none(email=email)

    async def authenticate(self, email: str, password: str) -> m.User:
        """Authenticate user against stored password hash."""
        user = await self.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise PermissionDeniedException("Invalid credentials")
        return user

    async def deactivate(self, user_id: UUID) -> m.User:
        """Deactivate user account."""
        return await self.update({"is_active": False}, item_id=user_id)
```

## Exception Handling

```python
from advanced_alchemy.exceptions import (
    NotFoundError,
    IntegrityError,
    RepositoryError,
)

try:
    user = await service.get(user_id)
except NotFoundError:
    raise HTTPException(status_code=404, detail="User not found")
```

## Slug Generation & Relationship Population in Lifecycle Hooks

Pair `SQLAlchemyAsyncSlugRepository` (`get_available_slug`) and `UniqueMixin` (`as_unique_async`) inside `to_model_on_create`, `to_model_on_update`, and `to_model_on_upsert` to auto-populate slugs and resolve child collections from plain input payloads:

```python
from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository
from advanced_alchemy.service import (
    ModelDictT,
    SQLAlchemyAsyncRepositoryService,
    is_dict,
    is_dict_with_field,
    is_dict_without_field,
    schema_dump,
)
from advanced_alchemy.utils.text import slugify
from app.db import models as m


class TagService(SQLAlchemyAsyncRepositoryService[m.Tag]):
    """Tag service with automatic slug assignment across create/update/upsert."""

    class Repo(SQLAlchemyAsyncSlugRepository[m.Tag]):
        model_type = m.Tag

    repository_type = Repo
    match_fields = ["name"]

    async def to_model_on_create(self, data: ModelDictT[m.Tag]) -> ModelDictT[m.Tag]:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug"):
            data["slug"] = await self.repository.get_available_slug(data["name"])
        return data

    async def to_model_on_update(self, data: ModelDictT[m.Tag]) -> ModelDictT[m.Tag]:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
            data["slug"] = await self.repository.get_available_slug(data["name"])
        return data

    async def to_model_on_upsert(self, data: ModelDictT[m.Tag]) -> ModelDictT[m.Tag]:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and (name := data.get("name")) is not None:
            data["slug"] = await self.repository.get_available_slug(name)
        return data


class ProjectService(SQLAlchemyAsyncRepositoryService[m.Project]):
    """Project service resolving unique tags and owner membership on create."""

    class Repo(SQLAlchemyAsyncSlugRepository[m.Project]):
        model_type = m.Project

    repository_type = Repo
    match_fields = ["name"]

    async def to_model_on_create(self, data: ModelDictT[m.Project]) -> m.Project:
        data = schema_dump(data)
        if is_dict(data):
            if "slug" not in data:
                data["slug"] = await self.repository.get_available_slug(data["name"])
            owner_id = data.pop("owner_id", None)
            tag_names: list[str] = data.pop("tags", [])
            db_obj = await super().to_model(data, "create")
            if owner_id is not None:
                db_obj.members.append(
                    m.ProjectMember(user_id=owner_id, role="ADMIN", is_owner=True),
                )
            if tag_names:
                db_obj.tags.extend(
                    [
                        await m.Tag.as_unique_async(
                            self.repository.session,
                            name=tag_text,
                            slug=slugify(tag_text),
                        )
                        for tag_text in tag_names
                    ],
                )
            return db_obj
        return await super().to_model(data, "create")
```

## Read-Only Analytics with `SQLAlchemyAsyncQueryService`

Use `SQLAlchemyAsyncQueryService` for aggregate or reporting endpoints that do not map to a single ORM entity. Wrap raw SQL execution in `wrap_sqlalchemy_exception()` and use `service.to_schema()` to return paginated responses:

```python
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception
from advanced_alchemy.service import OffsetPagination, SQLAlchemyAsyncQueryService
from sqlalchemy import RowMapping, text
from app import schemas as s


class StatsService(SQLAlchemyAsyncQueryService):
    """Read-only service for aggregate application metrics."""

    async def users_by_week(self) -> list[RowMapping]:
        """Aggregate new user registrations by week."""
        statement = text(
            """
            SELECT date_trunc('week', user_account.joined_at) AS week,
                   count(user_account.id) AS new_users
            FROM user_account
            GROUP BY 1
            ORDER BY 1
            """,
        )
        with wrap_sqlalchemy_exception():
            result = await self.repository.session.execute(statement)
            return list(result.mappings())


async def get_weekly_user_stats(stats_service: StatsService) -> OffsetPagination[s.UsersByWeek]:
    """Convert raw RowMapping results into an OffsetPagination schema response."""
    rows = await stats_service.users_by_week()
    return stats_service.to_schema(data=rows, schema_type=s.UsersByWeek)
```

## Idempotent Fixture Seeding (`open_fixture_async` + `upsert_many`)

Use `open_fixture_async` (or `open_fixture`) from `advanced_alchemy.utils.fixtures` with `service.upsert_many()` to seed JSON fixtures idempotently from CLI commands or startup hooks:

```python
from pathlib import Path
from advanced_alchemy.utils.fixtures import open_fixture_async
from app.config import alchemy_config
from app.domain.accounts.services import RoleService


async def seed_reference_data(fixtures_path: Path) -> None:
    """Load role fixtures from role.json and upsert by name."""
    async with RoleService.new(config=alchemy_config) as role_service:
        fixture_data = await open_fixture_async(fixtures_path, "role")
        await role_service.upsert_many(
            match_fields=["name"],
            data=fixture_data,
            auto_commit=True,
        )
```
