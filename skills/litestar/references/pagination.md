# Pagination (`OffsetPagination` + `create_filter_dependencies`)

Never hand-roll `limit` / `offset` query params. Use `create_filter_dependencies` from `advanced_alchemy.extensions.litestar` to declare the filter set on the Controller; pair `list_and_count` with `to_schema` for the response envelope.

## Pattern

```python
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from litestar import Controller, get
from litestar.params import Dependency, Parameter

from advanced_alchemy.extensions.litestar import create_filter_dependencies
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

## `OffsetPagination[T]` Response Shape

```json
{
  "items": [ ... ],
  "limit": 20,
  "offset": 0,
  "total": 137
}
```

The DTO `T` is whatever you pass to `schema_type=`. Clients page by setting `?currentPage=2&pageSize=20` (camelCase, since DTOs rename) or the equivalent `limit` / `offset` query params depending on `pagination_type`.

## Filter Field Catalog

`create_filter_dependencies` accepts a dict mapping filter names to config:

| Key | Type | Purpose |
|---|---|---|
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

## `list_and_count` + `to_schema` Workflow

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

## Cross-references

- Repository service methods (`list_and_count`, `to_schema`): [services.md](services.md)
- DTO definitions for `schema_type`: [dto.md](dto.md)
- Controller class structure: [routing.md](routing.md)
