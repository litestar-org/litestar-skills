# Litestar Framework Guide

Async-first Python web framework with dependency injection and plugin architecture.

## Route Handlers

### Basic Routes

```python
from litestar import Controller, delete, get, post, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, JSONBody


@get("/items/{item_id:int}")
async def get_item(item_id: FromPath[int]) -> Item:
    return await fetch_item(item_id)


@post("/items")
async def create_item(data: JSONBody[CreateItemDTO]) -> Item:
    return await save_item(data)
```

### Controllers

```python
class ItemController(Controller):
    path = "/items"
    dependencies = {"service": Provide(get_service)}

    @get("/")
    async def list_items(self, service: NamedDependency[ItemService]) -> list[Item]:
        return await service.list_all()

    @get("/{item_id:int}")
    async def get_item(
        self,
        item_id: FromPath[int],
        service: NamedDependency[ItemService],
    ) -> Item:
        return await service.get(item_id)

    @post("/")
    async def create_item(
        self,
        data: JSONBody[CreateItemDTO],
        service: NamedDependency[ItemService],
    ) -> Item:
        return await service.create(data)
```

## Typed Markers (Litestar ≥ 2.23)

Litestar 2.22–2.25 added generic marker aliases and explicit reserved-kwarg types that replace verbose `Annotated[T, Parameter()]` / `Annotated[T, Body()]` / `Annotated[T, Dependency()]` forms and implicit source inference. **Prefer the markers** — the underlying `params.Dependency`/`DependencyKwarg`, implicit parameter/dependency inference, and unmarked `data` / untyped reserved kwargs emit `LitestarDeprecationWarning` and are removed in 3.0. These examples target `litestar>=2.25`.

```python
from litestar import get, post
from litestar.di import NamedDependency
from litestar.params import (
    FromCookie,
    FromHeader,
    FromPath,
    FromQuery,
    JSONBody,
    MultipartBody,
    QueryParams,
    RawBody,
    RequestBody,
    RequestCookies,
    SkipValidation,
)


# Request parameters (2.22): FromQuery / FromPath / FromHeader / FromCookie
@get("/items/{item_id:int}")
async def get_item(item_id: FromPath[int], q: FromQuery[str | None] = None) -> Item:
    return await fetch_item(item_id, q)


# Request body (2.23 / 2.25): JSONBody / RequestBody / MsgPackBody / MultipartBody / URLEncodedBody
@post("/upload")
async def upload(data: MultipartBody[UploadDTO]) -> Receipt: ...


# Raw request body / reserved kwargs (2.25): RawBody / QueryParams / RequestCookies
@post("/webhook")
async def webhook(body: RawBody) -> dict[str, int]:
    return {"bytes": len(body)}


# Dependency injection (2.23):
#   NamedDependency[T]   replaces  Annotated[T, Dependency()]
#   NamedDependency[SkipValidation[T]] replaces Dependency(skip_validation=True)
@get("/users")
async def list_users(
    users_service: NamedDependency[UserService],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[User]:
    rows, total = await users_service.get_many_and_count(*filters)
    return users_service.to_schema(rows, total, filters=filters, schema_type=User)
```

Migration map (old → new):

| Old (deprecated/verbose) | New marker (≥ 2.23 / 2.25) |
| --- | --- |
| `Annotated[T, Parameter()]` query param | `FromQuery[T]` |
| `Annotated[T, Parameter()]` path param | `FromPath[T]` |
| `data: T` (unmarked body kwarg, deprecated in 2.25) | `data: JSONBody[T]` or `data: RequestBody[T]` |
| `Annotated[T, Body(media_type=RequestEncodingType.MULTI_PART)]` | `MultipartBody[T]` |
| `Annotated[T, Body(media_type=RequestEncodingType.URL_ENCODED)]` | `URLEncodedBody[T]` |
| `body: bytes` / `query: MultiDict` / `cookies: dict[str, str]` (2.25) | `body: RawBody` / `query: QueryParams` / `cookies: RequestCookies` |
| `Annotated[T, Dependency()]` | `NamedDependency[T]` |
| `Annotated[T, Dependency(skip_validation=True)]` | `NamedDependency[SkipValidation[T]]` |
| `Parameter(query=...)` / `Parameter(header=...)` | `QueryParameter(name=...)` / `HeaderParameter(name=...)` |
| `field: T = Parameter(default="x")` | `field: FromQuery[T] = "x"` |

