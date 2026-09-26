# Pagination and Filters — Per-Stack Patterns

Never hand-roll `limit` / `offset` query params inside a route handler. Both `advanced-alchemy` and `sqlspec` provide declarative Litestar filter dependency generators (`create_filter_dependencies`) and typed pagination envelopes (`OffsetPagination[T]`, plus `CursorPagination[T]` in `sqlspec`). Pick the branch that matches your project's data stack.

## Filter & Pagination Symbol Matrix (`advanced-alchemy` vs `sqlspec`)

Do not mix filter imports across libraries — their class names and module paths differ:

| Concern | `advanced-alchemy` (`advanced_alchemy.filters` / `advanced_alchemy.service`) | `sqlspec` (`sqlspec.core` / `sqlspec.core.filters`) |
| --- | --- | --- |
| Filter union type | `FilterTypes` (`advanced_alchemy.filters`) | `FilterTypes` (`sqlspec.core`) |
| Limit / offset filter | `LimitOffset(limit, offset)` | `LimitOffsetFilter(limit, offset)` |
| Cursor / keyset filter | *(not supported)* | `CursorFilter(keys=..., cursor=..., limit=..., secret=...)`, `CursorKey`, `CursorKeys` |
| Order-by filter | `OrderBy(field_name, sort_order)` | `OrderByFilter(field_name, sort_order)` |
| Search filter | `SearchFilter`, `NotInSearchFilter` | `SearchFilter`, `NotInSearchFilter` |
| Timestamp range filter | `BeforeAfter`, `OnBeforeAfter` | `BeforeAfterFilter`, `OnBeforeAfterFilter` |
| Collection `IN` / `NOT IN` | `CollectionFilter`, `NotInCollectionFilter` | `InCollectionFilter`, `NotInCollectionFilter`, `AnyCollectionFilter`, `NotAnyCollectionFilter` |
| Boolean / choice / null filters | `BooleanFilter`, `ChoicesFilter`, `NullFilter`, `NotNullFilter` | `BooleanFilter`, `ChoicesFilter`, `NullFilter`, `NotNullFilter` |
| Offset pagination envelope | `OffsetPagination[T]` (`advanced_alchemy.service`) | `OffsetPagination[T]` (`sqlspec.core`) |
| Cursor pagination envelope | *(not supported)* | `CursorPagination[T]` (`sqlspec.core`) |
| Litestar DI provider factory | `create_service_dependencies`, `create_filter_dependencies` (`advanced_alchemy.extensions.litestar.providers`) | `create_filter_dependencies` (`sqlspec.extensions.litestar.providers`) |

> [!IMPORTANT]
> Always wrap injected `list[FilterTypes]` in `SkipValidation[list[FilterTypes]]` (from `litestar.params`) or `Dependency(skip_validation=True)` so Litestar's signature model does not attempt runtime union validation on filter instances constructed by the provider.

## Branch A — `advanced-alchemy` pagination and filters

Use `create_service_dependencies` from `advanced_alchemy.extensions.litestar.providers` when the Controller also needs the service dependency, or `create_filter_dependencies` when service DI is wired separately. Pair `get_many_and_count(*filters)` with `to_schema(results, total, filters=filters, schema_type=...)` to return `OffsetPagination[T]`.

```python
from __future__ import annotations

from uuid import UUID

from advanced_alchemy.extensions.litestar.providers import (
    ChoiceField,
    FieldNameType,
    create_service_dependencies,
)
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination
from litestar import Controller, get
from litestar.di import NamedDependency
from litestar.params import FromPath, SkipValidation

from app.domain.accounts.guards import requires_superuser
from app.domain.users.schemas import User
from app.domain.users.services import UserService


class UserController(Controller):
    """User management endpoints."""

    path = "/api/users"
    tags = ["Users"]
    guards = [requires_superuser]
    dependencies = create_service_dependencies(
        UserService,
        key="users_service",
        filters={
            "id_filter": UUID,
            "id_field": "id",
            "pagination_type": "limit_offset",
            "pagination_size": 20,
            "search": "name,email",
            "search_ignore_case": True,
            "sort_field": "created_at",
            "sort_order": "desc",
            "created_at": True,
            "updated_at": True,
            "boolean_fields": "is_active,is_verified",
            "in_fields": [FieldNameType(name="role_id", type_hint=UUID)],
            "choice_fields": [ChoiceField(name="status", choices=("active", "suspended"))],
        },
    )

    @get("/", operation_id="ListUsers", name="ListUsers", summary="List Users")
    async def list_users(
        self,
        users_service: NamedDependency[UserService],
        filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> OffsetPagination[User]:
        """Return paginated users matching query filters."""
        results, total = await users_service.get_many_and_count(*filters)
        return users_service.to_schema(results, total, filters=filters, schema_type=User)

    @get("/{user_id:uuid}", operation_id="GetUser")
    async def get_user(
        self,
        users_service: NamedDependency[UserService],
        user_id: FromPath[UUID],
    ) -> User:
        """Return a single user by ID."""
        db_user = await users_service.get(user_id)
        return users_service.to_schema(db_user, schema_type=User)
```

