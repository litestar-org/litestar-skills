# Filter System

## Overview

Advanced Alchemy provides a composable filter and pagination system that integrates with the repository and service layers. Filters are passed as positional arguments to `get_many()` and `get_many_and_count()` methods.

```python
from advanced_alchemy.filters import (
    BeforeAfter,
    BooleanFilter,
    ChoicesFilter,
    CollectionFilter,
    ComparisonFilter,
    ExistsFilter,
    FilterGroup,
    FilterTypes,
    LimitOffset,
    MultiFilter,
    NotExistsFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.service.pagination import OffsetPagination
```

---

## FilterTypes

`FilterTypes` is the union type representing all valid filters. Use it as the type annotation when accepting filters:

```python
from advanced_alchemy.filters import FilterTypes


async def list_items(self, *filters: FilterTypes) -> list[Model]:
    return await self.service.get_many(*filters)
```

---

## Built-in Filters

### Filtering by Primary Key

To filter by a list of primary key values, use `CollectionFilter` with `field_name="id"` (generates an `IN` clause on the `id` column).

```python
from advanced_alchemy.filters import CollectionFilter

results = await service.get_many(
    CollectionFilter(field_name="id", values=[id1, id2, id3]),
)
```

### CollectionFilter

Filter where a column's value is in a given collection (`IN` clause on any field).

```python
from advanced_alchemy.filters import CollectionFilter

results = await service.get_many(
    CollectionFilter(field_name="status", values=["active", "pending"]),
)

results = await service.get_many(
    CollectionFilter(field_name="team_id", values=[team1_id, team2_id]),
)
```

### NotInCollectionFilter

Inverse of `CollectionFilter` — excludes rows where the field value is in the collection (`NOT IN`).

```python
from advanced_alchemy.filters import NotInCollectionFilter

results = await service.get_many(
    NotInCollectionFilter(field_name="status", values=["archived", "deleted"]),
)
```

### SearchFilter

Text search on one or more columns using SQL `LIKE` / `ILIKE`.

```python
from advanced_alchemy.filters import SearchFilter

results = await service.get_many(
    SearchFilter(field_name="name", value="john", ignore_case=True),
)

results = await service.get_many(
    SearchFilter(field_name={"name", "email"}, value="acme", ignore_case=True),
)
```

- `field_name`: single column name (`str`) or `set[str]` (combines multiple columns with `OR`)
- `ignore_case=False` (default): uses case-sensitive `.like()`; set `ignore_case=True` for case-insensitive `.ilike()`
- The value is wrapped in `%value%` wildcards automatically

### NotInSearchFilter

Inverse of `SearchFilter` — excludes rows matching the pattern (`NOT LIKE` / `NOT ILIKE`, combining multiple `field_name` entries with `AND`). Accepts `ignore_case`.

```python
from advanced_alchemy.filters import NotInSearchFilter

results = await service.get_many(
    NotInSearchFilter(field_name="email", value="@test.com", ignore_case=True),
)
```

### BeforeAfter

Filter a datetime column by a range (before and/or after a given timestamp).

```python
from datetime import datetime, timezone
from advanced_alchemy.filters import BeforeAfter

results = await service.get_many(
    BeforeAfter(
        field_name="created_at",
        before=datetime(2025, 12, 31, tzinfo=timezone.utc),
        after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
)

results = await service.get_many(
    BeforeAfter(field_name="expires_at", before=datetime.now(timezone.utc), after=None),
)
```

- Uses strict inequality: `after < column < before`

### OnBeforeAfter

Like `BeforeAfter` but uses inclusive inequality (`>=` and `<=`).

```python
from datetime import datetime, timezone
from advanced_alchemy.filters import OnBeforeAfter

results = await service.get_many(
    OnBeforeAfter(
        field_name="scheduled_at",
        on_or_before=datetime(2025, 12, 31, tzinfo=timezone.utc),
        on_or_after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
)
```

### Filtering on Audit Columns

To filter on the `created_at` and `updated_at` audit columns provided by `*AuditBase` classes, use `BeforeAfter` (or `OnBeforeAfter`) with the appropriate `field_name`.

```python
from datetime import datetime, timezone
from advanced_alchemy.filters import BeforeAfter

results = await service.get_many(
    BeforeAfter(field_name="created_at", before=None, after=datetime(2025, 6, 1, tzinfo=timezone.utc)),
)

results = await service.get_many(
    BeforeAfter(field_name="updated_at", before=datetime(2025, 1, 1, tzinfo=timezone.utc), after=None),
)
```

### OrderBy

Sort results by a column, model attribute, or SQL expression.

```python
from advanced_alchemy.filters import OrderBy

results = await service.get_many(
    OrderBy(field_name="created_at", sort_order="desc"),
)
```

- `sort_order`: `"asc"` (default) or `"desc"`

### LimitOffset

Pagination via limit and offset.

```python
from advanced_alchemy.filters import LimitOffset

results, total = await service.get_many_and_count(
    LimitOffset(limit=20, offset=0),
)

results, total = await service.get_many_and_count(
    LimitOffset(limit=20, offset=20),
)
```

