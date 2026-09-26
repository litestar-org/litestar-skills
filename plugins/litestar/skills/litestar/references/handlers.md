# Route Handlers, Controllers, Routers, and Layered Resolution

## HTTP Route Handlers (`@get`, `@post`, `@put`, `@patch`, `@delete`, `@head`, `@route`)

Keep route handlers thin: parse request data, call a domain service, and return a DTO or response object. Put shared `path`, `dependencies`, `guards`, `tags`, `dto`, `return_dto`, and `middleware` on the `Controller` or `Router`.

```python
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from litestar import Controller, HttpMethod, delete, get, head, patch, post, put, route
from litestar.di import NamedDependency, Provide
from litestar.params import (
    Body,
    CookieParameter,
    FromCookie,
    FromHeader,
    FromPath,
    FromQuery,
    HeaderParameter,
    MultipartBody,
    PathParameter,
    QueryParameter,
)


@get("/items/{item_id:int}")
async def get_item(item_id: FromPath[int]) -> Item:
    return await fetch_item(item_id)


@post("/items")
async def create_item(data: CreateItemDTO) -> Item:
    return await save_item(data)


@put("/items/{item_id:int}")
async def replace_item(item_id: FromPath[int], data: ReplaceItemDTO) -> Item:
    return await overwrite_item(item_id, data)


@patch("/items/{item_id:int}")
async def update_item(item_id: FromPath[int], data: UpdateItemDTO) -> Item:
    return await modify_item(item_id, data)


@delete("/items/{item_id:int}")
async def remove_item(item_id: FromPath[int]) -> None:
    await delete_item_by_id(item_id)


@head("/items/{item_id:int}")
async def check_item(item_id: FromPath[int]) -> None:
    await verify_item_exists(item_id)


@route(["/items/ping", "/v1/items/ping"], http_method=[HttpMethod.GET, HttpMethod.POST])
async def ping_items() -> dict[str, str]:
    return {"status": "ok"}
```

### Default Status Codes & Handler Validation Rules

| Decorator / Method | Default `status_code` | Return & Parameter Constraints |
| --- | --- | --- |
| `@get` | `200` | Must annotate return type. Cannot declare `data` kwarg (`ImproperlyConfiguredException`). |
| `@post` | `201` | Must annotate return type. Accepts `request_max_body_size`. |
| `@put` | `200` | Must annotate return type. Accepts `request_max_body_size`. |
| `@patch` | `200` | Must annotate return type. Accepts `request_max_body_size`. |
| `@delete` | `204` | Must annotate `-> None` (or empty response) when `status_code=204`. Set `status_code=200` to return a body. |
| `@head` | `200` | Must annotate `-> None` (or empty response / `File` / `ASGIFileResponse`). Cannot return a body. |
| `@route` | `201` (`POST`), `204` (`DELETE`), else `200` | Requires `http_method: HttpMethod \| Method \| Sequence[HttpMethod \| Method]`. Accepts `request_max_body_size`. |

- **Return annotation required**: omitting a return annotation on any route handler raises `ImproperlyConfiguredException`.
- **Empty body status codes**: status codes `< 200`, `204` (`HTTP_204_NO_CONTENT`), or `304` (`HTTP_304_NOT_MODIFIED`) require `-> None` (or `Response[None]`), otherwise `ImproperlyConfiguredException` is raised.
- **Default `media_type`**: inferred as `MediaType.TEXT` when returning `str`, `bytes`, or `AnyStr`, and `MediaType.JSON` for all other non-`Response` return types unless `media_type=` is explicitly provided.
- **Sync handlers (`sync_to_thread`)**: synchronous (`def`) handlers must explicitly set `sync_to_thread=True` (runs in AnyIO worker thread for blocking work) or `sync_to_thread=False` (runs inline on the event loop for trivial non-blocking work). Leaving `sync_to_thread=None` on a sync handler or setting `sync_to_thread` on an `async def` handler emits `LitestarWarning`.
- **Do not subclass `@get`/`@post`/etc.**: subclassing semantic handler classes emits `DeprecationWarning` (they become functional decorators in Litestar 3.0).

### `HTTPRouteHandler` Kwargs Reference

| Category | Kwargs |
| --- | --- |
| **Routing & Execution** | `path: str \| Sequence[str] \| None = None` (defaults to `"/"`), `http_method` (`@route` only), `status_code: int \| None = None`, `media_type: MediaType \| str \| None = None`, `sync_to_thread: bool \| None = None`, `background: BackgroundTask \| BackgroundTasks \| None = None`, `name: str \| None = None` (for `app.route_reverse`), `opt: Mapping[str, Any] \| None = None` (extra `**kwargs` also merge into `opt`) |
| **Hooks, Guards & Middleware** | `before_request`, `after_request`, `after_response`, `guards: Sequence[Guard] \| None = None`, `middleware: Sequence[Middleware] \| None = None`, `exception_handlers: ExceptionHandlersMap \| None = None` |
| **DI, DTOs & Serialization** | `dependencies: Dependencies \| None = None`, `dto: type[AbstractDTO] \| None \| EmptyType = Empty`, `return_dto: type[AbstractDTO] \| None \| EmptyType = Empty`, `type_encoders`, `type_decoders`, `signature_namespace`, `signature_types`, `request_class`, `response_class`, `request_max_body_size: int \| None \| EmptyType = Empty` |
| **Caching, Headers & Cookies** | `cache: bool \| int \| type[CACHE_FOREVER] = False`, `cache_key_builder: CacheKeyBuilder \| None = None`, `cache_control: CacheControlHeader \| None = None`, `etag: ETag \| None = None`, `response_headers: ResponseHeaders \| None = None`, `response_cookies: ResponseCookies \| None = None` |
| **OpenAPI Schema** | `tags: Sequence[str] \| None = None`, `summary: str \| None = None`, `description: str \| None = None`, `response_description: str \| None = None`, `responses: Mapping[int, ResponseSpec] \| None = None`, `raises: Sequence[type[HTTPException]] \| None = None`, `deprecated: bool = False`, `include_in_schema: bool \| EmptyType = Empty`, `security: Sequence[SecurityRequirement] \| None = None`, `operation_id: str \| OperationIDCreator \| None = None`, `operation_class: type[Operation] = Operation`, `content_encoding: str \| None = None`, `content_media_type: str \| None = None` |

