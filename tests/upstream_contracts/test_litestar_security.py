import dataclasses
import inspect
from importlib.metadata import version

from litestar import Litestar
from litestar_security import (
    AuthorizationSnapshot,
    CurrentUser,
    Principal,
    SecurityConfig,
    SecurityContext,
    SecurityPlugin,
    all_of,
    any_of,
    csp_nonce,
    requires_authenticated,
    requires_capability,
    requires_role,
    requires_scope,
    requires_tenant,
)


def test_litestar_security_030_plugin_and_authorization_contract() -> None:
    assert version("litestar-security") == "0.3.0"

    # Composable authorization predicates the skill documents as guard factories.
    for predicate in (
        requires_role,
        requires_scope,
        requires_tenant,
        requires_capability,
        requires_authenticated,
        all_of,
        any_of,
        csp_nonce,
    ):
        assert callable(predicate)

    # The resolver hook the skill tells users to configure.
    assert "authorization_resolver" in inspect.signature(SecurityConfig).parameters

    # Snapshot fields the skill's resolver example populates.
    snapshot_fields = {f.name for f in dataclasses.fields(AuthorizationSnapshot)}
    assert {"roles", "scopes", "capabilities", "tenant_ids"} <= snapshot_fields

    # Principal surface used for identity and user access.
    assert {"is_authenticated", "require_user", "id", "user"} <= set(dir(Principal))
    assert CurrentUser is not None
    assert SecurityContext is not None


@dataclasses.dataclass
class _User:
    id: str


def test_litestar_security_030_reserved_dependency_keys() -> None:
    config: SecurityConfig[_User] = SecurityConfig()
    plugin: SecurityPlugin[_User] = SecurityPlugin(config=config)
    app = Litestar(route_handlers=[], plugins=[plugin])
    assert set(app.dependencies) == {
        "principal",
        "security_context",
        "current_user",
        "websocket_connect_tokens",
    }
