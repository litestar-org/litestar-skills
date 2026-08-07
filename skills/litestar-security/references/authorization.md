# litestar-security — Authorization Reference

Authorization answers *what the caller may do*. It lives in Litestar's native
`guards=[...]` and evaluates synchronously against a snapshot resolved once per
request.

## The Snapshot

`AuthorizationSnapshot` is the single source of truth for a request's grants.

| Field | Holds |
| --- | --- |
| `roles` | Global role names |
| `scopes` | Scope strings |
| `capabilities` | Capability names |
| `team_roles` | Roles per team |
| `tenant_ids` | Tenants the principal belongs to |
| `resources` | Resource permissions |
| `attributes` | Application-defined extras |

## The Resolver

Configure `SecurityConfig(authorization_resolver=...)` with a callable taking
the authenticated `Principal` and returning a snapshot. It runs **once per
request** — which is exactly why guards must not perform I/O.

```python
from litestar_security import AuthorizationSnapshot, Principal


async def resolve_user_authorization(principal: Principal[User]) -> AuthorizationSnapshot:
    if not principal.is_authenticated:
        return AuthorizationSnapshot()
    user = principal.require_user()
    return AuthorizationSnapshot(
        roles=frozenset(user.roles),
        scopes=frozenset(user.scopes),
        tenant_ids=frozenset(user.tenant_ids),
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
| `requires_team_role(*, team_parameter="team_id", roles)` | keyword | Path team role membership |
| `requires_assurance(*, methods=(), traits=(), max_age=None, purpose=None)` | keyword | Recent or stronger evidence (step-up) |

## Combinators

Predicates compose with the `guard_*` family. These are distinct from the
identically shaped mechanism combinators used by `auth=`.

| Guard combinator | Mechanism combinator (for `auth=`) |
| --- | --- |
| `guard_any_of(*predicates)` | `any_of(*mechanism_names)` |
| `guard_all_of(*predicates)` | `all_of(*mechanism_names)` |
| `guard_at_least(count, *predicates)` | `at_least(count, *mechanism_names)` |
| `guard_one_of(*predicates)` | — |

Passing a predicate to `any_of()` raises `AttributeError` at import time,
because it expects a mechanism name.

```python
from litestar import Controller, get

from litestar_security import (
    guard_any_of,
    required,
    requires_role,
    requires_scope,
)


class ReportsController(Controller):
    path = "/reports"
    opt = {"auth": required("session")}
    guards = [requires_role("analyst")]

    @get("/", guards=[guard_any_of(requires_scope("read:all"), requires_scope("read:reports"))])
    async def list_reports(self) -> list[dict[str, str]]: ...
```

Controller-level guards apply to every handler beneath them; handler guards add
to rather than replace them.

## Path-Bound Checks

`requires_tenant` and `requires_team_role` compare the **path value** against
the server-resolved snapshot, so changing the identifier in the URL cannot
grant access:

```python
from litestar import get

from litestar_security import required, requires_team_role


@get(
    "/teams/{team_id:str}",
    auth=required(),
    guards=[requires_team_role(team_parameter="team_id", roles={"owner"})],
)
async def team_settings(team_id: str) -> dict[str, str]:
    return {"team_id": team_id}
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

- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/authentication.rst>
- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/providers.rst>
