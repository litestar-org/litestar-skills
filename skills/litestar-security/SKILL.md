---
name: litestar-security
description: "Auto-activate for litestar_security, SecurityPlugin, SecurityConfig, CurrentUser, Principal, SecurityContext, requires_role, requires_scope, requires_authenticated, requires_tenant, or requires_capability. Not for raw auth guards alone — use litestar-auth-guards."
---

# Litestar Security

`litestar-security` 0.3.0 is a declarative authentication and authorization framework for Litestar. It provides credential slots and mechanisms, unified session management, local accounts, MFA, WebAuthn passkeys, OAuth/OIDC, API keys, workload JWTs, and browser hardening.

Two separate axes, wired through two separate Litestar keywords:

- **Authentication** — *who is calling* — is a policy on `auth=` (or `opt={"auth": ...}`).
- **Authorization** — *what they may do* — is a predicate in Litestar's native `guards=[...]`.

Do not conflate them: the policy helpers (`public`, `required`, `any_of`, `all_of`, `at_least`) take **mechanism names**, while the guard combinators (`guard_any_of`, `guard_all_of`, `guard_at_least`, `guard_one_of`) take **predicates**.

## Code Style Rules

- **Declare authentication with `auth=`.** Put policy on the route, or on a router/controller/app through `opt={"auth": ...}`. The nearest native owner wins.
- **Keep authorization in `guards=[...]`.** Litestar's `security=` parameter is reserved for the OpenAPI requirements projected from `auth`.
- **Inject the user with `CurrentUser[T]`.** Use `NamedDependency[CurrentUser[UserType]]`; it rejects anonymous and userless service principals. `principal` and `security_context` stay typed on public routes too.
- **Authorize from the snapshot.** Guards read the `AuthorizationSnapshot` produced by the configured `authorization_resolver`. Never query the database inside a guard.
- **Exclude other plugins' routes by path.** Static assets and dashboards carry no `auth` and compile to implicit `required()`, so they answer `401` until listed in `SecurityConfig(exclude=[...])`.
- **Secure WebSockets with connect tokens.** Browsers cannot set handshake headers; mint a short-lived token over authenticated HTTP.
- **Load protector keys from a secret store.** MFA and OAuth protectors need application-owned 32-byte AES-256-GCM keys, never source literals.

## Quick Reference

### Plugin Registration

```python
from litestar import Litestar, get
from litestar.di import NamedDependency

from litestar_security import (
    SecurityConfig,
    SecurityContext,
    SecurityPlugin,
    public,
)


@get("/", auth=public(), sync_to_thread=False)
def index(security_context: NamedDependency[SecurityContext]) -> dict[str, bool]:
    return {"authenticated": bool(security_context.evidence)}


app = Litestar(
    route_handlers=[index],
    plugins=[SecurityPlugin(SecurityConfig())],
)
```

With mechanisms configured and no inherited policy, routes default to implicit `required()`. With no mechanisms at all they are public.

### Authentication Policy

```python
from litestar import Controller, get
from litestar_security import all_of, any_of, at_least, public, required

required()  # any configured mechanism
required("session")  # one named mechanism
any_of("session", "api_key")  # either
all_of("api_key", "workload_jwt")  # both, same subject
at_least(2, "session", "api_key", "passkey")  # N of M
public()  # no authentication, excluded from native CSRF
```

Apply it at whichever layer owns the decision:

```python
@get("/health", auth=public())
async def health() -> dict[str, str]:
    return {"status": "ok"}


class AccountController(Controller):
    opt = {"auth": required("session")}
```

Custom controller class attributes are not propagated by Litestar — policy must live in `opt`, or use the typed `SecureController` / `PublicController` base classes.

### Authorization Guards

```python
from litestar import Controller, get
from litestar_security import guard_any_of, requires_role, requires_scope


class ReportsController(Controller):
    path = "/reports"
    opt = {"auth": required("session")}
    guards = [requires_role("analyst")]

    @get("/", guards=[guard_any_of(requires_scope("read:all"), requires_scope("read:reports"))])
    async def list_reports(self) -> list[dict[str, str]]: ...
```

### Reserved Dependency Names

The plugin registers these; do not shadow them.

| Key | Type | Use |
| --- | --- | --- |
| `principal` | `Principal` | Stable envelope identity plus the active user model |
| `security_context` | `SecurityContext` | Active session, evidence, snapshot, and restrictions |
| `current_user` | `CurrentUser[User]` | Narrowing shortcut; rejects anonymous and service principals |
| `websocket_connect_tokens` | `WebSocketConnectTokenService` | WebSocket connect-token manager |

### Status Code Contract

| Outcome | Status |
| --- | --- |
| Authentication failure | `401` |
| Guard denial | `403` |
| Verification unavailable (fails closed) | `503` |

<workflow>

## Workflow

### Step 1: Install the capabilities in use

Core install covers JWT/JWKS validation, API keys, IAP, and OIDC token verification. Add an extra only for what the application uses: `[mfa]`, `[passkeys]`, `[oauth]`, `[argon2]`, or `[all]`.

### Step 2: Choose providers

Pick where identity is established — local accounts, OAuth/OIDC, Google IAP, API keys, or workload JWTs. Adding a provider makes its mechanism available; route policy decides where it is accepted. See [Providers](references/providers.md).

### Step 3: Implement the authorization resolver

Write a callable taking the authenticated `Principal` and returning an `AuthorizationSnapshot` of granted roles, scopes, capabilities, teams, and tenants. It runs once per request, which is why guards must not perform I/O.

