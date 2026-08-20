# SQLSpec Filter & Pagination System

## Overview

SQLSpec provides composable filter objects for common query patterns: pagination, ordering, searching, date ranges, and collection membership. Filters are designed to work with both raw SQL and the query builder.

---

## Built-in Filter Types

### LimitOffsetFilter

Standard offset-based pagination:

```python
from sqlspec.core.filters import LimitOffsetFilter

filter_ = LimitOffsetFilter(limit=20, offset=40)
```

### OrderByFilter

Dynamic column ordering:

```python
from sqlspec.core.filters import OrderByFilter

filter_ = OrderByFilter(field_name="created_at", sort_order="desc")
```

### SearchFilter

Text search across specified columns:

```python
from sqlspec.core.filters import SearchFilter

filter_ = SearchFilter(
    field_name="name",
    value="alice",
    ignore_case=True,
)
```

### BeforeAfterFilter

Date/time range filtering:

```python
from sqlspec.core.filters import BeforeAfterFilter
from datetime import datetime

filter_ = BeforeAfterFilter(
    field_name="created_at",
    before=datetime(2025, 12, 31),
    after=datetime(2025, 1, 1),
)
```

### InCollectionFilter

Filter rows where a column value is in a collection:

```python
from sqlspec.core.filters import InCollectionFilter

filter_ = InCollectionFilter(
    field_name="status",
    values=["active", "pending"],
)
```

---

## OffsetPagination Result Type

The standard pagination result container returned by `SQLSpecAsyncService.paginate()` / `SQLSpecSyncService.paginate()`:

- `result.items`: `list[T]` - current page rows
- `result.total`: `int` - total matching rows
- `result.limit`: `int` - page size
- `result.offset`: `int` - current offset

```python
from sqlspec.core import OffsetPagination

result: OffsetPagination[User]
```

---

## apply_filter()

Apply a filter to a SQL statement or query builder. The function takes a single filter; chain calls (or use a comprehension) to apply several:

```python
from sqlspec.core.filters import apply_filter, LimitOffsetFilter, OrderByFilter

stmt = sql.select("*").from_("users").where("active = true")

pagination = LimitOffsetFilter(limit=20, offset=0)
ordering = OrderByFilter(field_name="name", sort_order="asc")

stmt = apply_filter(stmt, pagination)
stmt = apply_filter(stmt, ordering)

rows = await db_session.select(stmt)
```

### Composing Multiple Filters

```python
from sqlspec.core.filters import apply_filter

filters = [
    SearchFilter(field_name="name", value="alice", ignore_case=True),
    BeforeAfterFilter(field_name="created_at", after=datetime(2025, 1, 1)),
    OrderByFilter(field_name="created_at", sort_order="desc"),
    LimitOffsetFilter(limit=20, offset=0),
]

stmt = sql.select("*").from_("users")
for f in filters:
    stmt = apply_filter(stmt, f)
rows = await db_session.select(stmt, schema_type=User)
```

Drivers also accept filter objects positionally — pass them directly to `select`/`select_with_total` and the driver applies them in order:

```python
rows, total = await db_session.select_with_total(
    sql.select("*").from_("users"),
    *filters,
    schema_type=User,
)
```

---

## Litestar Filter Dependencies

Use `create_filter_dependencies()` from `sqlspec.extensions.litestar.providers` to generate Litestar dependency injection parameters from a `FilterConfig` mapping:

```python
from litestar import get
from litestar.di import NamedDependency
from litestar.params import SkipValidation
from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.core import FilterTypes, OffsetPagination
from sqlspec.extensions.litestar.providers import create_filter_dependencies
from sqlspec.service import SQLSpecAsyncService

filter_deps = create_filter_dependencies(
    {
        "pagination_type": "limit_offset",
        "pagination_size": 20,
        "sort_field": "created_at",
        "sort_order": "desc",
        "search": "name,email",
        "search_ignore_case": True,
    }
)


@get("/users", dependencies=filter_deps)
async def list_users(
    db_session: NamedDependency[AsyncpgDriver],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[User]:
    service = SQLSpecAsyncService(db_session)
    return await service.paginate(
        sql.select("*").from_("users"),
        *filters,
        schema_type=User,
    )
```

Query parameters are automatically extracted from the request:

- `?currentPage=2&pageSize=20` for `LimitOffsetFilter`
- `?orderBy=name&sortOrder=asc` for `OrderByFilter`
- `?searchString=alice&searchIgnoreCase=true` for `SearchFilter`
- `?createdBefore=2025-12-31&createdAfter=2025-01-01` when `created_at=True`
- `?ids=<value>` for the configured ID collection filter