### `OffsetPagination[T]` response shape

```json
{
  "items": [ ... ],
  "limit": 20,
  "offset": 0,
  "total": 137
}
```

Clients page by passing `?currentPage=2&pageSize=20` in the query string. The `limit_offset_filter` dependency translates `currentPage` and `pageSize` into `LimitOffset(limit=page_size, offset=page_size * (current_page - 1))`.

### `advanced-alchemy` `FilterConfig` catalog

`create_service_dependencies(..., filters={...})` and `create_filter_dependencies({...})` accept `FilterConfig` keys:

| Key | Type | Query parameters exposed | Purpose |
| --- | --- | --- | --- |
| `id_filter` | `type[UUID \| int \| str]` | `?ids=...` | `CollectionFilter` (`IN (...)`) on `id_field` |
| `id_field` | `str` | — | Column name for `id_filter` / `not_in_fields` (default `"id"`) |
| `pagination_type` | `Literal["limit_offset"]` | `?currentPage=1&pageSize=20` | Enables `LimitOffset` filter dependency |
| `pagination_size` | `int` | — | Default `pageSize` (default `20`) |
| `search` | `str \| set[str] \| list[str]` | `?searchString=...&searchIgnoreCase=...` | `SearchFilter` (`LIKE` / `ILIKE`) across the listed columns |
| `search_ignore_case` | `bool` | — | Default for `searchIgnoreCase` (default `False`) |
| `sort_field` | `str \| set[str] \| list[str]` | `?orderBy=...&sortOrder=asc\|desc` | Default sort column(s) for `OrderBy` |
| `sort_order` | `Literal["asc", "desc"]` | — | Default sort direction (default `"desc"`) |
| `created_at` | `bool` | `?createdBefore=...&createdAfter=...` | `BeforeAfter` filter on `created_at` |
| `updated_at` | `bool` | `?updatedBefore=...&updatedAfter=...` | `BeforeAfter` filter on `updated_at` |
| `in_fields` | `FieldNameType \| set[FieldNameType] \| list[FieldNameType]` | `?{field}In=...` | Additional `CollectionFilter` fields |
| `not_in_fields` | `FieldNameType \| set[FieldNameType] \| list[FieldNameType]` | `?{field}NotIn=...` | `NotInCollectionFilter` (`NOT IN (...)`) fields |
| `boolean_fields` | `str \| set[str] \| list[str]` | `?{field}=true\|false` | Exact boolean column filters (`BooleanFilter`) |
| `choice_fields` | `ChoiceField \| Sequence[ChoiceField]` | `?{field}=...` | Enum/literal constrained filters (`ChoicesFilter`) |

### `DependencyDefaults` keys

Customize DI key names or default page size by passing `dep_defaults=DependencyDefaults(...)` from `advanced_alchemy.extensions.litestar.providers`:

- `FILTERS_DEPENDENCY_KEY = "filters"`
- `ID_FILTER_DEPENDENCY_KEY = "id_filter"`
- `LIMIT_OFFSET_FILTER_DEPENDENCY_KEY = "limit_offset_filter"`
- `ORDER_BY_FILTER_DEPENDENCY_KEY = "order_by_filter"`
- `SEARCH_FILTER_DEPENDENCY_KEY = "search_filter"`
- `CREATED_FILTER_DEPENDENCY_KEY = "created_filter"`
- `UPDATED_FILTER_DEPENDENCY_KEY = "updated_filter"`
- `DEFAULT_PAGINATION_SIZE = 20`

## Branch B — `sqlspec` pagination and filters

