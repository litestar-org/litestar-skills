# SQLSpec service layer — canonical patterns

This file is the deep reference for building service classes on top of SQLSpec in a Litestar application. For a lightweight overview of the patterns, see [`patterns.md`](patterns.md). For the full filter type catalogue and composition rules, see [`filters.md`](filters.md). This file covers the `SQLSpecAsyncService` base class, named SQL templates, direct driver usage, variadic filter composition, and DI wiring through Litestar's filter dependencies helper.

## The `SQLSpecAsyncService` and `SQLSpecSyncService` bases

`SQLSpecAsyncService` and `SQLSpecSyncService` are compiled upstream service bases in `sqlspec.service` (`@mypyc_attr(allow_interpreted_subclasses=True)`, supporting slotted subclasses). Each service can be constructed in one of two mutually exclusive modes:

1. **Session-backed (`SQLSpecAsyncService(driver)`)** — holds an already-open driver session injected per request.
2. **Config-backed (`SQLSpecAsyncService(config=db_config, loader=loader)`)** — holds a `DatabaseConfig` (and optional `SQLFileLoader`) and opens short-lived connections per operation via `self.provide_session()`, preventing connection pool starvation across slow or multi-step workflows.

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
from sqlspec.adapters.duckdb import DuckDBConfig, DuckDBDriver
from sqlspec.loader import SQLFileLoader
from sqlspec.service import SQLSpecAsyncService, SQLSpecSyncService


class AsyncpgLoaderService(SQLSpecAsyncService[AsyncpgDriver]):
    def __init__(self, config: AsyncpgConfig, loader: SQLFileLoader) -> None:
        super().__init__(config=config, loader=loader)


class DuckDBLoaderService(SQLSpecSyncService[DuckDBDriver]):
    def __init__(self, config: DuckDBConfig, loader: SQLFileLoader) -> None:
        super().__init__(config=config, loader=loader)
```

### Core methods

| Method | Signature sketch | Purpose |
| --- | --- | --- |
| `provide_session` | `(session=None) -> AsyncContextManager[DriverT]` | Yields an explicit `session`, the active transaction session, the bound `self.driver`, or a fresh `config.provide_session()` |
| `paginate` | `(stmt, /, *filters, schema_type=None, session=None, **kw) -> Pagination[T]` | Dispatches to `paginate_cursor` when a `CursorFilter` is present, otherwise `paginate_limit_offset` |
| `paginate_limit_offset` | `(stmt, /, *filters, schema_type=None, session=None, **kw) -> OffsetPagination[T]` | Runs `select_with_total` and extracts `LimitOffsetFilter` |
| `paginate_cursor` | `(stmt, /, *filters, schema_type=None, session=None, **kw) -> CursorPagination[T]` | Keyset pagination using `CursorFilter` and `OrderByFilter` (`limit + 1` lookahead, signed/encoded `next_cursor`) |
| `get_one` | `(stmt, /, *parameters, schema_type=..., error_message=..., session=None) -> T` | Single-row lookup; raises `NotFoundError` if not found |
| `exists` | `(stmt, /, *parameters, session=None, **kw) -> bool` | Returns `True` if any row matches |
| `begin_transaction` | `(session=None) -> AsyncContextManager[DriverT]` | Commits on clean exit and rolls back on error; nested `begin_transaction()` calls automatically use a savepoint on the outer session |
| `begin / commit / rollback` | `(session=None)` | Low-level transaction control for manual management |

### Subclassing: Session-Backed vs Config-Backed

For request-scoped session injection:

```python
from sqlspec.driver import AsyncDriverAdapterBase
from sqlspec.service import SQLSpecAsyncService


class OrderService(SQLSpecAsyncService):
    def __init__(self, driver: AsyncDriverAdapterBase) -> None:
        super().__init__(driver)