### NullFilter / NotNullFilter

`IS NULL` / `IS NOT NULL` on a column (added 1.9).

```python
from advanced_alchemy.filters import NotNullFilter, NullFilter

results = await service.get_many(NullFilter(field_name="deleted_at"))
results = await service.get_many(NotNullFilter(field_name="verified_at"))
```

### ComparisonFilter

A single `field op value` comparison supporting 16 operators (`VALID_OPERATORS`):

- Equality & ordering: `eq`, `ne`, `gt`, `ge`, `lt`, `le`
- Set & range membership: `in`, `notin`, `between` (expects a 2-tuple/list `(low, high)`)
- Pattern matching: `like`, `ilike`, `startswith`, `istartswith`, `endswith`, `iendswith`
- Date equality: `dateeq`

```python
from advanced_alchemy.filters import ComparisonFilter

results = await service.get_many(
    ComparisonFilter(field_name="age", operator="ge", value=18),
    ComparisonFilter(field_name="score", operator="between", value=(50, 100)),
)
```

### ChoicesFilter / BooleanFilter

Added 1.11. `ChoicesFilter` matches a field against an allowed set (an `IN` over a fixed choice list); `BooleanFilter` matches a boolean field (no-op when `value` is `None`, which is handy for optional query params).

```python
from advanced_alchemy.filters import BooleanFilter, ChoicesFilter

results = await service.get_many(ChoicesFilter(field_name="status", values=["active", "pending"]))
results = await service.get_many(BooleanFilter(field_name="is_published", value=True))
```

### ExistsFilter / NotExistsFilter

Correlated `EXISTS` / `NOT EXISTS` built from a list of column expressions combined with `operator` (`"and"` / `"or"`).

```python
from advanced_alchemy.filters import ExistsFilter

results = await service.get_many(
    ExistsFilter(values=[Post.author_id == User.id], operator="and"),
)
```

### FilterGroup / MultiFilter (composite)

`FilterGroup` joins several filters under one logical operator; `MultiFilter` builds a nested filter tree from a serialized dict (useful for client-driven advanced search).

```python
from advanced_alchemy.filters import BooleanFilter, ComparisonFilter, FilterGroup
from sqlalchemy import or_

group = FilterGroup(
    logical_operator=or_,
    filters=[BooleanFilter("is_featured", True), ComparisonFilter("views", "ge", 1000)],
)
results = await service.get_many(group)
```

> Filter values may also be SQLAlchemy func expressions (1.8+), e.g. comparing against `func.lower(...)`.

---

## Composing Filters

Filters are passed as positional arguments and are combined with AND logic:

```python
from datetime import datetime, timezone
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
    OrderBy,
    SearchFilter,
)

results, total = await service.get_many_and_count(
    SearchFilter(field_name="name", value="acme", ignore_case=True),
    CollectionFilter(field_name="status", values=["active", "trial"]),
    BeforeAfter(
        field_name="created_at",
        before=datetime(2025, 12, 31, tzinfo=timezone.utc),
        after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    OrderBy(field_name="name", sort_order="asc"),
    LimitOffset(limit=25, offset=0),
)
```

---

## Pagination Types

### OffsetPagination

Standard offset-based pagination response object for API endpoints.

```python
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.service import OffsetPagination


@get("/users")
async def list_users(
    user_service: UserService,
    limit: int = 20,
    offset: int = 0,
) -> OffsetPagination[UserSchema]:
    filters = [LimitOffset(limit=limit, offset=offset)]
    results, total = await user_service.get_many_and_count(*filters)
    return user_service.to_schema(
        results,
        total,
        filters=filters,
        schema_type=UserSchema,
    )
```

`OffsetPagination` fields:

- `items`: list of results
- `total`: total count of matching records
- `limit`: page size
- `offset`: current offset

### Cursor-Based Pagination

Advanced Alchemy ships `OffsetPagination` out of the box. For cursor-style pagination over large datasets, build the response manually using a `BeforeAfter` (or comparison) filter on a sortable column such as `created_at` or a UUIDv7 `id`, plus a `LimitOffset(limit=page_size, offset=0)` to cap the page. The "next cursor" is the last item's sortable value:

```python
from advanced_alchemy.filters import BeforeAfter, LimitOffset, OrderBy

results = await service.get_many(
    BeforeAfter(field_name="created_at", before=None, after=last_seen_created_at),
    OrderBy(field_name="created_at", sort_order="asc"),
    LimitOffset(limit=page_size, offset=0),
)
next_cursor = results[-1].created_at if results else None
```

- Avoids `OFFSET` performance degradation on large tables.
- Works well for append-mostly tables (logs, events, feeds) where rows may be inserted between pages.

---

## Litestar Filter Dependencies

### create_filter_dependencies()

Automatically creates Litestar dependency providers that parse filter parameters from query strings using `FilterConfig`:

