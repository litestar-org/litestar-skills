# Litestar Middleware Reference

Litestar supports two middleware categories:

1. **Built-in middleware configurations** — declarative dataclasses passed either to `Litestar(...)` (`cors_config`, `csrf_config`, `allowed_hosts`, `compression_config`, `response_cache_config`) or via `.middleware` in `middleware=[...]` (`RateLimitConfig`, `LoggingMiddlewareConfig`, `ServerSideSessionConfig`, `CookieBackendConfig`).
2. **Custom ASGI middleware** — `ASGIMiddleware` subclasses (preferred), `AbstractAuthenticationMiddleware` subclasses, and `MiddlewareProtocol` / third-party ASGI classes wrapped with `DefineMiddleware`.

## Execution Order and Layering

Understanding where each middleware runs prevents subtle ordering bugs with CORS preflights, exception handling, and `scope["route_handler"]` availability:

1. **Pre-routing (outer ASGI router boundary)**:
   - `OpenTelemetryPlugin` middleware (when installed)
   - `CORSMiddleware` (`Litestar(cors_config=...)`)
   - Outer `ExceptionHandlerMiddleware` (catches routing `404`/`405` and CORS errors)
   - `ASGIRouter` (matches the route and populates `scope["route_handler"]`, `scope["path_params"]`, and `scope["path_template"]`)
2. **Per-route stack (wrapped outermost to innermost for each route)**:
   1. User `middleware=[...]` resolved additively across `app -> router -> controller -> route_handler` (in list order at each layer; the first entry in `Litestar(middleware=[...])` runs first on request and last on response)
   2. `AllowedHostsMiddleware` (`Litestar(allowed_hosts=...)`)
   3. `ResponseCacheMiddleware` (`Litestar(response_cache_config=...)` when the route enables `cache`)
   4. `CompressionMiddleware` (`Litestar(compression_config=...)`)
   5. `CSRFMiddleware` (`Litestar(csrf_config=...)`)
   6. Inner `ExceptionHandlerMiddleware` (applies route/controller/router/app `exception_handlers`)
   7. Route handler execution (`guards` -> `before_request` -> dependencies & handler -> `after_request` -> `after_response`)

Because user `middleware=[...]` runs inside the per-route stack after `ASGIRouter` has matched the route, `scope["route_handler"]` and `scope["path_params"]` are already populated when your middleware's `handle()` method executes.

## Custom Middleware with `ASGIMiddleware` (Preferred)

Subclass `ASGIMiddleware` (`litestar.middleware.ASGIMiddleware`) for custom cross-cutting concerns (request IDs, timing, custom headers, tenant context).

- `ASGIMiddleware` defines no `__init__`, so subclasses can define their own `__init__` and are instantiated directly in `middleware=[TimingMiddleware()]`.
- **Statelessness requirement**: Litestar reuses the same `ASGIMiddleware` instance across all requests for a route. Never store per-request mutable state on `self`; store request data in `scope["state"]` (`connection.state`) or `contextvars.ContextVar`.
- `AbstractMiddleware` is **deprecated since Litestar 2.15** and emits `LitestarDeprecationWarning` when subclassed directly. Always use `ASGIMiddleware`.

### `ASGIMiddleware` Attributes and Hook

| Attribute / Method | Type & Default | Purpose |
| --- | --- | --- |
| `scopes` | `tuple[ScopeType, ...] = (ScopeType.HTTP, ScopeType.WEBSOCKET, ScopeType.ASGI)` | Restricts which ASGI scope types trigger `handle()`. |
| `exclude_path_pattern` | `str \| tuple[str, ...] \| None = None` | Regex pattern(s) matched against static `route_handler.paths` to skip routes at startup. |
| `exclude_opt_key` | `str \| None = None` | Route `opt` key; when truthy on `route_handler.opt`, the middleware is bypassed for that route. |
| `should_bypass_for_scope` | `Callable[[Scope], bool] \| None = None` | Runtime predicate evaluated per request against `Scope`; return `True` to bypass `handle()`. |
| `async def handle(self, scope, receive, send, next_app)` | `None` | Executes middleware logic and awaits `next_app(scope, receive, send)`. |

### `exclude_path_pattern` vs `should_bypass_for_scope` (Litestar 2.24 / 3.0)

In Litestar 2.24, `ASGIMiddleware` checks `exclude_path_pattern` against both static `route_handler.paths` and the runtime `scope["path"]`, emitting a deprecation warning whenever the two checks disagree (for example, matching file extensions like `r"\.css$"` on a parameterized route `/static/{file_path:path}`). Starting in Litestar 3.0, `exclude_path_pattern` will only be evaluated once against `route_handler.paths` when building the route stack.