## Dependency Injection

### Litestar Native DI

```python
from litestar import Litestar, Request
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide


async def get_db_session(state: State) -> AsyncSession:
    return state.db_session


async def get_current_user(
    request: Request,
    session: NamedDependency[AsyncSession],
) -> User:
    token = request.headers.get("Authorization")
    return await authenticate(session, token)


app = Litestar(
    route_handlers=[...],
    dependencies={
        "session": Provide(get_db_session),
        "current_user": Provide(get_current_user),
    },
)
```

### Dishka Integration

```python
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.litestar import (
    DishkaRouter,
    FromDishka,
    LitestarProvider,
    setup_dishka,
)
from litestar import Litestar, get


class ServiceProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def provide_user_service(
        self,
        driver: AsyncDriverAdapterBase,
    ) -> UserService:
        return UserService(driver)


# Usage in handlers (wrapped via DishkaRouter or @inject)
@get("/users")
async def list_users(service: FromDishka[UserService]) -> list[User]:
    return await service.list_all()


# Setup
container = make_async_container(LitestarProvider(), ServiceProvider())
app = Litestar(route_handlers=[DishkaRouter(path="", route_handlers=[list_users])])
setup_dishka(container, app)
```

## Middleware

```python
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send


class TimingMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP,)
    exclude_path_pattern = (r"^/health$", r"^/metrics$")

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        next_app: ASGIApp,
    ) -> None:
        start = time.perf_counter()
        await next_app(scope, receive, send)
        duration = time.perf_counter() - start
        logger.info(f"Request took {duration:.3f}s")
```

## DTOs

Prefer `MsgspecDTO` with `msgspec.Struct` in new Litestar code; use `DataclassDTO`, `SQLAlchemyDTO`, or `PydanticDTO` to match the project's existing stack.

```python
import msgspec
from litestar import get
from litestar.dto import DTOConfig, MsgspecDTO
from litestar.params import FromPath


class User(msgspec.Struct):
    id: int
    name: str
    email: str
    password_hash: str  # Sensitive!


class UserReadDTO(MsgspecDTO[User]):
    config = DTOConfig(exclude={"password_hash"})


class UserCreateDTO(MsgspecDTO[User]):
    config = DTOConfig(exclude={"id", "password_hash"})


@get("/users/{user_id:int}", return_dto=UserReadDTO)
async def get_user(user_id: FromPath[int]) -> User:
    return await fetch_user(user_id)
```

## Guards (Auth)

```python
from litestar import get
from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers import BaseRouteHandler


async def requires_auth(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    if not connection.scope.get("user"):
        raise PermissionDeniedException("Authentication required")


@get("/protected", guards=[requires_auth])
async def protected_route() -> dict[str, bool]: ...
```

## Exception Handling

```python
from litestar import get
from litestar.exceptions import HTTPException
from litestar.params import FromPath
from litestar.status_codes import HTTP_404_NOT_FOUND


class ItemNotFoundError(HTTPException):
    status_code = HTTP_404_NOT_FOUND
    detail = "Item not found"


@get("/items/{item_id:int}")
async def get_item(item_id: FromPath[int]) -> Item:
    item = await fetch_item(item_id)
    if item is None:
        raise ItemNotFoundError()
    return item
```

## Plugin Development

Subclass `InitPlugin` (from `litestar.plugins`), `CLIPlugin` / `CLIPluginProtocol`, `SerializationPlugin`, `OpenAPISchemaPlugin`, `ReceiveRoutePlugin`, or `DIPlugin`. (`InitPluginProtocol` and `SerializationPluginProtocol` are deprecated since Litestar 2.15 in favor of `InitPlugin` and `SerializationPlugin`.)

```python
from dataclasses import dataclass

from litestar.config.app import AppConfig
from litestar.plugins import InitPlugin


@dataclass
class MyPluginConfig:
    enabled: bool = True
    api_key: str | None = None


class MyPlugin(InitPlugin):
    __slots__ = ("config",)

    def __init__(self, config: MyPluginConfig | None = None) -> None:
        self.config = config or MyPluginConfig()

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        if self.config.enabled:
            app_config.state["my_plugin"] = self
        return app_config
```

