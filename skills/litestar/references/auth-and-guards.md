# Guards, `ASGIConnection`, and Native Security Backends

Guards are sync or async callables `(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None` that enforce authorization and raise on denial. Authentication belongs in `AbstractAuthenticationMiddleware` or a `litestar.security` backend (`JWTAuth`, `JWTCookieAuth`, `OAuth2PasswordBearerAuth`, `SessionAuth`) so identity is resolved once per connection.

## Choosing Between `litestar-security` and Native Guards

| Approach | When to Use | Core Primitives |
| --- | --- | --- |
| [`litestar-security`](../../litestar-security/SKILL.md) | Declarative route policies, immutable authorization snapshots, role/scope/tenant/capability helpers, or `CurrentUser` DI | `SecurityPlugin`, `SecurityConfig`, `auth=required(...)`, `CurrentUser[T]`, `Principal`, `SecurityContext`, `AuthorizationSnapshot` |
| Native `litestar.security` + `Guard` (this skill) | Built-in Litestar JWT / cookie / OAuth2 / session backends, custom `AbstractAuthenticationMiddleware`, or direct `guards=[...]` callables | `JWTAuth`, `JWTCookieAuth`, `OAuth2PasswordBearerAuth`, `SessionAuth`, `Token`, `ASGIConnection`, `Guard` |

## `ASGIConnection` Identity, State, and Session API

`ASGIConnection[HandlerT, UserT, AuthT, StateT]` (`litestar.connection.ASGIConnection`) is the common base class for `Request[UserT, AuthT, StateT]` and `WebSocket[UserT, AuthT, StateT]`. Every guard receives `ASGIConnection`, allowing the same guard callable to protect both HTTP and WebSocket handlers.

| Attribute / Method | Backing Scope Key | Behavior & Gotchas |
| --- | --- | --- |
| `connection.user` | `scope["user"]` | Typed as `UserT`. Raises `ImproperlyConfiguredException` if `"user"` is not in `scope` (no auth middleware ran or route bypassed auth middleware). |
| `connection.auth` | `scope["auth"]` | Typed as `AuthT` (e.g., `Token` for JWT backends, `dict[str, Any]` for `SessionAuth`). Raises `ImproperlyConfiguredException` if `"auth"` is not in `scope`. |
| `connection.session` | `scope["session"]` | Typed as `dict[str, Any]`. Raises `ImproperlyConfiguredException` if `"session"` is not in `scope`. |
| `connection.scope.get("user")` | `scope.get("user")` | Safe lookup returning `None` when auth middleware was skipped via `exclude_from_auth=True`. |
| `connection.state` | `scope["state"]` | Per-request `State` (`StateT`) view for sharing request-scoped data across middleware, guards, dependencies, and handlers. |
| `connection.set_session(value)` | `scope["session"]` | Replaces session data with a `dict[str, Any]` or `Empty`. |
| `connection.clear_session()` | `scope["session"]` | Sets `scope["session"] = Empty`, instructing the session middleware to clear server-side storage and expire the session cookie. |
| `connection.get_session_id()` | `scope["_session_id"]` | Returns `str \| None` when using server-side sessions. |
| `connection.route_handler` | `scope["route_handler"]` | The matched `HTTPRouteHandler`, `WebsocketRouteHandler`, or `ASGIRouteHandler`. |

## Guard Resolution, `opt` Metadata, and `exclude_from_auth`

### Additive Layering

Litestar resolves `guards` additively from outermost to innermost layer in `BaseRouteHandler.resolve_guards()`:

1. `Litestar(guards=[...])` (including any `guards` passed to `JWTAuth(..., guards=[...])`)
2. `Router(guards=[...])` (in router nesting order)
3. `Controller.guards = [...]`
4. `@get(..., guards=[...])` / `@websocket(..., guards=[...])`

All resolved guards run sequentially in `await route_handler.authorize_connection(connection)` before `before_request`, dependency resolution, or handler execution.

