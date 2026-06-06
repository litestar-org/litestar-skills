# Filter System

## Overview

Advanced Alchemy provides a composable filter and pagination system that integrates with the repository and service layers. Filters are passed as positional arguments to `get_many()` and `get_many_and_count()` methods.

```python
from advanced_alchemy.filters import (
    # Core filter type
    FilterTypes,
    # Filters
    SearchFilter,
    CollectionFilter,
    BeforeAfter,
    OnBeforeAfter,
    NotInCollectionFilter,
    NotInSearchFilter,
    OrderBy,
    # Value / null / comparison filters
    NullFilter,
    NotNullFilter,
    ComparisonFilter,
    ChoicesFilter,
    BooleanFilter,
    # Correlated subquery + composite filters
    ExistsFilter,
    NotExistsFilter,
    FilterGroup,
    MultiFilter,
    # Pagination
    LimitOffset,
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

# Get specific records by ID
results = await service.get_many(
    CollectionFilter(field_name="id", values=[id1, id2, id3]),
)
```

### CollectionFilter

Filter where a column's value is in a given collection (`IN` clause on any field).

```python
from advanced_alchemy.filters import CollectionFilter

# Filter by status
results = await service.get_many(
    CollectionFilter(field_name="status", values=["active", "pending"]),
)

# Filter by multiple IDs on a non-PK field
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

Text search on a column using SQL `LIKE` / `ILIKE`.

```python
from advanced_alchemy.filters import SearchFilter

# Case-insensitive search (default)
results = await service.get_many(
    SearchFilter(field_name="name", value="john", ignore_case=True),
)

# Case-sensitive search
results = await service.get_many(
    SearchFilter(field_name="email", value="@example.com", ignore_case=False),
)
```

- `ignore_case=True` (default): uses `ILIKE` on PostgreSQL, `LOWER()` comparison elsewhere
- The value is wrapped in `%value%` wildcards automatically

### NotInSearchFilter

Inverse of `SearchFilter` — excludes rows matching the pattern (`NOT LIKE`).

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

# Records created in a date range
results = await service.get_many(
    BeforeAfter(
        field_name="created_at",
        before=datetime(2025, 12, 31, tzinfo=timezone.utc),
        after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
)

# Only "before" — omit "after" by passing None
results = await service.get_many(
    BeforeAfter(field_name="expires_at", before=datetime.now(timezone.utc), after=None),
)
```

- Uses strict inequality: `after < column < before`

### OnBeforeAfter

Like `BeforeAfter` but uses inclusive inequality (`>=` and `<=`).

```python
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
from advanced_alchemy.filters import BeforeAfter

# Records created after a date
results = await service.get_many(
    BeforeAfter(field_name="created_at", before=None, after=datetime(2025, 6, 1, tzinfo=timezone.utc)),
)

# Records updated before a date
results = await service.get_many(
    BeforeAfter(field_name="updated_at", before=datetime(2025, 1, 1, tzinfo=timezone.utc), after=None),
)
```

### OrderBy

Sort results by a column.

```python
from advanced_alchemy.filters import OrderBy

# Sort by creation date descending
results = await service.get_many(
    OrderBy(field_name="created_at", sort_order="desc"),
)

# Sort by name ascending (default)
results = await service.get_many(
    OrderBy(field_name="name", sort_order="asc"),
)
```

- `sort_order`: `"asc"` (default) or `"desc"`

### LimitOffset

Pagination via limit and offset.

```python
from advanced_alchemy.filters import LimitOffset

# Page 1 (first 20 records)
results, total = await service.get_many_and_count(
    LimitOffset(limit=20, offset=0),
)

# Page 2
results, total = await service.get_many_and_count(
    LimitOffset(limit=20, offset=20),
)
```

### NullFilter / NotNullFilter

`IS NULL` / `IS NOT NULL` on a column (added 1.9).

```python
from advanced_alchemy.filters import NullFilter, NotNullFilter

results = await service.get_many(NullFilter(field_name="deleted_at"))       # only un-deleted
results = await service.get_many(NotNullFilter(field_name="verified_at"))   # only verified
```

### ComparisonFilter

A single `field op value` comparison (`eq`, `ne`, `gt`, `ge`, `lt`, `le`).

```python
from advanced_alchemy.filters import ComparisonFilter

results = await service.get_many(ComparisonFilter(field_name="age", operator="ge", value=18))
```

### ChoicesFilter / BooleanFilter

Added 1.11. `ChoicesFilter` matches a field against an allowed set (an `IN` over a fixed choice list); `BooleanFilter` matches a boolean field (no-op when `value` is `None`, which is handy for optional query params).

```python
from advanced_alchemy.filters import ChoicesFilter, BooleanFilter

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
from advanced_alchemy.filters import FilterGroup, BooleanFilter, ComparisonFilter

group = FilterGroup(
    logical_operator="or",
    filters=[BooleanFilter("is_featured", True), ComparisonFilter("views", "ge", 1000)],
)
results = await service.get_many(group)
```

> Filter values may also be SQLAlchemy func expressions (1.8+), e.g. comparing against `func.lower(...)`.

---

## Composing Filters

Filters are passed as positional arguments and are combined with AND logic:

```python
from advanced_alchemy.filters import (
    LimitOffset,
    OrderBy,
    SearchFilter,
    CollectionFilter,
    BeforeAfter,
)

results, total = await service.get_many_and_count(
    # Text search
    SearchFilter(field_name="name", value="acme", ignore_case=True),
    # Status filter
    CollectionFilter(field_name="status", values=["active", "trial"]),
    # Date range
    BeforeAfter(
        field_name="created_at",
        before=datetime(2025, 12, 31, tzinfo=timezone.utc),
        after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    # Sort
    OrderBy(field_name="name", sort_order="asc"),
    # Pagination
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
        results, total, filters=filters, schema_type=UserSchema,
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

Automatically creates Litestar dependency providers that parse filter parameters from query strings.

```python
from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies

# Creates dependencies for common filter patterns
filter_deps = create_filter_dependencies(
    id_filter=True,        # ?ids=uuid1,uuid2
    search=True,           # ?search=term&search_field=name
    created_at=True,       # ?created_before=...&created_after=...
    updated_at=True,       # ?updated_before=...&updated_after=...
    limit_offset=True,     # ?limit=20&offset=0
    order_by=True,         # ?order_by=created_at&sort_order=desc
)
```

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
        results, total, filters=filters, schema_type=UserSchema,
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
        search=True,
        limit_offset=True,
        order_by=True,
    )

    @get()
    async def list_users(
        self,
        user_service: UserService,
        filters: list[FilterTypes],
    ) -> OffsetPagination[UserSchema]:
        results, total = await user_service.get_many_and_count(*filters)
        return user_service.to_schema(
            results, total, filters=filters, schema_type=UserSchema,
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


# Usage in service methods
class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    async def list_active(self, *extra_filters: FilterTypes) -> list[m.User]:
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

```python
# OffsetPagination maps directly to frontend table expectations:
# {
#   "items": [...],
#   "total": 150,
#   "limit": 20,
#   "offset": 0
# }
#
# Frontend calculates:
#   total_pages = ceil(total / limit)
#   current_page = (offset / limit) + 1
```