## Vite Integration

```python
from pathlib import Path

from litestar import Litestar
from litestar_vite import PathConfig, TypeGenConfig, ViteConfig, VitePlugin

vite_config = ViteConfig(
    mode="spa",  # spa, template, htmx, hybrid, inertia, framework, ssr, ssg, external
    paths=PathConfig(
        resource_dir="src",
        bundle_dir="dist",
    ),
    types=TypeGenConfig(
        generate_sdk=True,
        generate_routes=True,
        generate_schemas=True,
        output=Path("src/generated"),
    ),
)

app = Litestar(plugins=[VitePlugin(config=vite_config)])
```

## Inertia Integration

```python
from litestar import Litestar, get
from litestar_vite import ViteConfig, VitePlugin
from litestar_vite.inertia import InertiaConfig

app = Litestar(
    plugins=[
        VitePlugin(
            config=ViteConfig(
                mode="hybrid",
                inertia=InertiaConfig(root_template="base.html"),
            )
        ),
    ],
)


@get("/users", component="Users/Index")
async def users_page() -> dict[str, list[User]]:
    return {"users": await fetch_users()}
```

## CLI Commands

```bash
litestar assets install        # Install frontend deps
litestar assets serve          # Start Vite dev server
litestar assets build          # Build for production
litestar assets generate-types # Generate TypeScript types
litestar assets status         # Check integration status
```

## Code Style Rules

- Use PEP 604 for unions: `T | None` (not `Optional[T]`)
- `from __future__ import annotations` is a **library-author guardrail, not a consumer rule**. Application code (handlers, services, tests — the Litestar apps you're building) MAY and typically SHOULD use it. Avoid it only in modules that define runtime-introspected types: `msgspec.Struct` subclasses, SQLAlchemy 2.0 `Mapped[...]` models, Dishka `@provide` providers, SAQ `@task` / `CronJob` registrations, Google ADK tool definitions.
- When `from __future__ import annotations` is enabled in Litestar route/controller modules alongside Ruff `flake8-type-checking` (`TC`), keep runtime-inspected handler annotations (`Request`, `NamedDependency`, `FromDishka`, `FromPath`, `FromQuery`, `JSONBody`, request/response DTOs) at module top-level with `# noqa: TC001, TC002` (or `"**/controllers.py" = ["TC001", "TC002", "TC003"]` in `per-file-ignores`). Moving them into `if TYPE_CHECKING:` causes runtime `NameError` when Litestar or Dishka inspects handler signatures at startup.
- Use Google-style docstrings
- All I/O operations should be async
- Import template engines and integrations from `litestar.plugins.*`, not `litestar.contrib.*` (`litestar.contrib.{jinja,mako,minijinja,opentelemetry}` are deprecated since 2.22 and removed in 3.0). Import the repository/service base from `advanced_alchemy`, not the deprecated `litestar.repository`.
- Prefer the typed markers (`FromQuery`/`FromPath`/`JSONBody`/`RequestBody`/`MultipartBody`/`NamedDependency`/`SkipValidation` and 2.25 reserved-kwarg markers `RawBody`/`QueryParams`/`RequestCookies`) over `Annotated[..., Parameter()/Body()/Dependency()]` or unmarked `data: T`; `params.Dependency`, implicit parameter/dependency inference, and untyped reserved kwargs are deprecated and removed in 3.0. See [Typed Markers](#typed-markers-litestar--223).

## Anti-Patterns

```python
# Bad: Using Optional
from typing import Optional


def bad(x: Optional[str]): ...


# Good: Use union syntax
def good(x: str | None): ...


# Bad: Sync I/O in async handler
@get("/data")
async def bad_handler() -> Data:
    with open("file.txt") as f:  # Blocking!
        return f.read()


# Good: Use async I/O
@get("/data")
async def good_handler() -> Data:
    async with aiofiles.open("file.txt") as f:
        return await f.read()


# Bad: Not typing return values
@get("/items")
async def list_items():  # Missing return type
    return await fetch_items()


# Good: Explicit return types
@get("/items")
async def list_items() -> list[Item]:
    return await fetch_items()
```
