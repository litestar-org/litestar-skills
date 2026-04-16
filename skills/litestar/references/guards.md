# Guards (Authentication & Authorization)

Guards are sync or async callables `(connection, route_handler) -> None` that raise on denial. Apply at Controller class level for shared policy, route level for per-handler exceptions.

## Basic Auth Guard

```python
from __future__ import annotations

from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers import BaseRouteHandler


async def requires_active_user(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    if not connection.user or not connection.user.is_active:
        raise PermissionDeniedException("Authentication required")


async def requires_superuser(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    if not connection.user or not connection.user.is_superuser:
        raise PermissionDeniedException("Superuser permission required")
```

Apply at Controller level:

```python
class AdminController(Controller):
    path = "/api/admin"
    guards = [requires_active_user, requires_superuser]
```

## JWT Auth (Bearer Token)

```python
from litestar.security.jwt import Token

async def requires_jwt_auth(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    auth = connection.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise PermissionDeniedException("Missing token")
    try:
        token = Token.decode(
            encoded_token=auth.removeprefix("Bearer "),
            secret=settings.app.secret_key,
            algorithm="HS256",
        )
    except Exception as exc:
        raise PermissionDeniedException("Invalid token") from exc
    connection.state.user_id = token.sub
```

For JWT auth as middleware (auto-loading the user onto `connection.user`), see [middleware.md](middleware.md).

## Membership / Multi-tenant Guard

```python
async def requires_workspace_membership(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    user = connection.user
    if user is None:
        raise PermissionDeniedException("Unauthorized")
    if user.is_superuser:
        return
    workspace_id = connection.path_params.get("workspace_id")
    if not await workspace_member_service.is_member(workspace_id, user.id):
        raise PermissionDeniedException("Not a workspace member")
```

## WebSocket Auth (query-param JWT)

WS handshakes can't carry HTTP `Authorization` headers — pass the JWT as a query param:

```python
from litestar.exceptions import WebSocketException


async def requires_websocket_auth(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    token_str = connection.query_params.get("token")
    if not token_str:
        raise WebSocketException(code=4001, detail="Missing token")
    try:
        token = Token.decode(token_str, secret=settings.app.secret_key, algorithm="HS256")
    except Exception as exc:
        raise WebSocketException(code=4001, detail="Invalid token") from exc
    user = await user_service.get(UUID(token.sub))
    if user is None or not user.is_active:
        raise WebSocketException(code=4001, detail="Unauthorized")
    connection.state.user = user
```

WS error codes:

- `4001` — Auth failure (missing/invalid token, inactive user)
- `4003` — Authorization failure (not a member, wrong subject)

## Layering Guards

```python
class WorkspaceController(Controller):
    guards = [requires_active_user, requires_workspace_membership]  # shared

    @get("/admin", guards=[requires_superuser])  # adds an extra check
    async def admin_view(self) -> dict: ...
```

## Cross-references

- WebSocket-specific guard composition: [websockets.md](websockets.md)
- Auto-loading users via middleware: [middleware.md](middleware.md)
- Custom exceptions for permission denials: [exceptions.md](exceptions.md)
