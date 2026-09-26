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

### CursorFilter & CursorKey

Keyset (cursor) pagination using opaque URL-safe cursor tokens (with optional HMAC-SHA256 signing via `secret`):

```python
from sqlspec.core import CursorFilter, CursorKey, normalize_cursor_keys

keys = normalize_cursor_keys([CursorKey("created_at", sort_order="desc"), "id"])
filter_ = CursorFilter(
    cursor=request_cursor_token,
    limit=25,
    keys=keys,
    secret=cursor_secret,
)
```

The final key in `keys` must uniquely identify each row (for example `"id"`) so ties in earlier sort columns remain deterministic. Invalid or tampered cursor tokens raise `InvalidCursorError` (which Litestar / FastAPI providers map to HTTP 400).

### OrderByFilter

Dynamic column ordering with optional `nulls` placement (`"first"` or `"last"`):

```python
from sqlspec.core.filters import OrderByFilter

filter_ = OrderByFilter(field_name="created_at", sort_order="desc", nulls="last")
```

### SearchFilter & NotInSearchFilter

Text search (or negated text search) across one or more columns:

```python
from sqlspec.core.filters import NotInSearchFilter, SearchFilter

search_ = SearchFilter(
    field_name={"name", "email"},
    value="alice",
    ignore_case=True,
)
exclude_ = NotInSearchFilter(
    field_name="email",
    value="spam.example",
    ignore_case=True,
)
```

### BeforeAfterFilter & OnBeforeAfterFilter

Exclusive (`<` / `>`) or inclusive (`<=` / `>=`) date/time range filtering:

```python
from datetime import datetime
from sqlspec.core.filters import BeforeAfterFilter, OnBeforeAfterFilter

exclusive_range = BeforeAfterFilter(
    field_name="created_at",
    before=datetime(2025, 12, 31),
    after=datetime(2025, 1, 1),
)
inclusive_range = OnBeforeAfterFilter(
    field_name="created_at",
    on_or_before=datetime(2025, 12, 31),
    on_or_after=datetime(2025, 1, 1),
)
```

### Collection, Null, Boolean, and Choices Filters

Filter rows by collection membership (`IN`, `NOT IN`, `= ANY(...)`, `<> ANY(...)`), nullability, boolean state, or an allowed set of choices:

```python
from sqlspec.core.filters import (
    AnyCollectionFilter,
    BooleanFilter,
    ChoicesFilter,
    InCollectionFilter,
    NotAnyCollectionFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
)

in_filter = InCollectionFilter(field_name="status", values=["active", "pending"])
not_in_filter = NotInCollectionFilter(field_name="status", values=["deleted"])
any_filter = AnyCollectionFilter(field_name="tag_id", values=[10, 20, 30])
not_any_filter = NotAnyCollectionFilter(field_name="tag_id", values=[99])
null_filter = NullFilter(field_name="archived_at")
not_null_filter = NotNullFilter(field_name="verified_at")
bool_filter = BooleanFilter(field_name="is_active", value=True)
choice_filter = ChoicesFilter(field_name="tier", values=("free", "pro", "enterprise"))
```

---

## Pagination Result Types (`OffsetPagination` & `CursorPagination`)

`SQLSpecAsyncService.paginate()` / `SQLSpecSyncService.paginate()` return `Pagination[T]` (`OffsetPagination[T] | CursorPagination[T]`):

- **`OffsetPagination[T]`** (returned by `paginate_limit_offset()` or `paginate()` with `LimitOffsetFilter`):
  - `result.items`: `list[T]` - current page rows
  - `result.total`: `int` - total matching rows
  - `result.limit`: `int` - page size
  - `result.offset`: `int` - current offset
- **`CursorPagination[T]`** (returned by `paginate_cursor()` or `paginate()` when a `CursorFilter` is present):
  - `result.items`: `Sequence[T]` - current page rows
  - `result.limit`: `int` - page size
  - `result.next_cursor`: `str | None` - opaque cursor token for the next page (`None` on the last page)
  - `result.previous_cursor`: `str | None` - opaque cursor token for the previous page (`None` on the first page)
  - `result.has_next`: `bool` - whether a page exists after `items`
  - `result.has_previous`: `bool` - whether a page exists before `items`

```python
from sqlspec.core import CursorPagination, OffsetPagination, Pagination

offset_page: OffsetPagination[User]
cursor_page: CursorPagination[User]
any_page: Pagination[User]
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

## Litestar & FastAPI Filter Dependencies

Use `create_filter_dependencies()` from `sqlspec.extensions.litestar.providers` (or `db_plugin.provide_filters()` in FastAPI) to generate dependency injection parameters from a `FilterConfig` mapping:

```python
from litestar import get
from litestar.di import NamedDependency
from litestar.params import SkipValidation
from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.core import CursorKey, CursorPagination, FilterTypes, OffsetPagination
from sqlspec.extensions.litestar.providers import ChoiceField, FieldNameType, create_filter_dependencies
from sqlspec.service import SQLSpecAsyncService

offset_filter_deps = create_filter_dependencies(
    {
        "pagination_type": "limit_offset",
        "pagination_size": 20,
        "pagination_max_size": 200,
        "sort_field": {"created_at", "name"},
        "sort_field_aliases": {"created": "created_at"},
        "sort_field_camelize": True,
        "sort_order": "desc",
        "search": "name,email",
        "search_ignore_case": True,
        "boolean_fields": ["is_active"],
        "choice_fields": [ChoiceField("tier", ("free", "pro", "enterprise"))],
        "in_fields": [FieldNameType("status", str)],
    }
)

cursor_filter_deps = create_filter_dependencies(
    {
        "pagination_type": "cursor",
        "cursor_keys": [CursorKey("created_at", sort_order="desc"), "id"],
        "cursor_secret": "app-cursor-signing-secret",
        "pagination_size": 25,
        "pagination_max_size": 100,
        "search": "name,email",
        "search_ignore_case": True,
    }
)


@get("/users", dependencies=offset_filter_deps)
async def list_users(
    db_session: NamedDependency[AsyncpgDriver],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[User]:
    service = SQLSpecAsyncService(db_session)
    return await service.paginate_limit_offset(
        sql.select("*").from_("users"),
        *filters,
        schema_type=User,
    )


@get("/users/stream-page", dependencies=cursor_filter_deps)
async def list_users_cursor(
    db_session: NamedDependency[AsyncpgDriver],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> CursorPagination[User]:
    service = SQLSpecAsyncService(db_session)
    return await service.paginate_cursor(
        sql.select("*").from_("users"),
        *filters,
        schema_type=User,
    )
```

Query parameters are automatically extracted and bounded by the provider:

- `?currentPage=2&pageSize=20` for `LimitOffsetFilter` (`pageSize` is capped by `pagination_max_size`, default `1000`)
- `?cursor=<token>&pageSize=25` for `CursorFilter`
- `?orderBy=name&sortOrder=asc` for `OrderByFilter` (supports `sort_field` allowlists, camelCase aliases when `sort_field_camelize=True`, and `sort_field_aliases`)
- `?searchString=alice&searchIgnoreCase=true` for `SearchFilter`
- `?createdBefore=2025-12-31&createdAfter=2025-01-01` when `created_at=True`
- `?ids=<value>` for the configured ID collection filter (`id_field` defaults to `"id"`)
