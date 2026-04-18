# Pagination — Per-Stack Patterns

Never hand-roll `limit` / `offset` query params inside a handler. The canonical pagination pattern depends on your data-access stack — pick the branch that matches your project.

## Pick the branch for your stack

- **`advanced-alchemy`** → `OffsetPagination[T]` + `create_filter_dependencies` (covered in full below). Controller declares the filter set declaratively; `list_and_count` + `to_schema` synthesize the response envelope.
- **`sqlspec`** → `LimitOffsetFilter` + `OrderByFilter` applied to the driver call. See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) for `*filters` composition and [`../../sqlspec/references/filters.md`](../../sqlspec/references/filters.md) for filter types.
- **raw SQLAlchemy** → apply `.limit()` / `.offset()` on a Core statement and return a hand-rolled pagination envelope (summary below).

## Branch A — `advanced-alchemy` pagination

Use `create_filter_dependencies` from `advanced_alchemy.extensions.litestar.providers` to declare the filter set on the Controller; pair `list_and_count` with `to_schema` for the response envelope.

```python
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from litestar import Controller, get
from litestar.params import Dependency, Parameter

from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination

from app.domain.users.schemas import User
from app.domain.users.services import UserService
from app.domain.accounts.guards import requires_superuser


class UserController(Controller):
    path = "/api/users"
    tags = ["Users"]
    guards = [requires_superuser]
    dependencies = create_filter_dependencies({
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
    })

    @get("/", operation_id="ListUsers", name="ListUsers", summary="List Users")
    async def list_users(
        self,
        users_service: UserService,
        filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
    ) -> OffsetPagination[User]:
        results, total = await users_service.list_and_count(*filters)
        return users_service.to_schema(results, total, filters=filters, schema_type=User)

    @get("/{user_id:uuid}", operation_id="GetUser")
    async def get_user(
        self,
        users_service: UserService,
        user_id: Annotated[UUID, Parameter(title="User ID")],
    ) -> User:
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

The DTO `T` is whatever you pass to `schema_type=`. Clients page by setting `?currentPage=2&pageSize=20` (camelCase, since DTOs rename) or the equivalent `limit` / `offset` query params depending on `pagination_type`.

### Filter field catalog

`create_filter_dependencies` accepts a dict mapping filter names to config:

| Key | Type | Purpose |
| --- | --- | --- |
| `id_filter` | type (`UUID`, `int`) | Add `?ids=<uuid>,<uuid>` filter |
| `id_field` | str | Column name to filter (default `"id"`) |
| `pagination_type` | `"limit_offset"` / `"cursor"` | Pagination mode |
| `pagination_size` | int | Default page size |
| `search` | comma-string or list | Searchable fields (`?searchString=foo`) |
| `search_ignore_case` | bool | Case-insensitive ILIKE |
| `sort_field` | str | Default sort column |
| `sort_order` | `"asc"` / `"desc"` | Default sort direction |
| `created_at` | bool | Add `?createdBefore=` / `?createdAfter=` filters |
| `updated_at` | bool | Add `?updatedBefore=` / `?updatedAfter=` filters |

### `list_and_count` + `to_schema` workflow

```python
# 1. Service returns raw rows + total count
results, total = await users_service.list_and_count(*filters)

# 2. to_schema wraps in OffsetPagination[T]
return users_service.to_schema(
    results,
    total,
    filters=filters,           # so it can read limit/offset back out
    schema_type=User,          # the camelized msgspec DTO
)
```

`to_schema` reads filter context to populate `limit`, `offset`, `total` — never compute them yourself.

## Branch B — `sqlspec` pagination (`LimitOffsetFilter` + `OrderByFilter`)

`sqlspec` exposes pagination as filter objects passed into driver calls. The Controller receives filters as a DI dependency, the service applies them to the SQL.

```python
from __future__ import annotations

from litestar import Controller, get
from litestar.params import Dependency

from sqlspec.core.filters import LimitOffsetFilter, OrderByFilter

from app.schemas import Post
from app.services import PostService


class PostController(Controller):
    path = "/api/posts"

    @get("/")
    async def list_posts(
        self,
        posts_service: PostService,
        limit_offset: LimitOffsetFilter,
        order_by: OrderByFilter,
    ) -> list[Post]:
        return await posts_service.list_all(limit_offset, order_by)
```

The service passes filters straight through to the driver:

```python
async def list_all(self, *filters) -> list[Post]:
    return await self.driver.select(
        "SELECT * FROM posts",
        filters=filters,
        schema_type=Post,
    )
```

See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) for the envelope shape and tenant-scoped filter patterns.

## Branch C — raw SQLAlchemy pagination

If you're on raw SA without `advanced-alchemy`, apply `.limit()` / `.offset()` on a Core statement and return a hand-rolled pagination envelope. The caller is responsible for computing `total` via a separate `count()` query.

```python
from __future__ import annotations

import msgspec
from sqlalchemy import func, select

from app.db.models import Post


class PagePosts(msgspec.Struct, rename="camel"):
    items: list[Post]
    limit: int
    offset: int
    total: int


async def list_posts(session: AsyncSession, limit: int = 20, offset: int = 0) -> PagePosts:
    stmt = select(Post).limit(limit).offset(offset).order_by(Post.created_at.desc())
    result = await session.execute(stmt)
    items = list(result.scalars())
    total = await session.scalar(select(func.count()).select_from(Post)) or 0
    return PagePosts(items=items, limit=limit, offset=offset, total=total)
```

No free filter DI, no automatic envelope. Consider graduating to `advanced-alchemy` or `sqlspec` once the pagination surface grows beyond one or two Controllers.

## Cross-references

- Repository service methods (advanced-alchemy `list_and_count`, `to_schema`): [services.md](services.md)
- DTO definitions for `schema_type`: [dto.md](dto.md)
- Controller class structure: [routing.md](routing.md)
- Sibling skills: [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md), [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md)