```python
from uuid import UUID

from advanced_alchemy.extensions.litestar.providers import (
    ChoiceField,
    FieldNameType,
    create_filter_dependencies,
)

filter_deps = create_filter_dependencies(
    {
        "id_filter": UUID,
        "id_field": "id",
        "search": {"name", "email"},
        "search_ignore_case": True,
        "created_at": True,
        "updated_at": True,
        "pagination_type": "limit_offset",
        "pagination_size": 20,
        "sort_field": "created_at",
        "sort_order": "desc",
        "in_fields": {FieldNameType(name="team_id", type_hint=UUID)},
        "not_in_fields": {"role"},
        "boolean_fields": {"is_active", "is_verified"},
        "choice_fields": [ChoiceField(name="status", choices=("active", "pending", "suspended"))],
    }
)
```

| `FilterConfig` Key | Type | Generated Query Parameter(s) |
| --- | --- | --- |
| `id_filter` | `type[UUID \| int \| str]` | `ids` |
| `id_field` | `str` (default `"id"`) | Target model column for `id_filter` |
| `search` | `str \| set[str] \| list[str]` | `searchString` |
| `search_ignore_case` | `bool` | `searchIgnoreCase` |
| `created_at` | `bool` | `createdBefore`, `createdAfter` |
| `updated_at` | `bool` | `updatedBefore`, `updatedAfter` |
| `pagination_type` | `Literal["limit_offset"]` | `currentPage`, `pageSize` |
| `pagination_size` | `int` (default `20`) | Default `pageSize` value |
| `sort_field` | `str \| set[str] \| list[str]` | `orderBy` |
| `sort_order` | `Literal["asc", "desc"]` | `sortOrder` |
| `in_fields` | `FieldNameConfig` | `<field>In` (camelCase, e.g. `teamIdIn`) |
| `not_in_fields` | `FieldNameConfig` | `<field>NotIn` (camelCase, e.g. `roleNotIn`) |
| `boolean_fields` | `FieldNameConfig` | `<field>` boolean query param (camelCase, e.g. `isActive`) |
| `choice_fields` | `ChoiceFieldConfig` | `<field>` literal choice query param (`ChoiceField(name, choices)` or `(name, choices)`) |

### Using in Litestar Routes

```python
from advanced_alchemy.filters import FilterTypes
from litestar import get
from litestar.di import Provide


@get("/users", dependencies=filter_deps)
async def list_users(
    user_service: UserService,
    filters: list[FilterTypes],
) -> OffsetPagination[UserSchema]:
    results, total = await user_service.get_many_and_count(*filters)
    return user_service.to_schema(
        results,
        total,
        filters=filters,
        schema_type=UserSchema,
    )
```

### Controller-Level Filter Configuration

Apply filter dependencies at the controller level for all routes:

```python
from litestar import Controller, get
from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies


class UserController(Controller):
    path = "/users"
    dependencies = create_filter_dependencies(
        {
            "search": {"name", "email"},
            "pagination_type": "limit_offset",
            "sort_field": "created_at",
        }
    )

    @get()
    async def list_users(
        self,
        user_service: UserService,
        filters: list[FilterTypes],
    ) -> OffsetPagination[UserSchema]:
        results, total = await user_service.get_many_and_count(*filters)
        return user_service.to_schema(
            results,
            total,
            filters=filters,
            schema_type=UserSchema,
        )
```

---

## Custom Filter Creation

Create domain-specific filters by building on existing filter types:

```python
from advanced_alchemy.filters import FilterTypes, CollectionFilter, BeforeAfter


def active_users_filter() -> list[FilterTypes]:
    """Pre-built filter for active users."""
    return [
        CollectionFilter(field_name="is_active", values=[True]),
    ]


def recent_items_filter(days: int = 30) -> list[FilterTypes]:
    """Filter for items created in the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [
        BeforeAfter(field_name="created_at", before=None, after=cutoff),
    ]


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    """User service using custom composite filters."""

    async def list_active(self, *extra_filters: FilterTypes) -> list[m.User]:
        """List active users with optional additional filters."""
        filters = [*active_users_filter(), *extra_filters]
        return await self.get_many(*filters)
```

---

## Frontend Integration Patterns

### Mapping Frontend Table Parameters to Filters

Common pattern for mapping frontend data-table query parameters to AA filters:

```python
from advanced_alchemy.filters import (
    FilterTypes,
    LimitOffset,
    OrderBy,
    SearchFilter,
)


def build_filters(
    *,
    page: int = 1,
    page_size: int = 20,
    sort_field: str | None = None,
    sort_order: str = "asc",
    search: str | None = None,
    search_field: str = "name",
) -> list[FilterTypes]:
    """Convert frontend table params to AA filters."""
    filters: list[FilterTypes] = [
        LimitOffset(limit=page_size, offset=(page - 1) * page_size),
    ]
    if sort_field:
        filters.append(OrderBy(field_name=sort_field, sort_order=sort_order))
    if search:
        filters.append(
            SearchFilter(field_name=search_field, value=search, ignore_case=True),
        )
    return filters
```

### Pagination Response Mapping

OffsetPagination maps directly to frontend table expectations:

```json
{
  "items": [],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

Frontend calculates:

- `total_pages = ceil(total / limit)`
- `current_page = (offset / limit) + 1`