### Route `opt` Inspection

Route `opt` dictionaries merge across `app -> router -> controller -> route_handler`, where the innermost layer wins on key collisions. Arbitrary keyword arguments passed to route decorators (`@get("/reports", required_role="analyst")`) are merged into `route_handler.opt`. When `authorize_connection` invokes a guard, it passes a shallow copy of `route_handler` whose `.opt` is already merged.

```python
from __future__ import annotations

from litestar import Controller, get
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.handlers import BaseRouteHandler


async def requires_active_user(
    connection: ASGIConnection,
    route_handler: BaseRouteHandler,
) -> None:
    if route_handler.opt.get("exclude_from_auth"):
        return
    user = connection.scope.get("user")
    if user is None or not user.is_active:
        raise NotAuthorizedException("Authentication required")


async def requires_role(
    connection: ASGIConnection,
    route_handler: BaseRouteHandler,
) -> None:
    if route_handler.opt.get("exclude_from_auth"):
        return
    user = connection.scope.get("user")
    if user is None:
        raise NotAuthorizedException("Authentication required")
    required_role = route_handler.opt.get("required_role")
    if required_role and required_role not in user.roles:
        raise PermissionDeniedException(f"Missing required role: {required_role}")


class ReportsController(Controller):
    path = "/api/reports"
    guards = [requires_active_user, requires_role]
    opt = {"required_role": "viewer"}

    @get("/")
    async def list_reports(self) -> list[str]:
        return ["q1", "q2"]

    @get("/export", opt={"required_role": "admin"})
    async def export_reports(self) -> dict[str, str]:
        return {"status": "exported"}

    @get("/public-summary", exclude_from_auth=True)
    async def public_summary(self) -> dict[str, str]:
        return {"summary": "public"}
```

### Critical Gotcha: `exclude_from_auth` vs `guards`

Setting `opt={"exclude_from_auth": True}` (or `exclude_from_auth=True` on a route decorator) tells `AbstractAuthenticationMiddleware` to skip `authenticate_request()` for that route. **It does not skip `guards`:**

1. Because `AbstractAuthenticationMiddleware` is skipped, `"user"` and `"auth"` are never written to `connection.scope`.
2. Any guard attached at the `Litestar`, `Router`, or `Controller` level (including `JWTAuth(guards=[...])`) still runs for that route.
3. If that guard accesses `connection.user` directly instead of checking `route_handler.opt.get("exclude_from_auth")` or `connection.scope.get("user")`, Litestar raises `ImproperlyConfiguredException` (`500 Internal Server Error`) instead of allowing the public route.

Either scope `guards` to protected routers/controllers only, or check `route_handler.opt.get("exclude_from_auth")` at the top of app/controller-wide guards.

## Custom `AbstractAuthenticationMiddleware`

When integrating external identity providers (IAP, OIDC/JWKS, API keys, custom headers), subclass `AbstractAuthenticationMiddleware` (`litestar.middleware.authentication`) and return an `AuthenticationResult(user=..., auth=...)`.

```python
from __future__ import annotations

from uuid import UUID

from litestar import Litestar
from litestar.connection import ASGIConnection
from litestar.enums import HttpMethod, ScopeType
from litestar.exceptions import NotAuthorizedException
from litestar.middleware import DefineMiddleware
from litestar.middleware.authentication import (
    AbstractAuthenticationMiddleware,
    AuthenticationResult,
)
from litestar.security.jwt import Token


class BearerTokenAuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(
        self,
        connection: ASGIConnection,
    ) -> AuthenticationResult:
        auth_header = connection.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise NotAuthorizedException("Missing Bearer token")
        encoded = auth_header.removeprefix("Bearer ").strip()
        token = Token.decode(
            encoded_token=encoded,
            secret=connection.app.state.jwt_secret,
            algorithm="HS256",
        )
        user = await connection.app.state.user_service.get(UUID(token.sub))
        if user is None or not user.is_active:
            raise NotAuthorizedException("Invalid user")
        return AuthenticationResult(user=user, auth=token)


auth_middleware = DefineMiddleware(
    BearerTokenAuthMiddleware,
    exclude=["^/health$", "^/schema"],
    exclude_from_auth_key="exclude_from_auth",
    exclude_http_methods=[HttpMethod.OPTIONS, HttpMethod.HEAD],
    scopes={ScopeType.HTTP, ScopeType.WEBSOCKET},
)

app = Litestar(route_handlers=[], middleware=[auth_middleware])
```

