---
name: litestar-security
description: "Auto-activate for litestar_security, SecurityPlugin, SecurityConfig, CurrentUser, Principal, SecurityContext, requires_role, requires_scope, requires_authenticated, requires_tenant, or requires_capability. Not for raw auth guards alone — use litestar-auth-guards."
---

# Litestar Security

`litestar-security` v0.3.0 is a comprehensive, declarative authentication and authorization framework for Litestar applications. It provides unified session management, local user auth, Multi-Factor Authentication (MFA), WebAuthn/Passkeys, OAuth/OIDC, and browser security hardening (Content Security Policy).

## Code Style Rules

- **Use CurrentUser[T] for Handler Injection:** Annotate route handler parameters with `NamedDependency[CurrentUser[UserType]]` or `CurrentUser[UserType]` to inject the authenticated user model.
- **Identify via Principal:** Use `Principal` to reference the user's stable envelope identity (e.g. `principal.id`).
- **Use Composable Authorization Predicates:** Protect endpoints using built-in guards returned by `requires_role("admin")`, `requires_scope("read")`, `requires_tenant()`, `requires_capability("write")`.
- **Authorize via Snapshots:** Business authorization logic reads the `AuthorizationSnapshot` resolved from the configured `authorization_resolver`. Never perform raw SQL queries inside route guards to resolve roles.
- **Secure WebSockets with Connect Tokens:** Require WebSocket connections to authorize via short-lived connect tokens issued by `WebSocketConnectTokenIssuer`.
- **Apply Stable Encryption Keys:** When configuring MFA or Passkeys, ensure sensitive attributes (such as TOTP secrets) are backed by a stable key/secret protector.

## Quick Reference

### Plugin Registration

```python
from litestar import Litestar
from litestar_security import SecurityConfig, SecurityPlugin

security_config = SecurityConfig(
    slots=[...],
    mechanisms=[...],
    authorization_resolver=my_auth_resolver,
)

app = Litestar(
    route_handlers=[...],
    plugins=[SecurityPlugin(config=security_config)],
)
```

### Composed Authorization Guards

Apply guards returned by predicate functions to Controllers or route handlers:

```python
from litestar import Controller, get
from litestar_security import requires_role, requires_scope, all_of, any_of


class AdminController(Controller):
    path = "/admin"
    guards = [requires_role("admin")]

    @get("/records", guards=[any_of(requires_scope("read:all"), requires_scope("read:records"))])
    async def list_records(self) -> list[Record]: ...
```

### Reserved Dependency Names

The plugin registers the following dependencies. Do not shadow them in your application:

| Key | Type | Use |
| --- | --- | --- |
| `principal` | `Principal` | Holds user ID, display name, and active user model |
| `security_context` | `SecurityContext` | Holds active session, evidence, snapshot, and restrictions |
| `current_user` | `CurrentUser[User]` | Convience shortcut for the attached user model |
| `websocket_connect_tokens` | `WebSocketConnectTokenService` | WebSocket connection token manager |

### Client-Side CSP Nonces

Retrieve nonces for script or style tags in templates:

```python
from litestar_security import csp_nonce
```

## Workflow

### Step 1: Define User and Principal

Your user model will represent the application user. At login or request authentication, it is wrapped in a `Principal(id="user_id", user=user_instance)`.

### Step 2: Implement the Authorization Resolver

Write a callable that takes the authenticated `Principal` and returns an `AuthorizationSnapshot` containing their granted roles, scopes, capabilities, and tenants.

```python
from litestar_security import AuthorizationSnapshot


async def resolve_user_authorization(principal: Principal) -> AuthorizationSnapshot:
    if not principal.is_authenticated:
        return AuthorizationSnapshot()
    user = principal.require_user()
    return AuthorizationSnapshot(
        roles=frozenset(user.roles),
        scopes=frozenset(user.scopes),
    )
```

### Step 3: Define Slots and Authentication Mechanisms

Configure the slots (`CredentialSlot`) and mechanisms (`AuthenticationMechanism`) that your application supports (e.g., sessions, API keys, bearer tokens).

### Step 4: Register the SecurityPlugin

Add `SecurityPlugin(config=SecurityConfig(...))` to your Litestar application plugins.

### Step 5: Secure Handlers

Use guards on route handlers and inject `CurrentUser` to access the authenticated user safely.

## Guardrails

- **Do not shadow reserved dependencies:** Avoid naming your custom providers `principal`, `security_context`, `current_user`, or `websocket_connect_tokens`.
- **Do not perform I/O in predicates:** Composable guards (such as `requires_role`) evaluate synchronously against `AuthorizationSnapshot`. If database checks are required, implement them in the `authorization_resolver` which runs once per request.
- **WebSocket authentication must use connect tokens:** The browser WebSocket API cannot send custom headers. Generate a token via `issue_websocket_connect_token()` over an HTTP endpoint, and pass it to the WebSocket handshake query.
- **MFA routes require a recovery-code pepper:** Registering MFA routes without providing `recovery_peppers` and a `login_methods` store will raise `ImproperlyConfiguredException` during startup.

## Validation Checkpoint

- [ ] `SecurityPlugin` is registered in application `plugins`.
- [ ] Custom `authorization_resolver` is configured and returns an `AuthorizationSnapshot`.
- [ ] No handler manually queries database tables to perform authorization checks.
- [ ] Handler parameter injection uses `CurrentUser[UserType]` or `NamedDependency[CurrentUser[UserType]]`.
- [ ] WebSockets use connection tokens verified by `WebSocketConnectTokenIssuer`.
- [ ] Exception handlers handle `NotAuthorizedException` (401) and `PermissionDeniedException` (403).

## Example

```python
from dataclasses import dataclass
from litestar import Litestar, get
from litestar.di import NamedDependency
from litestar_security import (
    CurrentUser,
    Principal,
    AuthorizationSnapshot,
    SecurityConfig,
    SecurityPlugin,
    requires_role,
)


@dataclass
class User:
    id: str
    username: str
    roles: list[str]


async def auth_resolver(principal: Principal[User]) -> AuthorizationSnapshot:
    if not principal.is_authenticated:
        return AuthorizationSnapshot()
    user = principal.require_user()
    return AuthorizationSnapshot(roles=frozenset(user.roles))


@get("/dashboard", guards=[requires_role("member")])
async def dashboard(current_user: CurrentUser[User]) -> dict[str, str]:
    return {"message": f"Welcome back, {current_user.username}!"}


security_config = SecurityConfig[User](
    authorization_resolver=auth_resolver,
    # Configure authentication slots and mechanisms matching your transport
)

app = Litestar(
    route_handlers=[dashboard],
    plugins=[SecurityPlugin(config=security_config)],
)
```

## References Index

- **[litestar](../litestar/SKILL.md)** — Litestar app setup and plugin list.
- **[litestar-auth-guards](../litestar-auth-guards/SKILL.md)** — Native guards and low-level ASGI connection context.

## Official References

- <https://github.com/cofin/litestar-security>
- <https://github.com/cofin/litestar-security/tree/main/examples>

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
