# litestar-security — Authorization Reference

Authorization answers *what the caller may do*. It lives in Litestar's native
`guards=[...]` and evaluates synchronously against a snapshot resolved once per
request.

## The Snapshot

`AuthorizationSnapshot` is the single source of truth for a request's grants.

| Field | Holds |
| --- | --- |
| `roles` | Global role names (`frozenset[str]`) |
| `scopes` | Scope strings (`frozenset[str]`) |
| `capabilities` | Capability names (`frozenset[str]`) |
| `tenant_roles` | Roles per tenant (`Mapping[str, frozenset[str]]`) |
| `tenant_ids` | Tenants the principal belongs to (`frozenset[str]`) |
| `resources` | Resource permissions (`frozenset[ResourcePermission]`) |
| `attributes` | Application-defined extras (`Mapping[str, object]`) |

## The Resolver

Configure `SecurityConfig(authorization_resolver=...)` with an object that
implements async `resolve(principal)`. Return a snapshot for an authorized
principal, `InvalidCredentials` for an expected denial, or
`VerificationUnavailable` for an expected dependency failure. It runs **once
per request** — which is exactly why guards must not perform I/O.

```python
from litestar_security import AuthorizationSnapshot, Principal


class AppAuthorizationResolver:
    async def resolve(self, principal: Principal[User]) -> AuthorizationSnapshot:
        if not principal.is_authenticated:
            return AuthorizationSnapshot()
        user = principal.require_user()
        return AuthorizationSnapshot(
            roles=frozenset(user.roles),
            scopes=frozenset(user.scopes),
            tenant_ids=frozenset(user.tenant_ids),
            tenant_roles={tenant.id: frozenset(tenant.roles) for tenant in user.tenants},
        )
```

Credential restrictions are applied on top of the resolved snapshot by
`resolve_authorization(snapshot, restrictions)`; a narrowly scoped API key
therefore cannot exceed the account's own grants.

## Predicates

| Predicate | Signature | Checks |
| --- | --- | --- |
| `requires_authenticated()` | — | A verified, non-anonymous principal |
| `requires_role(role)` | `str` | Global role membership |
| `requires_scope(scope)` | `str` | Scope grant |
| `requires_capability(capability)` | `str` | Capability grant |
| `requires_tenant(*, tenant_parameter="tenant_id")` | keyword | Path tenant is one of the principal's |
| `requires_tenant_role(*, tenant_parameter="tenant_id", roles=...)` | keyword | Path tenant role membership |
| `requires_assurance(*, methods=(), traits=(), max_age=None, purpose=None)` | keyword | Recent or stronger evidence (step-up) |

## Combinators

Predicates compose with the `requires_*` combinator family. These are distinct from the
identically shaped mechanism combinators used by `auth=`.

| Guard combinator (for `guards=[...]`) | Mechanism combinator (for `auth=`) |
| --- | --- |
| `requires_any_of(*predicates)` | `any_of(*mechanism_names)` |
| `requires_all_of(*predicates)` | `all_of(*mechanism_names)` |
| `requires_at_least(count, *predicates)` | `at_least(count, *mechanism_names)` |
| `requires_one_of(*predicates)` | — |

Passing a predicate to `any_of()` raises `AttributeError` at import time,
because it expects a mechanism name.

```python
from litestar import Controller, get

from litestar_security import (
    required,
    requires_any_of,
    requires_role,
    requires_scope,
)


class ReportsController(Controller):
    path = "/reports"
    opt = {"auth": required("session")}
    guards = [requires_role("analyst")]

    @get("/", guards=[requires_any_of(requires_scope("read:all"), requires_scope("read:reports"))])
    async def list_reports(self) -> list[dict[str, str]]:
        return []
```

Controller-level guards apply to every handler beneath them; handler guards add
to rather than replace them.

## Path-Bound Checks

`requires_tenant` and `requires_tenant_role` compare the **path value** against
the server-resolved snapshot, so changing the identifier in the URL cannot
grant access:

```python
from litestar import get

from litestar_security import required, requires_tenant_role


@get(
    "/tenants/{tenant_id:str}",
    auth=required(),
    guards=[requires_tenant_role(tenant_parameter="tenant_id", roles={"owner"})],
)
async def tenant_settings(tenant_id: str) -> dict[str, str]:
    return {"tenant_id": tenant_id}
```

## Step-Up Authentication

`requires_assurance` gates on evidence quality rather than grants — require a
recent re-authentication or a stronger factor before a sensitive action:

```python
from datetime import timedelta

from litestar_security import requires_assurance

recent_mfa = requires_assurance(methods={"totp", "passkey"}, max_age=timedelta(minutes=5))
```

Unavailable verification fails closed as `503` rather than denying as `403`, so
an outage in a verification dependency is distinguishable from a real denial.

## Injecting the User

| Dependency | Behavior on anonymous |
| --- | --- |
| `principal` | Present, `is_authenticated` is `False` |
| `security_context` | Present, empty evidence |
| `current_user` | Rejected — also rejects userless service principals |

`principal` and `security_context` stay typed on public routes; `current_user`
is the explicit narrowing dependency.

## Cross-References

- **[Authentication](authentication.md)** — the `auth=` axis and its combinators.
- **[WebSockets](websockets.md)** — detached snapshot refresh for long-lived sockets.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/authentication.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/providers.rst>