`AbstractAuthenticationMiddleware.__init__` signature and defaults in Litestar 2.24:

- `app: ASGIApp`
- `exclude: str | list[str] | None = None` — regex path patterns to bypass authentication.
- `exclude_from_auth_key: str = "exclude_from_auth"` — `route_handler.opt` key that bypasses authentication on a route.
- `exclude_http_methods: Sequence[Method] | None = (HttpMethod.OPTIONS,)` — HTTP methods that bypass authentication.
- `scopes: Scopes | None = {ScopeType.HTTP, ScopeType.WEBSOCKET}` — ASGI scopes processed by the middleware.

## Built-in `litestar.security` Backends

Litestar ships four `AbstractSecurityConfig` implementations wired through `Litestar(on_app_init=[auth.on_app_init])`. All four share these base options:

- `retrieve_user_handler: Callable[[Any, ASGIConnection], SyncOrAsyncUnion[Any | None]]` — receives the decoded `auth` value (`Token` or session `dict`) and `ASGIConnection`; if it returns `None`, authentication fails with `NotAuthorizedException`.
- `guards: Iterable[Guard] | None = None` — appended to `app_config.guards` (runs on all routes unless guarded against `exclude_from_auth`).
- `exclude: str | list[str] | None = None` — regex path patterns excluded from authentication middleware.
- `exclude_opt_key: str = "exclude_from_auth"` — `opt` key that skips authentication middleware on a route.
- `exclude_http_methods: Sequence[Method] | None = ["OPTIONS", "HEAD"]`.
- `scopes: Scopes | None = None` — defaults to `{ScopeType.HTTP, ScopeType.WEBSOCKET}` inside the middleware.
- `route_handlers: Iterable[ControllerRouterHandler] | None = None`, `dependencies: Dependencies | None = None`, `type_encoders: TypeEncodersMap | None = None`.

### `Token` (`litestar.security.jwt.Token`)

Requires `litestar[jwt]` (`pyjwt` and `cryptography`).

- Fields: `exp: datetime` (must be in the future), `sub: str` (non-empty), `iat: datetime` (defaults to UTC `datetime.now`, must be `<= now`), `iss: str | None = None`, `aud: str | Sequence[str] | None = None`, `jti: str | Sequence[str] | None = None`, `extras: dict[str, Any] = field(default_factory=dict)`. Any custom claims in the JWT payload are automatically collected into `token.extras`.
- Methods:
  - `Token.decode(encoded_token, secret, algorithm, audience=None, issuer=None, require_claims=None, verify_exp=True, verify_nbf=True, strict_audience=False) -> Self`
  - `Token.decode_payload(encoded_token, secret, algorithms, issuer=None, audience=None, options=None) -> dict[str, Any]`
  - `token.encode(secret, algorithm) -> str`

### `JWTAuth` and `JWTCookieAuth` (`litestar.security.jwt`)

`JWTAuth[UserType, TokenT]` authenticates requests via a header (`Authorization: Bearer <token>`) and registers the OpenAPI bearer security scheme. `JWTCookieAuth[UserType, TokenT]` checks the header first and falls back to an HTTP-only cookie, setting both on `.login()`.

