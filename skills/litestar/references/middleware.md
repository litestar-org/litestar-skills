# Middleware

Use `AbstractMiddleware` for cross-cutting concerns: timing, request IDs, structured logging, custom auth. Scope-filter to HTTP-only and exclude noise endpoints.

## Pattern

```python
from __future__ import annotations

import time

from litestar.middleware import AbstractMiddleware
from litestar.types import Receive, Scope, Send
from litestar.enums import ScopeType
import structlog


logger = structlog.get_logger()


class TimingMiddleware(AbstractMiddleware):
    scopes = {ScopeType.HTTP}              # HTTP only — skip WebSocket
    exclude = ["/health", "/metrics"]      # paths to skip entirely

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send,
    ) -> None:
        start = time.perf_counter()
        await self.app(scope, receive, send)
        duration = time.perf_counter() - start
        logger.info("request_complete", path=scope["path"], duration_ms=duration * 1000)
```

## Scope Filtering

| `scopes={...}` | Effect |
|---|---|
| `{ScopeType.HTTP}` | HTTP requests only (skip WS) |
| `{ScopeType.WEBSOCKET}` | WebSocket only |
| `{ScopeType.HTTP, ScopeType.WEBSOCKET}` | Both (default) |

## `exclude` Pattern

`exclude` accepts a list of regex patterns matched against `scope["path"]`. Use it for health checks, metrics, and other paths that shouldn't get the middleware's overhead:

```python
class StructuredLoggingMiddleware(AbstractMiddleware):
    scopes = {ScopeType.HTTP}
    exclude = ["^/health$", "^/metrics$", "^/schema"]
```

## Registration

```python
app = Litestar(
    route_handlers=[...],
    middleware=[TimingMiddleware, StructuredLoggingMiddleware],
)
```

Order matters — middleware wraps outermost-first. The first entry sees the request first and the response last.

## Auth Middleware (auto-loading user onto `connection.user`)

For JWT or IAP auth, prefer `AbstractAuthenticationMiddleware`:

```python
from litestar.middleware.authentication import AbstractAuthenticationMiddleware, AuthenticationResult


class JWTAuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, connection):
        token = connection.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token:
            return AuthenticationResult(user=None, auth=None)
        decoded = Token.decode(token, secret=settings.app.secret_key, algorithm="HS256")
        user = await user_service.get(UUID(decoded.sub))
        return AuthenticationResult(user=user, auth=decoded)
```

This populates `connection.user` and `connection.auth` so Guards can read them without re-decoding.

## Cross-references

- Guards consume `connection.user` set by auth middleware: [guards.md](guards.md)
- IAP middleware for Cloud Run / GKE: [deployment.md](deployment.md)