`sqlspec.extensions.litestar.providers.create_filter_dependencies` exposes the same declarative `FilterConfig` pattern for `sqlspec` controllers, plus first-party **cursor pagination**, `pagination_max_size`, `null_fields`, `not_null_fields`, and `sort_field_aliases`.

Pair `create_filter_dependencies` on the Controller with `SQLSpecAsyncService.paginate(...)` (or `paginate_limit_offset` / `paginate_cursor`):

```python
from __future__ import annotations

from uuid import UUID

from litestar import Controller, get
from litestar.di import NamedDependency, Provide
from litestar.params import SkipValidation
from sqlspec import sql
from sqlspec.core import FilterTypes, OffsetPagination
from sqlspec.extensions.litestar.providers import FieldNameType, create_filter_dependencies
from sqlspec.service import SQLSpecAsyncService

from app.domain.accounts.schemas import User


class UserService(SQLSpecAsyncService):
    """User service backed by SQLSpec."""

    async def list_users(self, *filters: FilterTypes) -> OffsetPagination[User]:
        """List users with limit-offset pagination."""
        stmt = sql.select("id", "email", "name", "is_active", "created_at").from_("users")
        return await self.paginate_limit_offset(stmt, *filters, schema_type=User)


class UserController(Controller):
    """User endpoints."""

    path = "/api/users"
    dependencies = {
        "users_service": Provide(UserService),
        **create_filter_dependencies(
            {
                "id_filter": UUID,
                "id_field": "id",
                "pagination_type": "limit_offset",
                "pagination_size": 20,
                "pagination_max_size": 200,
                "search": "name,email",
                "search_ignore_case": True,
                "sort_field": "created_at",
                "sort_order": "desc",
                "created_at": True,
                "updated_at": True,
                "boolean_fields": "is_active",
                "null_fields": "deleted_at",
                "in_fields": [FieldNameType(name="tenant_id", type_hint=UUID)],
            }
        ),
    }

    @get("/", operation_id="ListUsers")
    async def list_users(
        self,
        users_service: NamedDependency[UserService],
        filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> OffsetPagination[User]:
        """Return paginated users matching query filters."""
        return await users_service.list_users(*filters)
```

### `sqlspec`-specific `FilterConfig` keys

In addition to all `FilterConfig` keys listed in Branch A, `sqlspec.extensions.litestar.providers.FilterConfig` supports:

| Key | Type | Query parameters exposed | Purpose |
| --- | --- | --- | --- |
| `pagination_type` | `Literal["limit_offset", "cursor"]` | `?currentPage=&pageSize=` or `?cursor=&pageSize=` | Choose offset pagination (`LimitOffsetFilter`) or keyset pagination (`CursorFilter`) |
| `cursor_keys` | `CursorKeys` (`tuple[CursorKey, ...]`) | `?cursor=...&pageSize=...` | Required when `pagination_type="cursor"`; defines keyset sort columns, direction, and types |
| `cursor_secret` | `str \| bytes` | — | Optional HMAC-SHA256 signing key to prevent client cursor tampering |
| `pagination_max_size` | `int` | — | Maximum allowed `pageSize` enforced via `Parameter(le=...)` (default `1000`) |
| `sort_field_aliases` | `dict[str, str]` | — | Map public API sort field names to SQL column expressions |
| `sort_field_camelize` | `bool` | — | Automatically register camelCase aliases for snake_case `sort_field` names (default `True`) |
| `null_fields` | `str \| set[str] \| list[str]` | `?{field}IsNull=true` | `NullFilter` (`IS NULL`) |
| `not_null_fields` | `str \| set[str] \| list[str]` | `?{field}IsNotNull=true` | `NotNullFilter` (`IS NOT NULL`) |

### Cursor pagination in `sqlspec` (`CursorFilter` + `CursorPagination[T]`)

Use cursor (keyset) pagination for infinite scroll feeds, high-offset tables, or real-time streams where offset pagination degrades. Always include a unique tie-breaker column (such as `id`) as the final `CursorKey`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from litestar import Controller, get
from litestar.di import NamedDependency, Provide
from litestar.params import SkipValidation
from sqlspec import sql
from sqlspec.core import CursorKey, CursorPagination, FilterTypes
from sqlspec.extensions.litestar.providers import create_filter_dependencies
from sqlspec.service import SQLSpecAsyncService