```python
from __future__ import annotations

from datetime import timedelta
import os
from typing import Any
from uuid import UUID

from litestar import Litestar, Request, Response, get, post
from litestar.connection import ASGIConnection
from litestar.security.jwt import JWTAuth, JWTCookieAuth, Token
import msgspec


class User(msgspec.Struct):
    id: UUID
    email: str
    roles: list[str]
    is_active: bool = True


async def retrieve_user_handler(
    token: Token,
    connection: ASGIConnection[Any, Any, Any, Any],
) -> User | None:
    user_service = connection.app.state.user_service
    user = await user_service.get(UUID(token.sub))
    if user is None or not user.is_active:
        return None
    return user


async def is_token_revoked(
    token: Token,
    connection: ASGIConnection[Any, Any, Any, Any],
) -> bool:
    if token.jti is None or not isinstance(token.jti, str):
        return False
    denylist = connection.app.stores.get("revoked_tokens")
    return await denylist.exists(token.jti)


jwt_auth = JWTAuth[User, Token](
    retrieve_user_handler=retrieve_user_handler,
    revoked_token_handler=is_token_revoked,
    token_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
    algorithm="HS256",
    auth_header="Authorization",
    default_token_expiration=timedelta(hours=12),
    accepted_audiences=["https://api.example.com"],
    accepted_issuers=["https://auth.example.com"],
    require_claims=["sub", "exp", "iat", "jti"],
    verify_expiry=True,
    verify_not_before=True,
    strict_audience=True,
    exclude=["^/login$", "^/health$", "^/schema"],
)

jwt_cookie_auth = JWTCookieAuth[User, Token](
    retrieve_user_handler=retrieve_user_handler,
    token_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
    key="access_token",
    path="/",
    domain=None,
    secure=True,
    samesite="lax",
    exclude=["^/login$", "^/health$", "^/schema"],
)


@post("/login", exclude_from_auth=True)
async def login(data: dict[str, str]) -> Response[User]:
    user = User(id=UUID(int=1), email=data["email"], roles=["member"])
    return jwt_auth.login(
        identifier=str(user.id),
        response_body=user,
        token_issuer="https://auth.example.com",
        token_audience="https://api.example.com",
        token_unique_jwt_id="jti-001",
        token_extras={"roles": user.roles},
    )


@get("/me")
async def get_me(request: Request[User, Token, Any]) -> User:
    return request.user


app = Litestar(
    route_handlers=[login, get_me],
    on_app_init=[jwt_auth.on_app_init],
)
```

Key `JWTAuth` / `JWTCookieAuth` options in Litestar 2.24:

- `revoked_token_handler: Callable[[Any, ASGIConnection], SyncOrAsyncUnion[bool]] | None = None` — invoked after decoding and before `retrieve_user_handler`; returning `True` raises `NotAuthorizedException("Token has been revoked")`.
- `accepted_audiences: Sequence[str] | None = None`, `accepted_issuers: Sequence[str] | None = None`, `require_claims: Sequence[str] | None = None`.
- `verify_expiry: bool = True`, `verify_not_before: bool = True`.
- `strict_audience: bool = False` — when `True`, `accepted_audiences` must have exactly one entry and the token's `aud` claim is validated as a single string (RFC 7519 strict mode).
- `token_cls: type[TokenT] = Token` — custom `Token` subclass for typed extra claims.

### `OAuth2PasswordBearerAuth` (`litestar.security.jwt`)

Configures an OpenAPI `OAuth2` password flow security scheme (`token_url`) and returns a standard `OAuth2Login` response body (`access_token`, `token_type="bearer"`, `refresh_token`, `expires_in`) from `.login()` while also setting the header and `HttpOnly` cookie:

