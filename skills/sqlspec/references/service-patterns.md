# SQLSpec service layer — canonical patterns

This file is the deep reference for building service classes on top of SQLSpec in a Litestar application. For a lightweight overview of the patterns, see [`patterns.md`](patterns.md). For the full filter type catalogue and composition rules, see [`filters.md`](filters.md). This file covers the `SQLSpecAsyncService` base class, named SQL templates, direct driver usage, variadic filter composition, and DI wiring through Litestar's filter dependencies helper.

## The `SQLSpecAsyncService` base

`SQLSpecAsyncService` is an upstream service base in `sqlspec.service`. It holds a driver session injected by the DI container and exposes methods for pagination, single-row lookups, existence checks, and transaction control.

```python
from sqlspec.service import SQLSpecAsyncService


class OrderService(SQLSpecAsyncService):
    pass
```

### Core methods

| Method | Signature sketch | Purpose |
| --- | --- | --- |
| `paginate` | `(stmt, /, *filters, schema_type=None, **kw) -> OffsetPagination[T]` | Runs `select_with_total`, extracts `LimitOffsetFilter` from `*filters` |
| `get_one` | `(stmt, /, *parameters, schema_type=..., error_message=...) -> T` | Single-row lookup; raises `NotFoundError` if not found |
| `exists` | `(stmt, *parameters) -> bool` | Returns `True` if any row matches |
| `begin_transaction` | `() -> AsyncContextManager` | Wraps driver `begin/commit/rollback` in an async context manager |
| `begin / commit / rollback` | — | Low-level transaction control for manual management |

`paginate` calls `session.select_with_total(stmt, *filters, schema_type=schema_type)` and extracts `LimitOffsetFilter` from the passed filters for the `OffsetPagination` result.

### Subclassing

Extend `SQLSpecAsyncService` for each domain entity:

```python
from sqlspec.driver import AsyncDriverAdapterBase
from sqlspec.service import SQLSpecAsyncService

from app.schemas import Order


class OrderService(SQLSpecAsyncService):
    def __init__(self, driver: AsyncDriverAdapterBase) -> None:
        super().__init__(driver)
```

## `db_manager.get_sql()` + named SQL templates

SQLSpec supports loading SQL files from a directory tree with `dbm.load_sql_files(...)` and referencing them later by kebab-case key. This keeps SQL out of Python source files and enables `sqlglot`-based validation at load time — the loaded statements are parsed and dialect-checked before the app starts serving traffic.

Canonical usage pattern (adapted from `litestar-sqlstack/src/sqlstack/domain/accounts/services/_user.py:L33, L45–46, L65–66`):

```python  # pragma: legacy-example
from app.lib.db import db_manager
from app.schemas import Order
from sqlspec.driver import AsyncDriverAdapterBase
from sqlspec.service import SQLSpecAsyncService


class OrderService(SQLSpecAsyncService):
    def __init__(self, driver: AsyncDriverAdapterBase) -> None:
        super().__init__(driver)

    async def create_order(self, payload: dict) -> Order:
        return await self.driver.select_one(
            db_manager.get_sql("create-order"),
            schema_type=Order,
            **payload,
        )

    async def get_order(self, order_id: str) -> Order:
        return await self.get_one(
            db_manager.get_sql("get-order"),
            order_id=order_id,
            schema_type=Order,
            error_message=f"Order {order_id} not found",
        )
```

The `get_sql` key (`"create-order"`, `"get-order"`) maps to a SQL file discovered by `load_sql_files`. Keys are derived from the filename (minus the `.sql` extension, with slashes replaced by dashes).

## Direct driver API — `select_value` / `select_one` / `execute`

Use the driver methods directly when the base class helpers don't fit:

- **`select_value`** — scalar reads: `COUNT(*)`, `MAX(id)`, boolean existence checks (`SELECT EXISTS(...)`). Returns the single cell value, raises if no row.
- **`select_one`** — single mapped row. Raises `NotFoundError` if the query returns no rows. Use `select_one_or_none` when absence is valid.
- **`execute`** — mutations returning no rows or only a row count: `INSERT`, `UPDATE`, `DELETE` without `RETURNING`.

Decision table:

| You want | Use |
| --- | --- |
| A count or single cell | `select_value` |
| One mapped object, must exist | `select_one` / `get_one` |
| One mapped object, may be absent | `select_one_or_none` |
| List of rows | `select()` (via driver) or `paginate` (via service) |
| INSERT/UPDATE/DELETE (no return) | `execute` |

Example method combining `get_one` with a named template:

```python
async def get_order(self, order_id: str) -> Order:
    return await self.get_one(
        db_manager.get_sql("get-order"),
        order_id=order_id,
        schema_type=Order,
        error_message=f"Order {order_id} not found",
    )
```

Example scalar check using `select_value`:

```python
async def order_exists(self, order_id: str) -> bool:
    result = await self.driver.select_value(
        db_manager.get_sql("order-exists"),
        order_id=order_id,
    )
    return bool(result)
```

## Variadic filter composition — `*filters`

