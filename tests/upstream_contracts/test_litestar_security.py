"""Upstream contract verification for litestar-security 0.6.0."""

import dataclasses
import inspect
from importlib.metadata import version

from litestar import Litestar
from litestar_security import (
    AuthorizationPredicate,
    AuthorizationSnapshot,
    ContentSecurityPolicy,
    CSPMode,
    CurrentUser,
    InvalidCredentials,
    Principal,
    PublicController,
    SecureController,
    SecurityConfig,
    SecurityContext,
    SecurityHeadersConfig,
    SecurityPlugin,
    VerificationUnavailable,
    WebSocketCloseCodes,
    WebSocketConnectTokenService,
    WebSocketSecurityConfig,
    all_of,
    any_of,
    at_least,
    csp_nonce,
    exclude,
    issue_websocket_connect_token,
    mechanism,
    optional,
    public,
    required,
    requires_all_of,
    requires_any_of,
    requires_assurance,
    requires_at_least,
    requires_authenticated,
    requires_capability,
    requires_one_of,
    requires_role,
    requires_scope,
    requires_tenant,
    requires_tenant_role,
)
from litestar_security._cli import routes_command, security_group


def test_litestar_security_060_version() -> None:
    """Verify installed library version matches the upstream 0.6.0 release."""
    assert version("litestar-security") == "0.6.0"


def test_litestar_security_060_authorization_predicates_and_combinators() -> None:
    """Verify all guard predicates and combinators are callable and return predicates."""
    for predicate in (
        requires_authenticated,
        requires_role("admin"),
        requires_scope("read:all"),
        requires_capability("reports"),
        requires_tenant(),
        requires_tenant_role(roles={"owner"}),
        requires_assurance(),
        requires_all_of(requires_role("admin")),
        requires_any_of(requires_role("admin"), requires_scope("read:all")),
        requires_at_least(1, requires_role("admin")),
        requires_one_of(requires_role("admin")),
    ):
        assert isinstance(predicate, AuthorizationPredicate) or callable(predicate)

    assert callable(requires_role)
    assert callable(requires_scope)
    assert callable(requires_capability)
    assert callable(requires_tenant)
    assert callable(requires_tenant_role)
    assert callable(requires_assurance)
    assert callable(requires_all_of)
    assert callable(requires_any_of)
    assert callable(requires_at_least)
    assert callable(requires_one_of)
    assert csp_nonce is not None


def test_litestar_security_060_authentication_policy_helpers() -> None:
    """Verify authentication policy helpers and mechanism combinators."""
    for helper in (
        public,
        required,
        any_of,
        all_of,
        at_least,
        optional,
        exclude,
        mechanism,
    ):
        assert callable(helper)


def test_litestar_security_060_config_and_snapshot_contract() -> None:
    """Verify SecurityConfig, AuthorizationSnapshot, Principal, and SecurityContext schemas."""
    config_params = inspect.signature(SecurityConfig).parameters
    expected_config_params = {
        "authorization_resolver",
        "local_auth",
        "local_jwks",
        "oauth",
        "protected_resource",
        "mfa",
        "passkeys",
        "api_key",
        "iap",
        "service_token",
        "headers",
        "websocket",
        "exclude",
        "jwks_providers",
        "raised_error_schema",
        "wire_rename",
    }
    assert expected_config_params <= set(config_params)

    snapshot_fields = {f.name for f in dataclasses.fields(AuthorizationSnapshot)}
    expected_snapshot_fields = {
        "roles",
        "scopes",
        "capabilities",
        "tenant_roles",
        "tenant_ids",
        "resources",
        "attributes",
    }
    assert expected_snapshot_fields <= snapshot_fields

    principal_members = set(dir(Principal))
    assert {"is_authenticated", "require_user", "id", "display_name", "user"} <= principal_members
    assert CurrentUser is not None
    assert SecurityContext is not None

    headers_hardened = SecurityHeadersConfig.hardened()
    assert isinstance(headers_hardened, SecurityHeadersConfig)
    assert CSPMode.ENFORCE.value == "enforce"
    assert CSPMode.REPORT_ONLY.value == "report-only"
    assert ContentSecurityPolicy is not None

    assert issubclass(PublicController, SecureController)
    websocket_fields = {field.name for field in dataclasses.fields(WebSocketSecurityConfig)}
    assert {"connect_token_store", "current_security_epoch", "allowed_origins"} <= websocket_fields


class _AuthorizationResolver:
    async def resolve(self, principal: Principal["_User"]) -> AuthorizationSnapshot:
        return AuthorizationSnapshot()


def test_litestar_security_060_authorization_resolver_protocol() -> None:
    """Verify authorization resolvers provide an async ``resolve`` method."""
    resolver = _AuthorizationResolver()
    config: SecurityConfig[_User] = SecurityConfig(authorization_resolver=resolver)

    assert callable(resolver.resolve)
    assert config.authorization_resolver is resolver
    assert isinstance(InvalidCredentials(), InvalidCredentials)
    assert isinstance(VerificationUnavailable(), VerificationUnavailable)


@dataclasses.dataclass
class _User:
    id: str


def test_litestar_security_060_reserved_dependency_keys() -> None:
    """Verify standard dependency keys registered by SecurityPlugin."""
    config: SecurityConfig[_User] = SecurityConfig()
    plugin: SecurityPlugin[_User] = SecurityPlugin(config=config)
    app = Litestar(route_handlers=[], plugins=[plugin])
    assert set(app.dependencies) == {
        "principal",
        "security_context",
        "current_user",
        "websocket_connect_tokens",
    }


def test_litestar_security_060_websocket_and_cli_contract() -> None:
    """Verify WebSocket security helpers, close codes, and CLI command exports."""
    assert WebSocketSecurityConfig is not None
    close_codes = WebSocketCloseCodes()
    assert close_codes.unauthenticated == 4401
    assert close_codes.unauthorized == 4403
    assert close_codes.verification_unavailable == 1013
    assert callable(issue_websocket_connect_token)
    assert WebSocketConnectTokenService is not None

    assert security_group is not None
    assert routes_command is not None
    assert "routes" in security_group.commands