```python
from __future__ import annotations

import os
from typing import Any

from litestar import Response, post
from litestar.security.jwt import OAuth2Login, OAuth2PasswordBearerAuth, Token

oauth2_auth = OAuth2PasswordBearerAuth[User, Token](
    retrieve_user_handler=retrieve_user_handler,
    token_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
    token_url="/auth/token",
    oauth_scopes={"read:items": "Read items", "write:items": "Modify items"},
    exclude=["^/auth/token$", "^/schema"],
)


@post("/auth/token", exclude_from_auth=True)
async def issue_oauth_token() -> Response[OAuth2Login]:
    return oauth2_auth.login(
        identifier="00000000-0000-0000-0000-000000000001",
        send_token_as_response_body=True,
    )
```

### `SessionAuth` (`litestar.security.session_auth.SessionAuth`)

`SessionAuth[UserType, BaseSessionBackendT]` wraps either `ServerSideSessionConfig` (recommended for production with Redis/Valkey/SQL stores) or `CookieBackendConfig` (AES-GCM encrypted client-side cookies; requires `secret` of 16, 24, or 32 bytes). `SessionAuth.on_app_init` installs both the session middleware and `SessionAuthMiddleware` in the right order.

```python
from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from litestar import Litestar, Request, post
from litestar.connection import ASGIConnection
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.security.session_auth import SessionAuth
from litestar.stores.memory import MemoryStore


async def retrieve_session_user(
    session: dict[str, Any],
    connection: ASGIConnection[Any, Any, Any, Any],
) -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return await connection.app.state.user_service.get(UUID(user_id))


server_session_config = ServerSideSessionConfig(
    store="sessions",
    key="session",
    max_age=86400 * 14,
    renew_on_access=True,
    secure=True,
    httponly=True,
    samesite="lax",
)

cookie_session_config = CookieBackendConfig(
    secret=os.urandom(32),
    key="session",
    max_age=86400 * 14,
    secure=True,
    httponly=True,
    samesite="lax",
)

session_auth = SessionAuth[User, ServerSideSessionConfig](
    retrieve_user_handler=retrieve_session_user,
    session_backend_config=server_session_config,
    exclude=["^/session/login$", "^/health$", "^/schema"],
)


@post("/session/login", exclude_from_auth=True)
async def session_login(request: Request[Any, Any, Any], data: dict[str, str]) -> dict[str, str]:
    request.set_session({"user_id": data["user_id"]})
    return {"status": "logged_in"}


@post("/session/logout")
async def session_logout(request: Request[User, dict[str, Any], Any]) -> dict[str, str]:
    request.clear_session()
    return {"status": "logged_out"}


app = Litestar(
    route_handlers=[session_login, session_logout],
    on_app_init=[session_auth.on_app_init],
    stores={"sessions": MemoryStore()},
)
```

## Membership / Multi-Tenant Guard

Verify tenant membership in a guard using server-resolved path or user context — never trust an unverified client tenant header or payload field:

```python
from __future__ import annotations

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.handlers import BaseRouteHandler


async def requires_workspace_membership(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if user is None:
        raise NotAuthorizedException("Authentication required")
    if user.is_superuser:
        return
    workspace_id = connection.path_params.get("workspace_id")
    if workspace_id is None:
        raise PermissionDeniedException("Missing workspace_id")
    member_service = connection.app.state.workspace_member_service
    if not await member_service.is_member(workspace_id, user.id):
        raise PermissionDeniedException("Not a workspace member")
```

## WebSocket Authentication and Guards

WebSocket handshakes are HTTP upgrade requests that carry headers and cookies, exposed on `connection.headers` and `connection.cookies`. `AbstractAuthenticationMiddleware`, `JWTAuth`, `JWTCookieAuth`, and `SessionAuth` all include `ScopeType.WEBSOCKET` in their default `scopes`.

Choose the credential transport that matches the client:

| Client | Preferred Transport |
| --- | --- |
| Browser `WebSocket` API (same-origin / cookie-enabled) | `JWTCookieAuth` or `SessionAuth` (`HttpOnly`, `Secure` cookie) |
| Browser `WebSocket` without cookies | Short-lived, single-use query token or first authenticated message |
| Non-browser client (CLI, service-to-service, mobile native) | `Authorization: Bearer <token>` or explicit header |