```

For config-backed services that acquire a connection only for the duration of a query or transaction (preventing pool starvation during slow I/O such as Argon2 password hashing, object-store uploads, or LLM streaming):

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlspec import StatementStack
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
from sqlspec.loader import SQLFileLoader
from sqlspec.service import SQLSpecAsyncService

from app.schemas import Order


class AsyncpgService(SQLSpecAsyncService[AsyncpgDriver]):
    def __init__(self, app_db: AsyncpgConfig, loader: SQLFileLoader | None = None) -> None:
        super().__init__(config=app_db, loader=loader)

    @asynccontextmanager
    async def provide_app_session(self, session: AsyncpgDriver | None = None) -> AsyncIterator[AsyncpgDriver]:
        async with self.provide_session(session) as driver:
            yield driver


class AsyncpgLoaderService(AsyncpgService):
    def __init__(self, app_db: AsyncpgConfig, loader: SQLFileLoader) -> None:
        super().__init__(app_db=app_db, loader=loader)
        self._loader = loader


class OrderService(AsyncpgLoaderService):
    async def get_order(self, order_id: str) -> Order:
        return await self.get_one(
            self._loader.get_sql("get-order"),
            order_id=order_id,
            schema_type=Order,
            error_message=f"Order {order_id} not found",
        )

    async def import_order_bundle(self, order_id: str, raw_bytes: bytes, items: list[tuple[str, int]]) -> None:
        checksum = await compute_digest_and_upload_to_object_store(order_id, raw_bytes)
        stack = (
            StatementStack()
            .push_execute(self._loader.get_sql("upsert-order-checksum"), order_id=order_id, checksum=checksum)
            .push_execute_many(self._loader.get_sql("insert-order-item"), items)
        )
        async with self.provide_session() as session, session.transaction():
            await session.execute_stack(stack)
```

Key rules for config-backed services:

- **Never hold a DB session across slow I/O**: perform Argon2 hashing, external HTTP calls, object-store transfers, or LLM streaming *outside* `provide_session()`, then acquire a short-lived session and open `session.transaction()` (or `self.begin_transaction()`) only for the SQL statements.
- **Batch multi-statement writes with `StatementStack`**: combine `push_execute` and `push_execute_many` inside a single `session.transaction()` block to minimize round-trips and hold the connection for milliseconds.
- **Use `self._loader.get_sql(...)` over module-global `db_manager.get_sql(...)`**: injecting `SQLFileLoader` at `Scope.APP` keeps services testable with isolated SQL loaders.

## `db_manager.get_sql()` + named SQL templates

SQLSpec supports loading SQL files from a directory tree with `db_manager.load_sql_files(...)` (or a dedicated `SQLFileLoader`) and referencing them later by kebab-case key. Pass `**slots` to `get_sql(name, **slots)` when a query declares `/* slot: <name> */` placeholders. This keeps SQL out of Python source files and enables `sqlglot`-based validation at load time — the loaded statements are parsed and dialect-checked before the app starts serving traffic.

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

dependencies = create_filter_dependencies(
    {
        "id_filter": UUID,
        "search": "name,reference",
        "pagination_type": "limit_offset",
        "pagination_size": 20,
        "created_at": True,
        "updated_at": True,
        "sort_field": "created_at",
        "sort_order": "desc",
    }
)
```

### Handler signature — Dishka + Inject pattern

```python
from dishka.integrations.litestar import FromDishka as Inject, inject
from litestar import get
from litestar.di import NamedDependency
from litestar.params import SkipValidation
from sqlspec.core import OffsetPagination
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
from litestar.params import SkipValidation
from sqlspec.adapters.asyncpg import AsyncpgDriver
from sqlspec.core import OffsetPagination
from sqlspec.core.filters import FilterTypes

from app.domains.orders.services import OrderService
from app.schemas import Order


def provide_order_service(
    db_session: NamedDependency[AsyncpgDriver],
) -> OrderService:
    return OrderService(db_session)


@get(
    "/orders",
    dependencies={
        **dependencies,
        "orders_service": Provide(provide_order_service),
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

Enable the Litestar extension in your SQLSpec config to activate session management, lifespan pool teardown, and DI integration:

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
            "manage_lifespan": True,
        },
    },
)
db_manager.add_config(config)
```

`include_extensions: ["litestar"]` explicitly includes the Litestar session migration in SQLSpec's native migration runner. An enabled `extension_config["litestar"]` block also auto-includes its extension migration unless it is excluded.

`disable_di: True` with `manage_lifespan: True` — when using Dishka or config-backed services instead of SQLSpec's built-in Litestar DI providers, set `disable_di: True` to skip duplicate per-request session/connection dependency registration while keeping `manage_lifespan: True` so `SQLSpecPlugin` still registers the application lifespan hook that closes pools on shutdown (when `manage_lifespan` is omitted, it defaults to `not disable_di`). See [`dishka-integration.md`](dishka-integration.md) for provider setup.

## Cross-references

- [`filters.md`](filters.md) — full filter type catalogue, `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`, `InCollectionFilter`
- [`patterns.md`](patterns.md) — lightweight service layer overview, batch operations, upsert patterns
- [`observability.md`](observability.md) — `ObservabilityConfig`, `StatementObserver`, SQL-level event broadcasting
- [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md) — ORM path decision guide; `advanced_alchemy.extensions.litestar` filter deps

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