## ASGI Route Handlers (`@asgi` / `ASGIRouteHandler`)

Use `@asgi` to mount raw ASGI applications or custom ASGI callables:

```python
from litestar import asgi
from litestar.types import Receive, Scope, Send


@asgi("/sub-app", is_mount=True, copy_scope=True)
async def mounted_sub_app(scope: Scope, receive: Receive, send: Send) -> None:
    await other_asgi_app(scope, receive, send)
```

- **Signature rules**: the decorated callable must be `async def`, accept `scope`, `receive`, and `send` parameters, and annotate `-> None` (`ImproperlyConfiguredException` otherwise).
- **`is_mount: bool = False`**: when `True`, matches `/sub-app` and any sub-path underneath it (`/sub-app/a/b`).
- **`is_static: bool = False`**: marks static file handlers (automatically sets `is_mount=True`).
- **`copy_scope: bool | None = None`**: always set `copy_scope=True` (prevents mounted apps from mutating Litestar's ASGI scope) or `copy_scope=False` (when scope mutation is intentional). Leaving `copy_scope=None` emits `DeprecationWarning` in 2.x (`copy_scope` defaults to `True` in 3.0).
- **Supported kwargs**: `path`, `is_mount`, `is_static`, `copy_scope`, `guards`, `exception_handlers`, `name`, `opt`, `signature_namespace`, `**kwargs`.

## `Controller`, `Router`, and Layered Resolution

### Controller (preferred for related routes)

Cluster Controllers by business domain, not by HTTP method:

```python
from litestar import Controller, get
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath


class ItemController(Controller):
    path = "/api/items"
    tags = ["Items"]
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
```

- Every `(path, http_method)` (or `websocket` / `asgi`) combination on a `Controller` must be unique; duplicates raise `ImproperlyConfiguredException`.

### Router Composition

```python
# src/app/server/routers.py
from litestar import Router

from app.domain.accounts.controllers import AccountController, UserController
from app.domain.teams.controllers import TeamController


def create_api_router() -> Router:
    return Router(
        path="/api",
        route_handlers=[
            AccountController,
            UserController,
            TeamController,
        ],
    )
```

`Router(path, *, route_handlers, ...)` and `router.register(value)` accept `Controller` subclasses, nested `Router` instances (deep-copied on registration; registering a router on itself raises `ImproperlyConfiguredException`), `WebsocketListener` subclasses, and decorated route handlers (`@get`, `@post`, `@route`, `@websocket`, `@asgi`, etc.). For larger domain-package apps, use [Litestar Autowire](../../litestar-autowire/SKILL.md) (see [layout.md](layout.md)).

### Layered Resolution (`Litestar -> Router -> Controller -> Handler`)

Configuration attributes shared across `Litestar`, `Router`, `Controller`, and `HTTPRouteHandler` resolve across the ownership chain (`Litestar -> Router(s) -> Controller -> Handler`) using three strategies:

| Strategy | Attributes | Resolution Behavior |
| --- | --- | --- |
| **Override (closest to handler wins)** | `before_request`, `after_request`, `after_response`, `dto`, `return_dto`, `request_class`, `response_class`, `websocket_class`, `request_max_body_size`, `include_in_schema`, `cache_control`, `etag` | The innermost layer where the attribute is set (not `Empty` / `None`) replaces outer layers. Setting `dto=None` or `return_dto=None` on a handler disables a DTO inherited from a Controller/Router/App. If `return_dto` is `Empty` on all layers, it falls back to the resolved `dto`. |
| **Keyed Merge (inner keys override outer keys)** | `dependencies`, `exception_handlers`, `opt`, `parameters`, `response_headers`, `response_cookies`, `type_encoders`, `signature_namespace` | Dictionaries/sets merge top-down (`Litestar -> Router -> Controller -> Handler`); matching keys on closer layers override outer layers. |
| **Additive (accumulated across all layers)** | `guards`, `middleware`, `tags`, `security`, `type_decoders` | All layers combine outer-to-inner. `guards` and `middleware` run from `Litestar` down to `Handler`; `tags` form a sorted unique union; `security` and `type_decoders` concatenate in layer order. |

## Cross-References

- Path parameters, `From*` / `*Parameter` markers, `Body`, and reserved kwargs: [parameters.md](parameters.md)
- Domain-clustered folder layout and vertical slice: [layout.md](layout.md)
- Controller-level guards: [auth-and-guards.md](auth-and-guards.md)
- Controller-level filter dependencies: [filters-and-pagination.md](filters-and-pagination.md)