The browser `WebSocket` constructor cannot set arbitrary HTTP headers. Do not generalize that browser API limitation to non-browser WebSocket clients, and avoid long-lived query tokens because URLs are recorded in access logs and telemetry.

### Browser-Compatible Cookie Guard (Standalone)

When a WebSocket route uses a dedicated cookie or custom handshake check outside app-wide auth middleware, raise `WebSocketException` with private-use close codes (`4001` for authentication failure, `4003` for authorization failure):

```python
from __future__ import annotations

from uuid import UUID

from litestar.connection import ASGIConnection
from litestar.exceptions import WebSocketException
from litestar.handlers import BaseRouteHandler
from litestar.security.jwt import Token


async def requires_websocket_auth(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    token_str = connection.cookies.get("access_token")
    if not token_str:
        raise WebSocketException(code=4001, detail="Missing token")
    try:
        token = Token.decode(
            encoded_token=token_str,
            secret=connection.app.state.jwt_secret,
            algorithm="HS256",
        )
    except Exception as exc:
        raise WebSocketException(code=4001, detail="Invalid token") from exc
    user = await connection.app.state.user_service.get(UUID(token.sub))
    if user is None or not user.is_active:
        raise WebSocketException(code=4001, detail="Unauthorized")
    connection.scope["user"] = user
    connection.scope["auth"] = token
```

### Workspace, Subject, and Global Stream Guards

```python
from __future__ import annotations

from litestar import Controller
from litestar.connection import ASGIConnection
from litestar.exceptions import WebSocketException
from litestar.handlers import BaseRouteHandler


async def requires_websocket_workspace_member(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    if getattr(user, "is_superuser", False):
        return
    workspace_id = connection.path_params.get("workspace_id")
    if workspace_id is None:
        raise WebSocketException(code=4003, detail="Missing workspace_id")
    member_service = connection.app.state.workspace_member_service
    if not await member_service.is_member(workspace_id, user.id):
        raise WebSocketException(code=4003, detail="Forbidden")


async def requires_websocket_user_subject(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    user_id = connection.path_params.get("user_id")
    if str(user.id) != str(user_id):
        raise WebSocketException(code=4003, detail="Forbidden")


async def requires_websocket_global_access(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    if not getattr(user, "is_superuser", False):
        raise WebSocketException(code=4003, detail="Forbidden")


class WorkspaceStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_workspace_member]


class UserStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_user_subject]


class GlobalStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_global_access]
```

| Close Code | Meaning | Guards |
| --- | --- | --- |
| `4001` | Authentication failure — missing/invalid token or inactive user | `requires_websocket_auth` and any guard when `user is None` |
| `4003` | Authorization failure — not a workspace member, wrong subject, or insufficient role | `requires_websocket_workspace_member`, `requires_websocket_user_subject`, `requires_websocket_global_access` |

## Cross-References

- Declarative policy plugin (`SecurityPlugin`): [litestar-security](../../litestar-security/SKILL.md)
- ASGI middleware ordering and built-in middleware configs: [middleware.md](middleware.md)
- WebSocket handler and stream patterns: [websockets.md](websockets.md)
- RealtimeEvent contract and publisher: [channels-and-sse.md](channels-and-sse.md)
- Exception hierarchy and RFC 9457 Problem Details: [exceptions.md](exceptions.md)

## Audited Source (Litestar 2.24.0)

- [`litestar/connection/base.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/connection/base.py)
- [`litestar/handlers/base.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/handlers/base.py)
- [`litestar/middleware/authentication.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/middleware/authentication.py)
- [`litestar/security/jwt/auth.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/security/jwt/auth.py)
- [`litestar/security/jwt/token.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/security/jwt/token.py)
- [`litestar/security/session_auth/auth.py`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/security/session_auth/auth.py)