from app.domain.events.schemas import AuditEvent
from app.lib.settings import get_settings


class AuditEventService(SQLSpecAsyncService):
    """Audit event query service."""

    async def list_events(self, *filters: FilterTypes) -> CursorPagination[AuditEvent]:
        """Return a cursor-paginated page of audit events."""
        stmt = sql.select("id", "actor_id", "action", "created_at").from_("audit_events")
        return await self.paginate_cursor(stmt, *filters, schema_type=AuditEvent)


class AuditEventController(Controller):
    """Audit event endpoints."""

    path = "/api/audit-events"
    dependencies = {
        "events_service": Provide(AuditEventService),
        **create_filter_dependencies(
            {
                "pagination_type": "cursor",
                "pagination_size": 50,
                "pagination_max_size": 250,
                "cursor_keys": (
                    CursorKey(field_name="created_at", sort_order="desc"),
                    CursorKey(field_name="id", sort_order="desc"),
                ),
                "cursor_secret": get_settings().app.secret_key,
            }
        ),
    }

    @get("/", operation_id="ListAuditEvents")
    async def list_events(
        self,
        events_service: NamedDependency[AuditEventService],
        filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> CursorPagination[AuditEvent]:
        """List audit events with keyset cursor pagination."""
        return await events_service.list_events(*filters)
```

`CursorPagination[T]` serializes to:

```json
{
  "items": [ ... ],
  "limit": 50,
  "next_cursor": "eyJ2IjpbIjIwMjYtMDktMjZUMTI6MDA6MDBaIiwi..."
}
```

When `next_cursor` is `null`, the caller has reached the end of the dataset.

### Direct filter construction in `sqlspec` services

When calling `SQLSpecAsyncService` from background tasks, CLI commands, or custom endpoints, pass filter objects positionally (`*filters`) into `self.paginate(...)` or `self.driver.select_with_total(...)`:

```python
from uuid import UUID

from sqlspec import sql
from sqlspec.core import (
    InCollectionFilter,
    LimitOffsetFilter,
    OffsetPagination,
    OrderByFilter,
    SearchFilter,
)

from app.domain.posts.schemas import Post
from app.domain.posts.services import PostService


async def search_tenant_posts(
    service: PostService,
    tenant_ids: list[UUID],
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> OffsetPagination[Post]:
    """Run a programmatic filtered query using SQLSpec filter primitives."""
    stmt = sql.select("id", "title", "body", "tenant_id", "created_at").from_("posts")
    return await service.paginate_limit_offset(
        stmt,
        InCollectionFilter(field_name="tenant_id", values=tenant_ids),
        SearchFilter(field_name={"title", "body"}, value=query, ignore_case=True),
        OrderByFilter(field_name="created_at", sort_order="desc"),
        LimitOffsetFilter(limit=limit, offset=offset),
        schema_type=Post,
    )
```

## Branch C — raw SQLAlchemy pagination

If you are on raw SQLAlchemy without `advanced-alchemy`, apply `.limit()` / `.offset()` on a Core statement and return a typed `msgspec.Struct` pagination envelope:

```python
from __future__ import annotations

import msgspec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post


class PagePosts(msgspec.Struct, rename="camel"):
    """Paginated posts response envelope."""

    items: list[Post]
    limit: int
    offset: int
    total: int


async def list_posts(session: AsyncSession, limit: int = 20, offset: int = 0) -> PagePosts:
    """Return a page of posts and total count using raw SQLAlchemy."""
    stmt = select(Post).limit(limit).offset(offset).order_by(Post.created_at.desc())
    result = await session.execute(stmt)
    items = list(result.scalars())
    total = await session.scalar(select(func.count()).select_from(Post)) or 0
    return PagePosts(items=items, limit=limit, offset=offset, total=total)
```

Consider adopting `advanced-alchemy` or `sqlspec` once pagination and filtering span multiple Controllers.

## Cross-references

- Service layer methods (`get_many_and_count`, `to_schema`, `SQLSpecAsyncService.paginate`): [services-and-repos.md](services-and-repos.md)
- SQLSpec filter deep dive: [`../../sqlspec/references/filters.md`](../../sqlspec/references/filters.md)
- DTO definitions for `schema_type`: [dtos.md](dtos.md)
- Controller class structure: [handlers.md](handlers.md)
- Sibling skills: [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md), [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md)
