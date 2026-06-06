# Middleware

Use `ASGIMiddleware` for cross-cutting concerns: timing, request IDs, structured logging, custom auth. Scope-filter to HTTP-only and exclude noise endpoints.

## Pattern

```python
from __future__ import annotations

import time

from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send
import structlog


logger = structlog.get_logger()


class TimingMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP,)                   # HTTP only; skip WebSocket
    exclude_path_pattern = ("/health", "/metrics")

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp,
    ) -> None:
        start = time.perf_counter()
        await next_app(scope, receive, send)
        duration = time.perf_counter() - start
        logger.info("request_complete", path=scope["path"], duration_ms=duration * 1000)
```

## Scope Filtering

| `scopes=(...)` | Effect |
| --- | --- |
| `(ScopeType.HTTP,)` | HTTP requests only (skip WS) |
| `(ScopeType.WEBSOCKET,)` | WebSocket only |
| `(ScopeType.HTTP, ScopeType.WEBSOCKET)` | Both |

## Skip Patterns

`exclude_path_pattern` accepts regex patterns matched against `scope["path"]`; `exclude_opt_key` skips handlers that set a matching `opt` key. Use these for health checks, metrics, and other paths that shouldn't get the middleware's overhead:

```python
class StructuredLoggingMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP,)
    exclude_path_pattern = ("^/health$", "^/metrics$", "^/schema")
    exclude_opt_key = "skip_access_log"
```

## Registration

```python
app = Litestar(
    route_handlers=[...],
    middleware=[TimingMiddleware(), StructuredLoggingMiddleware()],
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

- Guards consume `connection.user` set by auth middleware: [guards.md](../../litestar-auth-guards/references/guards.md)
- IAP middleware for Cloud Run / GKE: [litestar-app.md](../../litestar-deployment/references/litestar-app.md)
