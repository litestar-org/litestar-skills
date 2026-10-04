# App Composition, Lifecycle, State, and 2.22–2.24 Contracts

## `Litestar(...)` Constructor and `AppConfig`

Keep the `Litestar` constructor thin and declarative. Group domain routes into Controllers or Routers, register first-party plugins, and pass shared configuration objects from a settings module.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar, Request, Response, get
from litestar.config.app import AppConfig
from litestar.datastructures import ImmutableState, State
from litestar.events import listener
from litestar.static_files import create_static_files_router


@asynccontextmanager
async def db_lifespan(app: Litestar) -> AsyncIterator[None]:
    """Initialize and dispose shared application resources across lifespan."""
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False


def normalize_app_config(app_config: AppConfig) -> AppConfig:
    """Inspect or mutate AppConfig during application initialization."""
    app_config.tags.append("v1")
    return app_config


@listener("audit.event")
async def handle_audit_event(event_name: str, actor_id: str) -> None:
    """Process asynchronous in-process events emitted via request.app.emit."""
    _ = (event_name, actor_id)


@get("/health")
async def health_check(
    state: ImmutableState,
    request: Request[object, object, State],
) -> dict[str, bool]:
    """Read application state through ImmutableState and emit an audit event."""
    request.app.emit("audit.event", event_name="health_check", actor_id="system")
    return {"ready": bool(state.get("ready", False))}


def create_app() -> Litestar:
    """Construct the Litestar application instance."""
    return Litestar(
        route_handlers=[
            health_check,
            create_static_files_router(path="/static", directories=["public"]),
        ],
        path="/api",
        lifespan=[db_lifespan],
        on_app_init=[normalize_app_config],
        listeners=[handle_audit_event],
        state=State({"ready": False}),
        request_max_body_size=10_000_000,
        multipart_form_part_limit=1000,
    )
```

### Core `Litestar` / `AppConfig` Parameters

| Category | Parameters | Notes |
| --- | --- | --- |
| Routing & Static | `route_handlers`, `path` | Mount static assets via `create_static_files_router(path=..., directories=[...])` inside `route_handlers` (`StaticFilesConfig` is deprecated). |
| Plugins & DI | `plugins`, `dependencies`, `signature_namespace`, `signature_types` | Prefer `InitPlugin` / `CLIPluginProtocol` in `plugins` and explicit `NamedDependency[T]` at injection sites. |
| Security & Middleware | `guards`, `middleware`, `cors_config`, `csrf_config`, `allowed_hosts`, `compression_config`, `security` | Built-in config objects (`CORSConfig`, `CSRFConfig`, `AllowedHostsConfig`, `CompressionConfig`) auto-register their middleware. |
| Lifespan & Hooks | `lifespan`, `on_startup`, `on_shutdown`, `on_app_init`, `before_request`, `after_request`, `after_response`, `before_send`, `after_exception` | Prefer `lifespan=[...]` async context managers over split `on_startup`/`on_shutdown` pairs when a resource needs teardown. |
| State, Stores & Cache | `state`, `stores`, `response_cache_config`, `cache_control`, `etag` | `stores` accepts a `StoreRegistry` or `dict[str, Store]`; registered stores join app lifespan automatically. |
| Serialization & DTOs | `dto`, `return_dto`, `type_encoders`, `type_decoders`, `request_max_body_size`, `multipart_form_part_limit` | `request_max_body_size` defaults to `10_000_000` bytes (10 MB); set on app or per route handler. |
| OpenAPI & Templates | `openapi_config`, `template_config`, `tags`, `include_in_schema`, `opt`, `parameters` | `openapi_config` defaults to `DEFAULT_OPENAPI_CONFIG` serving `/schema`; pass `openapi_config=None` to disable. |
| Events & Debugging | `listeners`, `event_emitter_backend`, `logging_config`, `exception_handlers`, `debug`, `pdb_on_exception`, `debugger_module` | `event_emitter_backend` defaults to `SimpleEventEmitter`. |

## Reference Architecture: `ApplicationCore` + `create_app()`

In multi-domain applications following [`litestar-fullstack`](https://github.com/litestar-org/litestar-fullstack) and `litestar-sqlstack`, encapsulate all `AppConfig` and CLI wiring inside `ApplicationCore(InitPluginProtocol, CLIPluginProtocol)` in `server/core.py` and keep `create_app() -> Litestar` in `asgi.py` (or `server/app.py`) to a single plugin registration:

```python
import click
from litestar import Litestar
from litestar.config.app import AppConfig
from litestar.config.response_cache import ResponseCacheConfig
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol
from litestar.stores.memory import MemoryStore
from litestar.stores.registry import StoreRegistry