- Use `exclude_path_pattern` with anchored regexes for **static route exclusions**: `exclude_path_pattern = ("^/health$", "^/metrics$", "^/schema")`.
- Use `should_bypass_for_scope` for **dynamic runtime checks** against `scope["path"]`, headers, or query strings.

```python
from __future__ import annotations

import time
from uuid import uuid4

from litestar import Litestar, get
from litestar.datastructures import MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send


def bypass_static_assets(scope: Scope) -> bool:
    return scope.get("path", "").endswith((".css", ".js", ".png", ".ico"))


class RequestTimingMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP,)
    exclude_path_pattern = ("^/health$", "^/metrics$", "^/schema")
    exclude_opt_key = "skip_timing"
    should_bypass_for_scope = staticmethod(bypass_static_assets)

    def __init__(self, header_name: str = "X-Process-Time-Ms") -> None:
        self.header_name = header_name

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        next_app: ASGIApp,
    ) -> None:
        start = time.perf_counter()
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers = MutableScopeHeaders.from_message(message=message)
                headers[self.header_name] = f"{elapsed_ms:.2f}"
                headers["X-Request-ID"] = request_id
            await send(message)

        await next_app(scope, receive, send_wrapper)


@get("/items")
async def list_items() -> list[str]:
    return ["item-1"]


@get("/health", opt={"skip_timing": True})
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[list_items, health],
    middleware=[RequestTimingMiddleware()],
)
```

## `DefineMiddleware` and `MiddlewareProtocol`

Use `DefineMiddleware(middleware, *args, **kwargs)` (`litestar.middleware.DefineMiddleware`) when wrapping:

- An `AbstractAuthenticationMiddleware` subclass
- A class implementing `MiddlewareProtocol` (`__init__(self, app: ASGIApp, ...)` and `async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None`)
- Any third-party ASGI middleware class or factory callable that accepts `app: ASGIApp` as a keyword argument

```python
from __future__ import annotations

from litestar import Litestar
from litestar.middleware import DefineMiddleware, MiddlewareProtocol
from litestar.types import ASGIApp, Receive, Scope, Send


class CustomHeaderProtocolMiddleware(MiddlewareProtocol):
    def __init__(self, app: ASGIApp, environment: str) -> None:
        self.app = app
        self.environment = environment

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})["environment"] = self.environment
        await self.app(scope, receive, send)


app = Litestar(
    route_handlers=[],
    middleware=[DefineMiddleware(CustomHeaderProtocolMiddleware, environment="production")],
)
```

## Built-in App-Level Middleware Configurations

These five configurations are passed directly as keyword arguments to `Litestar(...)`.

### `CORSConfig` (`litestar.config.cors.CORSConfig`)

Configures `CORSMiddleware` at the outer ASGI router boundary.

```python
from litestar import Litestar
from litestar.config.cors import CORSConfig

cors_config = CORSConfig(
    allow_origins=["https://app.example.com"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    allow_credentials=True,
    allow_origin_regex=r"^https://.*\.example\.com$",
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    max_age=600,
)

app = Litestar(route_handlers=[], cors_config=cors_config)
```

Defaults: `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=False`, `allow_origin_regex=None`, `expose_headers=[]`, `max_age=600`.

### `CSRFConfig` (`litestar.config.csrf.CSRFConfig`)

Protects unsafe HTTP methods using a double-submit HMAC token stored in a cookie and verified against a request header (or `_csrf_token` form field on `application/x-www-form-urlencoded` and `multipart/form-data` requests).

```python
import os

from litestar import Litestar, post
from litestar.config.csrf import CSRFConfig

csrf_config = CSRFConfig(
    secret=os.environ.get("CSRF_SECRET", "change-me-in-production"),
    cookie_name="csrftoken",
    cookie_path="/",
    header_name="x-csrftoken",
    cookie_secure=True,
    cookie_httponly=False,
    cookie_samesite="lax",
    cookie_domain=None,
    safe_methods={"GET", "HEAD", "OPTIONS"},
    exclude=["^/webhooks/"],
    exclude_from_csrf_key="exclude_from_csrf",
)


@post("/webhooks/stripe", exclude_from_csrf=True)
async def stripe_webhook(data: dict[str, object]) -> dict[str, str]:
    return {"received": str(data.get("id", ""))}


app = Litestar(route_handlers=[stripe_webhook], csrf_config=csrf_config)
```

Note: `CSRFConfig` uses `exclude_from_csrf_key` (default `"exclude_from_csrf"`), not `exclude_opt_key`.

### `AllowedHostsConfig` (`litestar.config.allowed_hosts.AllowedHostsConfig`)

Validates the `Host` / `X-Forwarded-Host` header and optionally redirects `www.<domain>` to `<domain>`. You can pass either an `AllowedHostsConfig` instance or a `list[str]` directly to `Litestar(allowed_hosts=...)`. Wildcard domains must be `"*"` or start with `"*."`.

