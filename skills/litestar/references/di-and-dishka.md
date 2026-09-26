# Dependency Injection — `Provide()`, `NamedDependency`, and Dishka

Two paths: built-in `Provide()` for small and medium apps, Dishka (`1.10.1`) for explicit multi-scope container management. Do not default to Dishka — it is a scaling choice, not a style choice.

## Litestar Built-in DI (`Provide()`)

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

from litestar import Litestar, Request
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide
from sqlalchemy.ext.asyncio import AsyncSession


async def provide_db_session(state: State) -> AsyncGenerator[AsyncSession, None]:
    async with state.session_maker() as session:
        yield session


async def provide_current_user(
    request: Request,
    db_session: NamedDependency[AsyncSession],
) -> User:
    token = request.headers.get("Authorization")
    return await authenticate(db_session, token)


async def provide_user_service(
    db_session: NamedDependency[AsyncSession],
) -> UserService:
    return UserService(session=db_session)


app = Litestar(
    route_handlers=[...],
    dependencies={
        "db_session": Provide(provide_db_session),
        "current_user": Provide(provide_current_user),
        "users_service": Provide(provide_user_service),
    },
)
```

### `Provide` Signature & Execution Rules

`Provide(dependency: AnyCallable | type[Any], use_cache: bool = False, sync_to_thread: bool | None = None)` wraps functions, generators, classes, or callable instances:

| Provider Callable Type | `sync_to_thread` Rule | `use_cache` Rule |
| --- | --- | --- |
| `async def fn(...) -> T` | Leave `None` (setting `True`/`False` emits `LitestarWarning`) | `False` (per-request DAG) or `True` (app-lifetime singleton) |
| `def fn(...) -> T` or `class Cls` | **Required**: `True` (blocking I/O in worker thread) or `False` (non-blocking inline); `None` emits `LitestarWarning` | `False` or `True` |
| `async def gen(...) -> AsyncGenerator[T, None]` | Leave `None` (setting `True`/`False` emits `LitestarWarning`) | **Must be `False`** (`True` raises `ImproperlyConfiguredException`) |
| `def gen(...) -> Generator[T, None, None]` | Leave `None` (setting `True`/`False` emits `LitestarWarning`; cleanup runs via `ensure_async_callable`) | **Must be `False`** (`True` raises `ImproperlyConfiguredException`) |

- **Per-request DAG deduplication vs `use_cache=True`**:
  - Within a single request, `KwargsModel` builds a dependency DAG (`create_dependency_batches`), resolves independent dependencies in parallel batches via `anyio.create_task_group()`, and stores each resolved key in `kwargs[key]`. If both `provide_current_user` and `provide_user_service` depend on `db_session: NamedDependency[AsyncSession]`, `provide_db_session` runs **once per request** even with `use_cache=False`.
  - Setting `use_cache=True` caches the first return value on `Provide.value` **across the entire application lifetime** (ignoring kwargs on subsequent calls). Never set `use_cache=True` on request-scoped resources (such as database sessions or request-derived objects) or the first request's instance will leak across all subsequent requests.

### Generator Dependencies & Cleanup (`DependencyCleanupGroup`)

Use sync or async generator functions (`yield`) when a dependency requires teardown after the route handler finishes:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def provide_transaction_session(
    session_maker: NamedDependency[async_sessionmaker[AsyncSession]],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- **Normal completion**: after the handler returns, `DependencyCleanupGroup` advances all active generators (`next` / `anext`). When multiple generators are active, cleanup runs concurrently in reverse registration order inside an `anyio.TaskGroup`.
- **Exception handling**: if the handler (or a downstream dependency) raises an exception, `DependencyCleanupGroup` throws the exception into each active generator via `gen.throw(exc)` / `await gen.athrow(exc)` sequentially. If cleanup raises additional exceptions, they are bundled into an `ExceptionGroup`.
- **No caching**: combining a generator provider with `use_cache=True` raises `ImproperlyConfiguredException("Cannot cache generator dependency, consider using Lifespan Context instead.")`.

### Layered Dependency Resolution (`Litestar -> Router -> Controller -> Handler`)

Dependencies can be declared at four ownership layers:

1. **`Litestar(dependencies={...})`** (application layer)
2. **`Router(dependencies={...})`** (router layer, supports nested routers)
3. **`Controller.dependencies = {...}`** (controller class attribute)
4. **`@get(..., dependencies={...})`** (route handler decorator)

Resolution rules:

- **Inner overrides outer**: `handler.resolve_dependencies()` merges dictionaries top-down (`Litestar -> Router -> Controller -> Handler`). A provider registered under the same key on an inner layer overrides the outer layer's provider for that handler.
- **Cross-layer sub-dependencies**: a provider at an inner layer (e.g. `Controller`) can depend on a provider from an outer layer (e.g. `Litestar`), as well as request parameters (`FromPath`, `FromQuery`, `FromHeader`, `FromCookie`) and reserved kwargs (`request`, `socket`, `state`, `scope`, `headers`, `cookies`, `query`, `data`, `body`).
- **Unique key per `Provide` instance**: registering the same `Provide` instance (or an equal `Provide` wrapping the same callable) under two *different* keys in the same ownership chain raises `ImproperlyConfiguredException`. To override a dependency at a lower layer, reuse the exact same key.
- **Disjoint names & `data` compatibility**: dependency keys cannot collide with path parameter names, aliased parameter names, or `RESERVED_KWARGS`. If both a dependency and the route handler consume `data`, their annotations and form encodings must match (`ImproperlyConfiguredException` otherwise).

## Typed Dependency Parameters (`NamedDependency` & `SkipValidation`)

Mark every parameter resolved from a Litestar `dependencies` map — both on route handlers and on sub-dependency functions — with `NamedDependency[T]` (from `litestar.di`). Use `NamedDependency[SkipValidation[T]]` (with `SkipValidation` from `litestar.params`) when the provider returns an arbitrary or third-party object that should bypass `SignatureModel` validation:

```python
from litestar.di import NamedDependency
from litestar.params import SkipValidation


