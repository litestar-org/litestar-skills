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

For JWT auth as middleware (auto-loading the user onto `connection.user`), see [middleware.md](../../litestar-middleware/references/middleware.md).

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

WS handshakes can't carry HTTP `Authorization` headers — pass the JWT as a query param.

### Auth guard (token + user load)

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

### Membership guard (workspace-scoped)

Verifies the authenticated user is a member of the workspace in the path. Superusers bypass the
membership check. Adapted from `_websocket.py:L72–105`.

```python
async def requires_websocket_workspace_member(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    if has_full_access_role(user):
        return
    workspace_id = connection.path_params.get("workspace_id")
    if workspace_id is None:
        raise WebSocketException(code=4003, detail="Missing workspace_id")
    is_member = await workspace_member_service.is_member(workspace_id, user.id)
    if not is_member:
        raise WebSocketException(code=4003, detail="Forbidden")
```

### Subject guard (user-scoped)

Restricts a user stream subscription to the authenticated subject — the `user_id` path param must
match the token user. Adapted from `_websocket.py:L108–121`.

```python
async def requires_websocket_user_subject(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    user_id = connection.path_params.get("user_id")
    if str(user.id) != str(user_id):
        raise WebSocketException(code=4003, detail="Forbidden")
```

### Global-access guard

Allows only users with a full-access role (e.g., admin / superuser). Adapted from
`_websocket.py:L124–133`.

```python
async def requires_websocket_global_access(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")
    if not has_full_access_role(user):
        raise WebSocketException(code=4003, detail="Forbidden")
```

WS close-code convention — `requires_websocket_workspace_member`, `requires_websocket_user_subject`,
and `requires_websocket_global_access` all raise `4003` on authz failure; all guards raise `4001`
on missing/invalid auth state:

| Code | Meaning | Guards |
| --- | --- | --- |
| `4001` | Auth failure — missing/invalid token or inactive user | all guards |
| `4003` | Authz failure — not a member, wrong subject, or insufficient role | workspace / subject / global |

## Layering Guards

Compose guards per scope — one controller (or handler) per stream type:

```python
class WorkspaceStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_workspace_member]


class UserStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_user_subject]


class GlobalStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_global_access]
```

Contrast with HTTP-only controllers that use `requires_active_user` + `requires_workspace_membership`
— WS controllers always start with `requires_websocket_auth` because the HTTP middleware auth
stack is bypassed for WebSocket connections.

## Cross-references

- WebSocket-specific guard composition: [websockets.md](../../litestar-realtime/references/websockets.md)
- RealtimeEvent contract and publisher: [realtime-events.md](../../litestar-realtime/references/realtime-events.md)
- Auto-loading users via middleware: [middleware.md](../../litestar-middleware/references/middleware.md)
- Custom exceptions for permission denials: [exceptions.md](../../litestar-exceptions/references/exceptions.md)