```python
from litestar import Litestar
from litestar.config.allowed_hosts import AllowedHostsConfig
from litestar.enums import ScopeType

allowed_hosts_config = AllowedHostsConfig(
    allowed_hosts=["example.com", "*.example.com"],
    exclude=["^/health$"],
    exclude_opt_key="skip_allowed_hosts",
    scopes={ScopeType.HTTP, ScopeType.WEBSOCKET},
    www_redirect=True,
)

app = Litestar(route_handlers=[], allowed_hosts=allowed_hosts_config)
```

### `CompressionConfig` (`litestar.config.compression.CompressionConfig`)

Compresses HTTP responses larger than `minimum_size` bytes using `gzip` (built-in) or `brotli` (requires `litestar[brotli]`).

```python
from litestar import Litestar
from litestar.config.compression import CompressionConfig

compression_config = CompressionConfig(
    backend="brotli",
    minimum_size=500,
    brotli_quality=5,
    brotli_mode="text",
    brotli_lgwin=22,
    brotli_lgblock=0,
    brotli_gzip_fallback=True,
    gzip_compress_level=9,
    exclude=["^/metrics$", "^/events$"],
    exclude_opt_key="skip_compression",
)

app = Litestar(route_handlers=[], compression_config=compression_config)
```

### `ResponseCacheConfig` (`litestar.config.response_cache.ResponseCacheConfig`)

Configures route-level HTTP response caching backed by `app.stores.get(store)` (default store name `"response_cache"`). Individual routes opt in via `cache=True` (uses `default_expiration`), `cache=120` (seconds), or `cache=CACHE_FOREVER`.

```python
from litestar import Litestar, get
from litestar.config.response_cache import (
    CACHE_FOREVER,
    ResponseCacheConfig,
    default_cache_key_builder,
)
from litestar.stores.memory import MemoryStore
from litestar.types import HTTPScope


def cache_only_200(scope: HTTPScope, status_code: int) -> bool:
    return status_code == 200


response_cache_config = ResponseCacheConfig(
    default_expiration=60,
    key_builder=default_cache_key_builder,
    store="response_cache",
    cache_response_filter=cache_only_200,
)


@get("/catalog", cache=300)
async def get_catalog() -> list[str]:
    return ["sku-1", "sku-2"]


@get("/static-metadata", cache=CACHE_FOREVER)
async def get_metadata() -> dict[str, str]:
    return {"version": "1"}


app = Litestar(
    route_handlers=[get_catalog, get_metadata],
    response_cache_config=response_cache_config,
    stores={"response_cache": MemoryStore()},
)
```

## Built-in `.middleware` Property Configurations

These configs expose a `.middleware` property returning a `DefineMiddleware` wrapper to include in `middleware=[...]`.

### `RateLimitConfig` (`litestar.middleware.rate_limit.RateLimitConfig`)

Enforces fixed-window request quotas per client identifier using `app.stores.get(store)` (default `"rate_limit"`). `rate_limit` accepts `(unit, quota)` where `unit` is `"second"`, `"minute"`, `"hour"`, or `"day"`.

```python
from litestar import Litestar, Request
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.stores.memory import MemoryStore


async def identify_client(request: Request) -> str:
    user = request.scope.get("user")
    if user is not None:
        return f"user:{user.id}:{request.scope['path']}"
    client_host = request.client.host if request.client else "anonymous"
    return f"ip:{client_host}:{request.scope['path']}"


rate_limit_config = RateLimitConfig(
    rate_limit=("minute", 100),
    exclude=["^/health$", "^/schema"],
    exclude_opt_key="skip_rate_limit",
    identifier_for_request=identify_client,
    check_throttle_handler=None,
    set_rate_limit_headers=True,
    rate_limit_policy_header_key="RateLimit-Policy",
    rate_limit_remaining_header_key="RateLimit-Remaining",
    rate_limit_reset_header_key="RateLimit-Reset",
    rate_limit_limit_header_key="RateLimit-Limit",
    store="rate_limit",
)

app = Litestar(
    route_handlers=[],
    middleware=[rate_limit_config.middleware],
    stores={"rate_limit": MemoryStore()},
)
```

Note: The default `get_remote_address` reads `request.client.host` and does not parse `X-Forwarded-For` directly. Configure proxy header handling in your ASGI server (Granian/Uvicorn) or provide a custom `identifier_for_request`.

### `LoggingMiddlewareConfig` (`litestar.middleware.logging.LoggingMiddlewareConfig`)

Logs structured request and response fields while obfuscating sensitive headers and cookies.

