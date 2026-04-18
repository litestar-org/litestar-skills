# Dishka + sqlspec integration

Dishka is an explicit-scope DI framework for Python that gives you precise control over provider lifecycle — `Scope.APP` for process-lifetime singletons, `Scope.REQUEST` for per-request resources, and `Scope.SESSION` for WebSocket connections. When combined with SQLSpec, Dishka manages the `AsyncDriverAdapterBase` session lifecycle in a `LitestarPersistenceProvider`, injects domain services via a `DomainServiceProvider`, and keeps long-lived backends (e.g. `ChannelsBackend`) in an `AppSingletonsProvider`.

**When to use Dishka vs Litestar's built-in `Provide`:**

- **Use `Provide`** (Litestar's default) for simple apps with a handful of injected services, no cross-request singletons, and no WebSocket session scope. It's zero-dep and composable with Litestar's controller-level `dependencies` dict. See [`../../litestar/references/di.md`](../../litestar/references/di.md) for the full guide.
- **Use Dishka** when you need explicit scope control (APP vs REQUEST vs SESSION), multiple provider classes with lifecycle hooks, or the same provider graph across Litestar and background workers (SAQ, Celery). Dishka also makes provider graphs testable in isolation via `make_async_container`.

## Provider overview — 3 providers, 3 scopes

### `DomainServiceProvider` — `Scope.REQUEST`

Provides domain service instances. Each `@provide` method declares a service that receives an `AsyncDriverAdapterBase` (itself provided by `LitestarPersistenceProvider`). The `scope = Scope.REQUEST` class-level attribute applies to all `@provide` methods that don't override it.

```python
from dishka import Provider, Scope, provide
from sqlspec.driver import AsyncDriverAdapterBase

from app.domains.orders.services import OrderService
from app.domains.posts.services import PostService
from app.domains.notifications.services import NotificationService


class DomainServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def provide_order_service(self, driver: AsyncDriverAdapterBase) -> OrderService:
        return OrderService(driver)

    @provide
    def provide_post_service(self, driver: AsyncDriverAdapterBase) -> PostService:
        return PostService(driver)

    @provide
    def provide_notification_service(
        self, driver: AsyncDriverAdapterBase
    ) -> NotificationService:
        return NotificationService(driver)
```

Note: no `from __future__ import annotations` — Dishka inspects `@provide` method signatures at runtime to resolve dependencies. The future-annotations import defers evaluation and breaks introspection.

### `LitestarPersistenceProvider` — `Scope.REQUEST`

Yields an `AsyncDriverAdapterBase` from the SQLSpec connection pool. The `async with db_manager.provide_session(db)` context manager opens a connection at the start of the request and releases it on exit (commit or rollback). Adapted from [litestar-sqlstack](https://github.com/cofin/litestar-sqlstack) (`src/sqlstack/ioc.py:L107–125`).

```python
from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlspec.driver import AsyncDriverAdapterBase

from app.lib.db import db, db_manager


class LitestarPersistenceProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_driver(self) -> AsyncIterator[AsyncDriverAdapterBase]:
        async with db_manager.provide_session(db) as driver:
            yield driver
```

### `AppSingletonsProvider` — `Scope.APP`

Provides process-lifetime singletons — things that are initialized once and shared across all requests. The `ChannelsBackend` is the most common: it's a long-lived client that maintains connections to the pub/sub backend. Pull it from `app.channels` (the Litestar `ChannelsPlugin` instance) so it's already initialized by the time handlers need it.

```python
from dishka import Provider, Scope, provide
from litestar import Litestar
from litestar_channels.backends.base import ChannelsBackend


class AppSingletonsProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_channels_backend(self, app: Litestar) -> ChannelsBackend:
        return app.channels._backend  # noqa: SLF001
```

## `FromDishka as Inject` alias

The standard alias for injecting Dishka-managed dependencies into Litestar handlers. Both canonical apps use this alias consistently:

```python
from dishka.integrations.litestar import FromDishka as Inject
```

Cited from `litestar-sqlstack/src/sqlstack/lib/di.py:L42`.

Import this alias once in a `app/lib/di.py` re-export module and use `Inject[SomeService]` in all handler signatures:

```python
# app/lib/di.py
from dishka.integrations.litestar import FromDishka as Inject, inject

__all__ = ["Inject", "inject"]
```

## Scope discipline

| Scope | Use this for | Lifetime |
| --- | --- | --- |
| `Scope.REQUEST` | DB sessions, domain services, anything tied to one HTTP request | Created at request start, released at response end |
| `Scope.APP` | `ChannelsBackend`, long-lived clients, config objects, caches | Created at app startup, lives until process exit |
| `Scope.SESSION` | WebSocket connections — Dishka manages a child container per WS session | Created at `ws.accept()`, released at `ws.close()` |

`Scope.SESSION` is managed internally by Dishka's `with_websocket_request` context manager — you typically don't register `Scope.SESSION` providers manually. See [`../../litestar/references/websockets.md`](../../litestar/references/websockets.md) §Dishka DI in WS handlers for details.

## Full provider example

Three-provider setup for a neutral-domain app with orders, posts, and notifications (adapted from `litestar-sqlstack/src/sqlstack/ioc.py:L74–149`):

```python
from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.litestar import FromDishka as Inject, setup_dishka
from litestar import Litestar
from litestar_channels.backends.base import ChannelsBackend
from sqlspec.driver import AsyncDriverAdapterBase

from app.domains.orders.services import OrderService
from app.domains.posts.services import PostService
from app.domains.notifications.services import NotificationService
from app.lib.db import db, db_manager


class DomainServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def provide_order_service(self, driver: AsyncDriverAdapterBase) -> OrderService:
        return OrderService(driver)

    @provide
    def provide_post_service(self, driver: AsyncDriverAdapterBase) -> PostService:
        return PostService(driver)

    @provide
    def provide_notification_service(
        self, driver: AsyncDriverAdapterBase
    ) -> NotificationService:
        return NotificationService(driver)


class LitestarPersistenceProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_driver(self) -> AsyncIterator[AsyncDriverAdapterBase]:
        async with db_manager.provide_session(db) as driver:
            yield driver


class AppSingletonsProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_channels_backend(self, app: Litestar) -> ChannelsBackend:
        return app.channels._backend  # noqa: SLF001
```

## Handler injection pattern

Handlers declare injected services via `Inject[ServiceType]` and receive filter lists via `Dependency(skip_validation=True)`. The `@inject` decorator (from `dishka.integrations.litestar`) activates resolution. Adapted from `litestar-sqlstack/src/sqlstack/domain/accounts/controllers/_user.py:L26–53`.

```python
from dishka.integrations.litestar import inject
from litestar import get
from litestar.pagination import OffsetPagination
from litestar.params import Dependency
from sqlspec.core.filters import FilterTypes
from sqlspec.extensions.litestar.providers import create_filter_dependencies
from typing import Annotated
from uuid import UUID

from app.domains.orders.services import OrderService
from app.lib.di import Inject
from app.schemas import Order

dependencies = create_filter_dependencies({
    "id_filter": UUID,
    "search": "reference,status",
    "pagination_type": "limit_offset",
    "pagination_size": 20,
    "created_at": True,
    "updated_at": True,
    "sort_field": "created_at",
    "sort_order": "desc",
})


@get("/orders", dependencies=dependencies, operation_id="ListOrders")
@inject
async def list_orders(
    orders_service: Inject[OrderService],
    filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
) -> OffsetPagination[Order]:
    return await orders_service.list_orders(*filters)
```

## Wiring into Litestar

Build the container from your providers and wire it into the Litestar app via `setup_dishka`. The container is created once at startup and shared across all requests.

```python
from dishka import make_async_container
from dishka.integrations.litestar import setup_dishka
from litestar import Litestar

from app.ioc import AppSingletonsProvider, DomainServiceProvider, LitestarPersistenceProvider


def create_app() -> Litestar:
    container = make_async_container(
        DomainServiceProvider(),
        LitestarPersistenceProvider(),
        AppSingletonsProvider(),
    )
    app = Litestar(route_handlers=[...])
    setup_dishka(container, app)
    return app
```

`setup_dishka` registers a Litestar lifespan hook that calls `container.close()` on shutdown, ensuring all APP-scope providers run their cleanup logic.

## When Dishka is overkill

Dishka's explicit scope control is most valuable when you have multiple provider classes, APP-scoped singletons, and WebSocket SESSION scope in the same app. For simpler setups — a handful of handlers, one DB pool, no pub/sub backend — Litestar's built-in `Provide` is the lighter choice. It requires no extra dependency, composes naturally with controller-level `dependencies` dicts, and keeps the DI graph implicit rather than explicit. See [`../../litestar/references/di.md`](../../litestar/references/di.md) for the full `Provide` reference.

## Cross-references

- [`service-patterns.md`](service-patterns.md) — `SQLSpecAsyncService` base, `db_manager.get_sql`, variadic `*filters`, `create_filter_dependencies()`
- [`observability.md`](observability.md) — `ObservabilityConfig`, `StatementObserver`, SQL-level event broadcasting
- [`../../litestar/references/di.md`](../../litestar/references/di.md) — Litestar built-in `Provide`; when to use it vs Dishka
- [`../../litestar/references/websockets.md`](../../litestar/references/websockets.md) — `with_websocket_request`, Dishka `Scope.SESSION` in WS handlers

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