async def list_users(
    users_service: NamedDependency[UserService],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[User]:
    rows, total = await users_service.get_many_and_count(*filters)
    return users_service.to_schema(rows, total, filters=filters, schema_type=User)
```

- **Why `SkipValidation[T]` matters**: Litestar validates all handler and provider parameters through `SignatureModel` (`msgspec.convert`). While client parameter validation errors return `400 ValidationException`, a validation failure on a dependency parameter raises `500 InternalServerException`. Wrapping arbitrary non-msgspec types or union filter lists in `SkipValidation[T]` treats their `SignatureModel` field as `Any` at runtime while preserving static typing for `mypy` and `pyright`.
- **Missing provider check at startup**: if a parameter is marked with `NamedDependency[T]` and no matching key exists in the handler's `Litestar -> Router -> Controller -> Handler` ownership layers, Litestar raises `ImproperlyConfiguredException` at app startup unless the parameter is optional (`T | None`) or defines a default value (`= default`).
- **Deprecations (2.23–2.24 -> 3.0)**:
  - `litestar.params.Dependency` and `DependencyKwarg` (including `Dependency(skip_validation=True)`) are deprecated since 2.23 and removed in 3.0.
  - Implicit name-matched dependency injection (omitting `NamedDependency[T]`) emits `LitestarDeprecationWarning` in 2.24 and is removed in 3.0.

## Dependency Replacement in Tests

Litestar has no mutable `app.dependency_overrides` registry. Construct a fresh app or test client with replacement `dependencies`:

```python
import pytest
from litestar import get
from litestar.di import NamedDependency, Provide
from litestar.testing import create_async_test_client


@get("/")
async def get_user(users_service: NamedDependency[UserService]) -> User:
    return await users_service.get_current()


async def provide_fake_users_service() -> UserService:
    return FakeUserService()


@pytest.mark.anyio
async def test_get_user() -> None:
    async with create_async_test_client(
        get_user,
        dependencies={
            "users_service": Provide(provide_fake_users_service),
        },
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
```

For full-application tests, make `create_app(dependencies: Dependencies | None = None)` accept overrides and construct a new `Litestar` instance per test.

## Dishka Integration (`dishka.integrations.litestar`, `dishka>=1.10.1`)

Use Dishka when the application needs explicit multi-scope lifetimes (`Scope.APP`, `Scope.SESSION`, `Scope.REQUEST`), modular `Provider` classes, or shared containers across HTTP, WebSockets, CLI, and worker processes.

### How `dishka.integrations.litestar` Works

`dishka.integrations.litestar` exports `setup_dishka`, `FromDishka` (commonly aliased `FromDishka as Inject`), `LitestarProvider`, `DishkaRouter`, `inject`, and `inject_websocket`:

1. **`setup_dishka(container, app)`** wraps `app.asgi_handler` with an outer ASGI middleware and sets `app.state.dishka_container = container`. For HTTP requests it enters `Scope.REQUEST` with `{Request: request}` context (`request.state.dishka_container`); for WebSocket connections it enters `Scope.SESSION` with `{WebSocket: socket}` context (`socket.state.dishka_container`).
2. **`LitestarProvider()`** registers `Request` (`Scope.REQUEST`) and `WebSocket` (`Scope.SESSION`) via `from_context` so Dishka `@provide` methods can request `request: Request` or `socket: WebSocket`.
3. **Handler injection requires `DishkaRouter` or `@inject` / `@inject_websocket`**: `setup_dishka` alone does **not** rewrite handler signatures. Every handler using `FromDishka[T]` must either be registered on a `DishkaRouter` (which automatically wraps HTTP handlers/Controllers with `inject` and `WebsocketListener`s with `inject_websocket`) or be explicitly decorated with `@inject` (HTTP) or `@inject_websocket` (WebSocket) **below** the Litestar route decorator.

### Pattern A — `DishkaRouter` with Controllers (Recommended)

```python
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.litestar import (
    DishkaRouter,
    FromDishka as Inject,
    LitestarProvider,
    setup_dishka,
)
from litestar import Controller, Litestar, Request, get
from litestar.params import FromPath
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AppProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_db_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    async def provide_user_service(
        self,
        db_session: AsyncSession,
        request: Request,
    ) -> UserService:
        return UserService(session=db_session, correlation_id=request.headers.get("X-Request-ID"))


class UserController(Controller):
    path = "/users"

    @get("/{user_id:uuid}")
    async def get_user(
        self,
        user_id: FromPath[UUID],
        users_service: Inject[UserService],
    ) -> User:
        return await users_service.get(user_id)


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    yield
    await app.state.dishka_container.close()


api_router = DishkaRouter(path="/api", route_handlers=[UserController])
container = make_async_container(AppProvider(), LitestarProvider())
app = Litestar(route_handlers=[api_router], lifespan=[lifespan])
setup_dishka(container=container, app=app)
```

When using [litestar-autowire](../../litestar-autowire/SKILL.md), `AutowireConfig(domain_packages=[...], integrations=["dishka"])` selects `DishkaRouter` automatically for discovered controllers.

### Pattern B — Explicit `@inject` Decorator on Standalone Handlers

When not using `DishkaRouter`, place `@inject` **below** `@get` / `@post` (closest to `async def`) so `@inject` strips `FromDishka[...]` parameters before Litestar builds its `SignatureModel`:

```python
from dishka.integrations.litestar import FromDishka as Inject, inject
from litestar import get
from litestar.params import FromPath


@get("/users/{user_id:uuid}")
@inject
async def get_user(
    user_id: FromPath[UUID],
    users_service: Inject[UserService],
) -> User:
    return await users_service.get(user_id)
```

### WebSocket Injection (`@inject_websocket` & `Scope.SESSION` -> `Scope.REQUEST`)

WebSocket connections span multiple messages, so Dishka maps the connection lifetime to `Scope.SESSION` (`APP -> SESSION -> REQUEST`):

- `@inject_websocket` (or `DishkaRouter` with `WebsocketListener`) resolves `Scope.APP` and `Scope.SESSION` dependencies directly via `FromDishka[T]`.
- To resolve `Scope.REQUEST` dependencies per incoming WebSocket message, inject `container: FromDishka[AsyncContainer]` (the `SESSION`-scoped container) and enter a child `Scope.REQUEST` context per message:

```python
from dishka import AsyncContainer
from dishka.integrations.litestar import FromDishka as Inject, inject_websocket
from litestar import websocket_listener


@websocket_listener("/ws/tasks")
@inject_websocket
async def task_ws_handler(
    data: dict[str, str],
    session_tracker: Inject[ConnectionTracker],  # Scope.SESSION
    container: Inject[AsyncContainer],  # SESSION-scoped container
) -> dict[str, str]:
    async with container() as request_container:  # enters Scope.REQUEST per message
        task_service = await request_container.get(TaskService)
        await task_service.process_event(data)
    return {"status": "processed"}
```

### Dishka 1.10.1 Notes & Gotchas

- **Runtime type hints (`get_type_hints`)**: Both Dishka `Provider` classes and `@inject` / `DishkaRouter` call `typing.get_type_hints` at runtime. Avoid `from __future__ import annotations` in Dishka `Provider` files, and in controller/handler modules using `FromDishka` ensure all parameter types are imported at runtime (never hidden inside `if TYPE_CHECKING:`).
- **Sync retrieval on `AsyncContainer`**: Dishka `1.10.1` provides `container.get_sync(DepType)` on `AsyncContainer` for retrieving already-cached or synchronous dependencies from synchronous contexts without `await`.
- **`DishkaRouter` class mutation in tests**: `DishkaRouter.register()` wraps `Controller.get_route_handlers` on the `Controller` class. In tests that mount the same `Controller` class on a plain `Litestar` test app without `setup_dishka`, either call `setup_dishka` with a test `AsyncContainer` or inject a mock `scope["state"]["dishka_container"]` in middleware.
- **Auth middleware ordering**: `setup_dishka(container, app)` wraps `app.asgi_handler` at the outermost ASGI layer, so `connection.state.dishka_container` is available inside `retrieve_user_handler` callbacks via `await connection.state.dishka_container.get(UserService)`.

## When to Scale Up

| Symptom | Stay on `Provide()` | Move to Dishka |
| --- | --- | --- |
| <10 dependencies | ✓ | — |
| Flat dependency graph | ✓ | — |
| Resource lifetimes match request | ✓ | — |
| Need cross-scope (`APP` singleton + `SESSION` WS + `REQUEST` transient) | — | ✓ |
| Hand-wiring `Provide` callables feels repetitive | — | ✓ |
| Strict type-based resolution across modular `Provider` classes | — | ✓ |
| Mixing CLI + worker + HTTP entry points sharing services | — | ✓ |

## Cross-references

- Repository service deps live alongside DB sessions: [services-and-repos.md](services-and-repos.md)
- Plugin-supplied deps (e.g. `TaskQueues` from `litestar-saq`): [plugins.md](plugins.md), `../../litestar-saq/SKILL.md`
- Automatic `DishkaRouter` wiring for domain controllers: [integrations.md](../../litestar-autowire/references/integrations.md)

## Tagged source

- [2.24 dependency injection guide](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/usage/dependency-injection.rst)
- [2.24 `Provide` and `NamedDependency`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/di.py)
- [2.24 test override guidance](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/onboarding/fastapi.rst)
- [Dishka 1.10.1 Litestar integration](https://github.com/reagento/dishka/blob/1.10.1/src/dishka/integrations/litestar.py)