```python
from litestar import Litestar
from litestar.middleware.logging import LoggingMiddlewareConfig

logging_middleware_config = LoggingMiddlewareConfig(
    exclude=["^/health$", "^/metrics$"],
    exclude_opt_key="skip_logging",
    include_compressed_body=False,
    logger_name="litestar",
    request_cookies_to_obfuscate={"session", "access_token"},
    request_headers_to_obfuscate={"Authorization", "X-API-KEY"},
    response_cookies_to_obfuscate={"session", "access_token"},
    response_headers_to_obfuscate={"Authorization", "X-API-KEY"},
    request_log_message="HTTP Request",
    response_log_message="HTTP Response",
    request_log_fields=("path", "method", "content_type", "headers", "query", "path_params"),
    response_log_fields=("status_code", "headers"),
)

app = Litestar(
    route_handlers=[],
    middleware=[logging_middleware_config.middleware],
)
```

### Session Middleware (`ServerSideSessionConfig` and `CookieBackendConfig`)

When you need `request.session` without `SessionAuth`, pass `session_config.middleware` to `middleware=[...]`. When pairing sessions with user authentication, pass `session_config` to `SessionAuth(session_backend_config=session_config, ...)` instead (see [auth-and-guards.md](auth-and-guards.md)).

```python
import os

from litestar import Litestar
from litestar.enums import ScopeType
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.stores.memory import MemoryStore

server_session_config = ServerSideSessionConfig(
    store="sessions",
    session_id_bytes=32,
    renew_on_access=True,
    key="session",
    max_age=86400 * 14,
    scopes={ScopeType.HTTP, ScopeType.WEBSOCKET},
    path="/",
    domain=None,
    secure=True,
    httponly=True,
    samesite="lax",
    exclude=["^/health$"],
    exclude_opt_key="skip_session",
)

cookie_session_config = CookieBackendConfig(
    secret=os.urandom(32),
    key="session",
    max_age=86400 * 14,
    scopes={ScopeType.HTTP, ScopeType.WEBSOCKET},
    path="/",
    domain=None,
    secure=True,
    httponly=True,
    samesite="lax",
    exclude=["^/health$"],
    exclude_opt_key="skip_session",
)

app = Litestar(
    route_handlers=[],
    middleware=[server_session_config.middleware],
    stores={"sessions": MemoryStore()},
)
```

## Authentication Middleware (`AbstractAuthenticationMiddleware`)

To populate `connection.user` and `connection.auth` for downstream guards and handlers, subclass `AbstractAuthenticationMiddleware` (`litestar.middleware.authentication`) and register it with `DefineMiddleware`:

```python
from __future__ import annotations

from uuid import UUID

from litestar import Litestar
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.middleware import DefineMiddleware
from litestar.middleware.authentication import (
    AbstractAuthenticationMiddleware,
    AuthenticationResult,
)
from litestar.security.jwt import Token


class JWTAuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(
        self,
        connection: ASGIConnection,
    ) -> AuthenticationResult:
        auth_header = connection.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise NotAuthorizedException("Missing Bearer token")
        token = Token.decode(
            encoded_token=auth_header.removeprefix("Bearer ").strip(),
            secret=connection.app.state.jwt_secret,
            algorithm="HS256",
        )
        user = await connection.app.state.user_service.get(UUID(token.sub))
        if user is None or not user.is_active:
            raise NotAuthorizedException("Invalid user")
        return AuthenticationResult(user=user, auth=token)


app = Litestar(
    route_handlers=[],
    middleware=[
        DefineMiddleware(
            JWTAuthMiddleware,
            exclude=["^/health$", "^/schema"],
            exclude_from_auth_key="exclude_from_auth",
        )
    ],
)
```

## Cross-References

- Native security backends (`JWTAuth`, `JWTCookieAuth`, `OAuth2PasswordBearerAuth`, `SessionAuth`) and `Guard` patterns: [auth-and-guards.md](auth-and-guards.md)
- Declarative route security policies (`SecurityPlugin`): [litestar-security](../../litestar-security/SKILL.md)
- Cloud Run / GKE IAP and proxy configuration: [litestar-app.md](../../litestar-deployment/references/litestar-app.md)

## Audited Source (Litestar 2.24.0)

- [`litestar/middleware/base.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/base.py)
- [`litestar/middleware/authentication.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/authentication.py)
- [`litestar/middleware/allowed_hosts.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/allowed_hosts.py)
- [`litestar/middleware/cors.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/cors.py)
- [`litestar/middleware/csrf.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/csrf.py)
- [`litestar/middleware/compression/middleware.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/compression/middleware.py)
- [`litestar/middleware/logging.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/logging.py)
- [`litestar/middleware/rate_limit.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/rate_limit.py)
- [`litestar/middleware/response_cache.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/response_cache.py)
- [`litestar/middleware/session/server_side.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/session/server_side.py)
- [`litestar/middleware/session/client_side.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/session/client_side.py)