Service methods accept `*filters: StatementFilter` and forward them to `driver.select_with_total(...)` or the inherited `paginate()`. Filters are composable — the driver applies them in order. The `LimitOffsetFilter` controls pagination; `OrderByFilter` sets the sort; `SearchFilter` adds an `ILIKE` clause.

List method with full filter forwarding:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlspec.core.filters import FilterTypes

async def list_orders(self, *filters: "FilterTypes") -> "OffsetPagination[Order]":
    return await self.paginate(
        db_manager.get_sql("list-orders"),
        *filters,
        schema_type=Order,
    )
```

Count + list together (adapted from `litestar-sqlstack/src/sqlstack/domain/accounts/services/_user.py:L70`):

```python
async def list_with_count(self, *filters: "FilterTypes") -> tuple[list[Order], int]:
    return await self.driver.select_with_total(
        db_manager.get_sql("list-orders"),
        *filters,
        schema_type=Order,
    )
```

Filters are passed as positional args between the SQL statement and any keyword parameters. Order does not matter between filter objects — SQLSpec resolves them by type.

## `create_filter_dependencies()` — wiring filters into Litestar DI

`create_filter_dependencies` from `sqlspec.extensions.litestar.providers` generates a Litestar `dependencies` dict that injects composable filter objects into route handlers automatically. Handlers receive the assembled `list[FilterTypes]` via `NamedDependency[SkipValidation[list[FilterTypes]]]` (Litestar ≥ 2.24; replaces implicit DI and the deprecated `Dependency(skip_validation=True)`).

```python
from sqlspec.extensions.litestar.providers import create_filter_dependencies
```

Full config example (adapted from `litestar-sqlstack/src/sqlstack/domain/accounts/controllers/_user.py:L10, L26–35`):

```python
from litestar import get
from sqlspec.extensions.litestar.providers import create_filter_dependencies
from uuid import UUID

from app.schemas import Order

dependencies = create_filter_dependencies({
    "id_filter": UUID,
    "search": "name,reference",
    "pagination_type": "limit_offset",
    "pagination_size": 20,
    "created_at": True,
    "updated_at": True,
    "sort_field": "created_at",
    "sort_order": "desc",
})
```

### Handler signature — Dishka + Inject pattern

```python
from dishka.integrations.litestar import FromDishka as Inject, inject
from litestar import get
from litestar.di import NamedDependency
from litestar.pagination import OffsetPagination
from litestar.params import SkipValidation  # Litestar >= 2.23
from sqlspec.core.filters import FilterTypes

from app.domains.orders.services import OrderService
from app.schemas import Order


@get("/orders", dependencies=dependencies)
@inject
async def list_orders(
    orders_service: Inject[OrderService],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[Order]:
    return await orders_service.list_orders(*filters)
```

### Handler signature — plain `Provide` pattern

```python
from litestar import get
from litestar.di import NamedDependency, Provide
from litestar.pagination import OffsetPagination
from litestar.params import SkipValidation  # Litestar >= 2.23
from sqlspec.core.filters import FilterTypes

from app.domains.orders.services import OrderService
from app.schemas import Order


@get(
    "/orders",
    dependencies={
        **dependencies,
        "orders_service": Provide(lambda driver: OrderService(driver)),
    },
)
async def list_orders(
    orders_service: NamedDependency[OrderService],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[Order]:
    return await orders_service.list_orders(*filters)
```

**Match-your-stack note:** `create_filter_dependencies` is the SQLSpec version. Advanced-Alchemy's equivalent lives at `advanced_alchemy.extensions.litestar` and has a different kwarg surface (different key names, different filter types). See [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md) for the ORM path.

## SQLSpec Litestar extension registration

Enable the Litestar extension in your SQLSpec config to activate session management and DI integration:

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig

db_manager = SQLSpec()
config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://localhost/app"},
    migration_config={
        "version_table_name": "db_version",
        "script_location": "migrations",
        "project_root": BASE_DIR,
        "include_extensions": ["litestar"],
    },
    extension_config={
        "litestar": {
            "session_table": "app_session",
            "disable_di": True,
        },
    },
)
db_manager.add_config(config)
```

`include_extensions: ["litestar"]` activates the Litestar extension in the migration pipeline — Alembic will include session-table migrations automatically. (Cited from `litestar-sqlstack/src/sqlstack/lib/settings.py:L148`.)

`disable_di: True` — when using Dishka as the DI container, set this to prevent SQLSpec's built-in Litestar DI registration from conflicting with the Dishka provider. Handlers receive the `AsyncDriverAdapterBase` via the `LitestarPersistenceProvider` instead. See [`dishka-integration.md`](dishka-integration.md) for provider setup.

## Cross-references

- [`filters.md`](filters.md) — full filter type catalogue, `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `InCollectionFilter`
- [`patterns.md`](patterns.md) — lightweight service layer overview, batch operations, upsert patterns
- [`observability.md`](observability.md) — `ObservabilityConfig`, `StatementObserver`, SQL-level event broadcasting
- [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md) — ORM path decision guide; `advanced_alchemy.extensions.litestar` filter deps

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
