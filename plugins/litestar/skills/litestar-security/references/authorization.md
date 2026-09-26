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
per request** — project roles and tenant memberships already loaded on
`principal.user` with zero extra database queries, and expand hierarchical
workspace roles additively (`MEMBER` → `{"member"}`, `ADMIN` →
`{"member", "admin"}`, ownership adding `{"admin", "owner"}`):

```python
from litestar_security import AuthorizationSnapshot, InvalidCredentials, Principal

WORKSPACE_ROLE_EXPANSION = {
    "MEMBER": frozenset({"member"}),
    "ADMIN": frozenset({"member", "admin"}),
}


class AppAuthorizationResolver:
    __slots__ = ()

    async def resolve(self, principal: Principal[User]) -> AuthorizationSnapshot | InvalidCredentials:
        if not principal.is_authenticated:
            return AuthorizationSnapshot()
        if principal.user is None:
            return InvalidCredentials()
        user = principal.user
        tenant_roles: dict[str, frozenset[str]] = {}
        for membership in user.workspaces:
            roles = WORKSPACE_ROLE_EXPANSION.get(membership.role.upper(), frozenset({"member"}))
            if membership.is_owner:
                roles |= {"admin", "owner"}
            tenant_roles[str(membership.workspace_id)] = roles
        return AuthorizationSnapshot(
            roles=frozenset(role.slug for role in user.roles),
            scopes=frozenset(user.scopes),
            tenant_roles=tenant_roles,
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
from typing import ClassVar

from litestar import get
from litestar_security import (
    AuthenticationPolicy,
    SecureController,
    required,
    requires_any_of,
    requires_role,
    requires_scope,
)


class ReportsController(SecureController):
    path = "/reports"
    auth: ClassVar[AuthenticationPolicy] = required("session")
    guards = [requires_role("analyst")]

    @get("/", guards=[requires_any_of(requires_scope("read:all"), requires_scope("read:reports"))])
    async def list_reports(self) -> list[dict[str, str]]:
        return []
```

Controller-level guards apply to every handler beneath them; handler guards add
to rather than replace them.

## Path-Bound Tenant & Workspace Checks

`requires_tenant` and `requires_tenant_role` compare the **path value** against
the server-resolved snapshot, so changing the identifier in the URL cannot
grant access. Expand hierarchical workspace roles additively in your
`authorization_resolver` (for example `MEMBER` → `{"member"}`, `ADMIN` →
`{"member", "admin"}`, owner → `{"member", "admin", "owner"}`) and combine
global admin roles with `requires_any_of`:

```python
from litestar import get

from litestar_security import (
    AuthorizationPredicate,
    required,
    requires_any_of,
    requires_role,
    requires_tenant_role,
)


def requires_workspace_role(*roles: str) -> AuthorizationPredicate:
    return requires_any_of(
        requires_role("full-access"),
        requires_tenant_role(tenant_parameter="workspace_id", roles=frozenset(roles)),
    )


@get(
    "/workspaces/{workspace_id:str}/settings",
    auth=required(),
    guards=[requires_workspace_role("owner")],
)
async def workspace_settings(workspace_id: str) -> dict[str, str]:
    return {"workspace_id": workspace_id}
```

## Custom Predicates

Subclass `AuthorizationPredicate` and return an `AuthorizationDecision` to
compose domain-specific synchronous checks (such as self-subject path matching)
inside `requires_any_of` or `requires_all_of`:

```python
from typing import Any

from litestar.connection import ASGIConnection
from litestar_security import requires_any_of, requires_role
from litestar_security.guards import AuthorizationDecision, AuthorizationPredicate


class SelfSubjectPredicate(AuthorizationPredicate):
    __slots__ = ()

    def decide(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthorizationDecision:
        principal = connection.scope.get("user")
        principal_id = getattr(principal, "id", None)
        if principal_id is None:
            return AuthorizationDecision(granted=False, authentication_required=True)
        subject = connection.path_params.get("user_id")
        return AuthorizationDecision(granted=subject is not None and str(subject) == str(principal_id))


requires_self_or_admin = requires_any_of(requires_role("full-access"), SelfSubjectPredicate())
```

## Step-Up Authentication

`requires_assurance` gates on evidence quality (`methods`, `AssuranceTrait`,
`max_age`, `purpose`) rather than grants — require a recent re-authentication
or a stronger factor before a sensitive action:

```python
from datetime import timedelta

from litestar_security import AssuranceTrait, requires_assurance

recent_mfa = requires_assurance(
    methods={"totp", "passkey"},
    traits={AssuranceTrait.USER_VERIFIED},
    max_age=timedelta(minutes=5),
)
```

Available `AssuranceTrait` values: `PHISHING_RESISTANT`, `USER_VERIFIED`,
`HARDWARE_BACKED`.

Unavailable verification fails closed as `503` rather than denying as `403`, so
an outage in a verification dependency is distinguishable from a real denial.

## Injecting the User

| Dependency | Annotation | Behavior on anonymous |
| --- | --- | --- |
| `principal` | `NamedDependency[Principal[User]]` | Present, `is_authenticated` is `False` |
| `security_context` | `NamedDependency[SecurityContext]` | Present, empty evidence |
| `current_user` | `CurrentUser[User]` | Rejected — also rejects userless service principals |

`principal` and `security_context` stay typed on public routes; `current_user`
is the explicit narrowing dependency (`CurrentUser[User]` is already a
`NamedDependency[User]` alias).

## Cross-References

- **[Authentication](authentication.md)** — the `auth=` axis and its combinators.
- **[WebSockets](websockets.md)** — detached snapshot refresh for long-lived sockets.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/authentication.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/providers.rst>