```python
from litestar_security import AuthorizationSnapshot, Principal


async def resolve_user_authorization(principal: Principal[User]) -> AuthorizationSnapshot:
    if not principal.is_authenticated:
        return AuthorizationSnapshot()
    user = principal.require_user()
    return AuthorizationSnapshot(
        roles=frozenset(user.roles),
        scopes=frozenset(user.scopes),
    )
```

### Step 4: Register the plugin and set default policy

Scope an application-wide `opt={"auth": ...}` default to the router that owns the application's own routes, so policy-less third-party routes keep the implicit default rather than counting as declared.

### Step 5: Exclude routes the application did not write

Add `SecurityConfig(exclude=[...])` patterns for static files, queue dashboards, and schema browsers. See [Composition](references/composition.md).

### Step 6: Harden the deployment

Apply `SecurityHeadersConfig.hardened()`, supply every CSP directive explicitly, and move protector keys and peppers into secret management. See [Hardening](references/hardening.md).

</workflow>

<guardrails>

## Guardrails

- **Do not pass predicates to `any_of` / `all_of` / `at_least`.** Those compose authentication mechanisms. Use `guard_any_of`, `guard_all_of`, `guard_at_least`, or `guard_one_of` for predicates.
- **Do not shadow reserved dependencies.** Avoid naming providers `principal`, `security_context`, `current_user`, or `websocket_connect_tokens`.
- **Do not perform I/O in predicates.** Guards evaluate synchronously against the snapshot; put database checks in the `authorization_resolver`.
- **Do not use `guards=` for authentication or `auth=` for authorization.** They compile to different things — runtime admission plus OpenAPI projection versus permission checks.
- **Do not put a layer-level policy above excluded routes.** A route that both declares `auth` and matches an exclusion pattern is rejected at startup.
- **Do not put bearer credentials in WebSocket query strings.** Use a connect token or an HttpOnly cookie.
- **Do not enable `MFAConfig.require_at_login` before enrolling factors.** Affected accounts lock themselves out.
- **Do not hard-code protector keys.** Load exact 32-byte material from a KMS or secret store, and retain the previous key through rotation.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] `SecurityPlugin` is registered in application `plugins`.
- [ ] Every route's authentication policy is declared via `auth=` or inherited `opt={"auth": ...}`.
- [ ] Authorization uses `guards=[...]` with predicates, never the mechanism combinators.
- [ ] A custom `authorization_resolver` returns an `AuthorizationSnapshot`.
- [ ] No handler or guard queries the database to perform authorization checks.
- [ ] Handler injection uses `CurrentUser[UserType]` or `NamedDependency[CurrentUser[UserType]]`.
- [ ] Routes registered by other plugins are excluded by anchored path pattern or given an explicit policy.
- [ ] WebSockets use connect tokens verified against the registered handler name and exact Origin.
- [ ] Exception handlers cover `401`, `403`, and `503` outcomes.
- [ ] Protector keys, peppers, and session secrets come from secret management.

</validation>

<example>

## Example

```python
from dataclasses import dataclass, field

from litestar import Litestar, Router, get
from litestar.di import NamedDependency
from litestar_security import (
    AuthorizationSnapshot,
    CurrentUser,
    Principal,
    SecurityConfig,
    SecurityHeadersConfig,
    SecurityPlugin,
    guard_any_of,
    public,
    required,
    requires_role,
    requires_scope,
)


@dataclass
class User:
    id: str
    username: str
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)


async def auth_resolver(principal: Principal[User]) -> AuthorizationSnapshot:
    if not principal.is_authenticated:
        return AuthorizationSnapshot()
    user = principal.require_user()
    return AuthorizationSnapshot(
        roles=frozenset(user.roles),
        scopes=frozenset(user.scopes),
    )


@get("/health", auth=public())
async def health() -> dict[str, str]:
    return {"status": "ok"}


@get(
    "/orders",
    guards=[guard_any_of(requires_scope("read:all"), requires_scope("read:orders"))],
)
async def list_orders(current_user: NamedDependency[CurrentUser[User]]) -> dict[str, str]:
    return {"owner": current_user.username}


@get("/admin/orders", guards=[requires_role("admin")])
async def admin_orders() -> list[dict[str, str]]:
    return []


api = Router(path="/api", route_handlers=[list_orders, admin_orders], opt={"auth": required("session")})

security_config = SecurityConfig[User](
    authorization_resolver=auth_resolver,
    headers=SecurityHeadersConfig.hardened(),
    exclude=["^/static"],
)

app = Litestar(
    route_handlers=[health, api],
    plugins=[SecurityPlugin(config=security_config)],
)
```

</example>

## References Index

- **[Authentication](references/authentication.md)** — policy helpers, ownership layers, controller base classes, CSRF interaction.
- **[Authorization](references/authorization.md)** — snapshots, resolvers, predicates, combinators, tenant and team checks, assurance.
- **[Providers](references/providers.md)** — local accounts, OAuth/OIDC, IAP, API keys, workload JWTs, transaction protectors.
- **[Composition](references/composition.md)** — excluding routes other plugins register, and the patterns per plugin.
- **[Hardening](references/hardening.md)** — CSP, security headers, secrets, key rotation, MFA operational rules.
- **[WebSockets](references/websockets.md)** — connect tokens, close codes, snapshot refresh, revocation.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app setup and plugin list.
- **[litestar-auth-guards](../litestar-auth-guards/SKILL.md)** — native guards and low-level ASGI connection context.
- **[litestar-exceptions](../litestar-exceptions/SKILL.md)** — mapping `401` / `403` / `503` to Problem Details responses.

## Official References

- <https://github.com/cofin/litestar-security>
- <https://github.com/cofin/litestar-security/tree/v0.3.0/docs>
- <https://github.com/cofin/litestar-security/tree/v0.3.0/examples>

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
