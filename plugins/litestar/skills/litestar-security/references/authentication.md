# litestar-security — Authentication Reference

Authentication policy answers *who is calling*. It compiles once, at route
registration, into both runtime admission and the OpenAPI security projection.

## Credential Slots

A credential slot owns a physical transport location — a cookie, a header, a
query parameter. Slot behavior is deliberately strict:

- A presented credential that is malformed or invalid is **terminal**. It is
  never downgraded to "absent" in order to unlock a weaker alternative.
- When more than one credential succeeds, all must resolve to the **same
  subject**.
- Credential-granted scopes, roles, capabilities, tenant roles, tenant IDs, and resource
  permissions **intersect** rather than union.

## Policy Helpers

| Helper | Meaning |
| --- | --- |
| `public()` | No authentication. Also excluded from native CSRF. |
| `required()` | Any configured mechanism |
| `required("session")` | That named mechanism |
| `any_of("session", "api-key")` | At least one of the named mechanisms |
| `all_of("api-key", "service-jwt")` | All named mechanisms, same subject |
| `at_least(2, "session", "api-key", "service-jwt")` | N of M |
| `optional(policy)` | Authenticate when credentials are present, do not require them |
| `exclude()` | Bypass authentication; leaves Litestar's native CSRF middleware untouched |
| `mechanism("oauth", "read:user")` | Select a named mechanism with requested provider scopes |

All take mechanism names (`str` or `MechanismRequirement`) — never
authorization predicates.

## Ownership Layers

Policy resolves through Litestar's native ownership layers, nearest owner
first: handler `auth=` → controller (`SecureController` / `PublicController` or
`opt`) → router `opt` → application `opt`.

Subclass `SecureController` or `PublicController` for application controllers;
both compile their typed `auth` attribute into `opt["auth"]`, and a
handler-level `auth=` still overrides them:

```python
from typing import ClassVar

from litestar import Litestar, Router, get
from litestar_security import (
    AuthenticationPolicy,
    PublicController,
    SecureController,
    SecurityConfig,
    SecurityPlugin,
    public,
    required,
)


class SystemController(PublicController):
    path = "/health"

    @get("/")
    async def index(self) -> dict[str, str]:
        return {"status": "ok"}


class AccountController(SecureController):
    path = "/accounts"
    auth: ClassVar[AuthenticationPolicy] = required("session")


api_router = Router(
    path="/api",
    route_handlers=[AccountController],
    opt={"auth": required()},
)

app = Litestar(
    route_handlers=[SystemController, api_router],
    plugins=[SecurityPlugin(SecurityConfig())],
)
```

Custom controller class attributes on a plain `Controller` are **not**
propagated by Litestar — use `SecureController` / `PublicController` for
application controllers, and reserve `opt = {"auth": ...}` for `Router`,
`Litestar`, or third-party controllers that cannot subclass `SecureController`.

### Implicit Defaults

| Situation | Effective policy |
| --- | --- |
| Mechanisms configured, no inherited policy | `required()` |
| No mechanisms configured | `public()` |

The implicit `required()` is what makes third-party routes answer `401`; see
[Composition](composition.md).

## Non-HTTP Handlers

The `auth` policy also compiles for WebSocket and raw ASGI handlers. See
[WebSockets](websockets.md) for the connect-token pattern.

## CSRF Interaction

Browser sessions require native CSRF coverage, derived automatically for
session-capable policies.

- `auth=public()` excludes a stateless route from native CSRF.
- A public handler that establishes cookie-authenticated state (a login route)
  must declare `csrf_required=True`. This key is HTTP-only.
- `auth=exclude()` (along with `SecurityConfig(exclude=[...])` and
  `exclude_from_auth=True`) derives no CSRF demand from default mechanisms and
  writes no native CSRF exclusion either, leaving the route to Litestar's own
  CSRF middleware unless `csrf_required=True` is declared.
- A native CSRF exclusion key such as `exclude_from_csrf=True` is accepted only
  when the derived policy is not session-capable.

## OpenAPI Projection

`auth` drives the OpenAPI security requirements. Litestar's `security=`
parameter is reserved for that projection — do not hand-write it.

Schema endpoints are recognized by the handler Litestar generated for them, not
by URL. An application route is authenticated by its own `auth` even when it
sits under the OpenAPI base path, so `path="/api"` on `OpenAPIConfig` never
relaxes `/api/orders`. To serve documentation from application handlers,
declare `opt={"auth": public()}` on the router or controller that owns them.

## Status Codes

| Outcome | Status |
| --- | --- |
| Authentication failure | `401` |
| Guard denial | `403` |
| Verification unavailable | `503` (fails closed) |

## Cross-References

- **[Authorization](authorization.md)** — the `guards=[...]` axis.
- **[Composition](composition.md)** — excluding routes registered by other plugins.
- **[Providers](providers.md)** — configuring the mechanisms these policies name.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/authentication.rst>