class ApplicationCore(InitPluginProtocol, CLIPluginProtocol):
    """Centralize application and CLI initialization in a single core plugin."""

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Register plugins, routes, dependencies, stores, and logging on AppConfig."""
        app_config.stores = StoreRegistry(stores={"response_cache": MemoryStore()})
        app_config.response_cache_config = ResponseCacheConfig(default_expiration=60)
        app_config.logging_config = LoggingConfig(
            log_exceptions="always",
            disable_stack_trace={404},
        )
        return app_config

    def on_cli_init(self, cli: click.Group) -> None:
        """Attach application-specific Click commands to the litestar CLI group."""
        _ = cli


def create_app() -> Litestar:
    """Instantiate Litestar via the ApplicationCore plugin."""
    return Litestar(plugins=[ApplicationCore()])
```

Use direct `Litestar(...)` keyword arguments for compact services or tests, and `ApplicationCore(InitPluginProtocol, CLIPluginProtocol)` when coordinating multiple domain routers, ecosystem plugins (`GranianPlugin`, `SQLAlchemyPlugin` / `SQLSpecPlugin`, `SAQPlugin` / `QueuePlugin`, `VitePlugin`), and custom CLI commands.

## Lifespan and Request Lifecycle Execution Order

| Hook / Manager | Signature / Shape | When It Runs |
| --- | --- | --- |
| `on_app_init` | `Callable[[AppConfig], AppConfig]` | Synchronous boot phase before `Litestar.__init__` finalizes route and middleware tables. Plugin `InitPlugin.on_app_init` hooks run before `Litestar(on_app_init=[...])`. |
| `CLIPlugin.server_lifespan` | `@contextmanager def server_lifespan(self, app: Litestar)` | CLI server process wrapper before/after worker startup (`litestar run`). |
| `lifespan` | `Callable[[Litestar], AbstractAsyncContextManager[Any]] \| AbstractAsyncContextManager[Any]` | ASGI lifespan startup and shutdown in registration order. |
| `on_startup` / `on_shutdown` | `Callable[[Litestar], Any] \| Callable[[], Any]` | ASGI lifespan startup (before serving requests) and shutdown (after draining requests). |
| `before_request` | `Callable[[Request], Any]` | Before the route handler runs; returning a response or value short-circuits the handler. |
| `after_request` | `Callable[[Response], Response]` | After the route handler builds a `Response`, before sending it over ASGI. |
| `before_send` | `Callable[[Message, Scope], Awaitable[None]]` | Low-level ASGI send hook invoked on every ASGI message. |
| `after_response` | `Callable[[Request], Any]` | After the HTTP response has been sent to the client. |
| `after_exception` | `Callable[[Exception, Scope], Any]` | When an exception occurs during request processing, before exception handlers map it to a response. |

## Application State (`State` and `ImmutableState`)

`State` (`from litestar.datastructures import State, ImmutableState`) is a mutable, thread-safe (`RLock`-guarded) mapping supporting both attribute (`state.db_pool`) and dictionary (`state["db_pool"]`) access.

- Pass initial state via `Litestar(state=State({...}))` or mutate `app.state` inside a `lifespan` context manager.
- Inject `state: ImmutableState` in route handlers or dependencies that should only read state.
- Inject `state: State` when mutating state is required.
- Helper methods:
  - `State.dict() -> dict[str, Any]`
  - `State.copy() -> State`
  - `State.immutable_copy() -> ImmutableState`
  - `ImmutableState.mutable_copy() -> State`

## Litestar 2.22–2.24 Explicit Declaration Contracts

Litestar 2.22 through 2.24 standardize explicit parameter, body, and dependency annotations in preparation for Litestar 3.0:

```python
from typing import Annotated

import msgspec
from litestar import Controller, get, post
from litestar.di import NamedDependency, Provide
from litestar.params import (
    CookieParameter,
    FromCookie,
    FromHeader,
    FromPath,
    FromQuery,
    HeaderParameter,
    JSONBody,
    MsgPackBody,
    MultipartBody,
    PathParameter,
    QueryParameter,
    SkipValidation,
    URLEncodedBody,
)


class CreateItemPayload(msgspec.Struct):
    name: str
    tags: list[str] | None = None


class ItemService:
    async def get_item(self, item_id: int, locale: str | None) -> dict[str, object]:
        return {"id": item_id, "locale": locale}


async def provide_item_service() -> ItemService:
    return ItemService()


class ItemController(Controller):
    path = "/items"
    dependencies = {"item_service": Provide(provide_item_service)}

    @get("/{item_id:int}")
    async def retrieve_item(
        self,
        item_id: FromPath[int],
        item_service: NamedDependency[ItemService],
        locale: FromQuery[str | None] = None,
        trace_id: FromHeader[str | None] = None,
        session_id: FromCookie[str | None] = None,
        page_size: Annotated[int, QueryParameter(gt=0, le=100)] = 25,
        region: Annotated[str | None, HeaderParameter(name="X-Region")] = None,
        theme: Annotated[str | None, CookieParameter(name="ui_theme")] = None,
        raw_ctx: NamedDependency[SkipValidation[dict[str, object] | None]] = None,
    ) -> dict[str, object]:
        """Use explicit parameter, dependency, and skip-validation type markers."""
        _ = (trace_id, session_id, page_size, region, theme, raw_ctx)
        return await item_service.get_item(item_id=item_id, locale=locale)

    @post("/json")
    async def create_json_item(
        self,
        data: JSONBody[CreateItemPayload],
    ) -> CreateItemPayload:
        """Accept an explicit JSON request body via JSONBody[T]."""
        return data

    @post("/msgpack")
    async def create_msgpack_item(
        self,
        data: MsgPackBody[CreateItemPayload],
    ) -> CreateItemPayload:
        """Accept a MessagePack request body via MsgPackBody[T]."""
        return data

    @post("/form")
    async def create_urlencoded_item(
        self,
        data: URLEncodedBody[CreateItemPayload],
    ) -> CreateItemPayload:
        """Accept URL-encoded form data via URLEncodedBody[T]."""
        return data

    @post("/multipart")
    async def create_multipart_item(
        self,
        data: MultipartBody[dict[str, str]],
    ) -> dict[str, str]:
        """Accept multipart form data via MultipartBody[T]."""
        return data
```

### Summary of 2.22–2.24 Changes

| Release | Contract Change | Preferred Pattern |
| --- | --- | --- |
| **2.22.0** | Explicit parameter generics and source-specific parameter metadata classes added. | Use `FromPath[T]`, `FromQuery[T]`, `FromHeader[T]`, `FromCookie[T]` for unconstrained parameters, and `Annotated[T, PathParameter(...)]`, `QueryParameter(...)`, `HeaderParameter(...)`, `CookieParameter(...)` when constraints or wire names (`name=...`) are needed. |
| **2.22.0** | `litestar.contrib.{jinja,mako,minijinja,opentelemetry}` and `litestar.repository` deprecated. | Import from `litestar.plugins.{jinja,mako,minijinja,opentelemetry}` and `advanced_alchemy` instead. |
| **2.22.0** | `Decimal` OpenAPI schema output updated; `SwaggerRenderPlugin(oauth2_redirect_url=...)` added. | `Decimal` fields emit `type: "string"` in OpenAPI schemas to preserve precision. |
| **2.23.0** | Generic request body type aliases added (`JSONBody`, `MsgPackBody`, `MultipartBody`, `URLEncodedBody`). | Use `data: JSONBody[Payload]`, `MsgPackBody[Payload]`, `MultipartBody[Payload]`, or `URLEncodedBody[Payload]` instead of `Body(media_type=RequestEncodingType....)` when extra `Body(...)` constraints are not needed. |
| **2.23.0** | `NamedDependency[T]` and `SkipValidation[T]` added; `litestar.params.Dependency` deprecated. | Import `NamedDependency` from `litestar.di` and `SkipValidation` from `litestar.params`. |
| **2.23.0** | Strict `Host` header validation enforced. | Requests with malformed `Host` headers are rejected with `400 Bad Request`. |
| **2.24.0** | Implicitly declared dependencies deprecated. | Annotate injected dependencies with `NamedDependency[T]` (or `NamedDependency[SkipValidation[T]]` when skipping validation). |
| **2.24.0** | OpenAPI 3.1 required vs nullable semantics and dependency-owned `data` parameters fixed. | Nullable fields (`T \| None`) without a default value are marked `required` in OpenAPI 3.1; give optional fields an explicit `= None` default. `data` declared inside a dependency function is now included in the route's OpenAPI schema. |
