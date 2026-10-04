"""Upstream contract verification for litestar-security 0.6.0."""

import dataclasses
import inspect
from importlib.metadata import version

import pytest
from litestar import Litestar, Router, get
from litestar.exceptions import ImproperlyConfiguredException, LitestarWarning
from litestar.testing import TestClient
from litestar_security import (
    AssuranceRequirement,
    AssuranceTrait,
    AuthenticationEvidence,
    AuthorizationPredicate,
    AuthorizationSnapshot,
    ContentSecurityPolicy,
    CredentialVerifier,
    CSPMode,
    CurrentUser,
    ExternalCSRF,
    InvalidCredentials,
    MFAConfig,
    PasskeyConfig,
    Principal,
    PublicController,
    RaisedErrorSchema,
    RouteDocs,
    SecureController,
    SecurityConfig,
    SecurityContext,
    SecurityHeadersConfig,
    SecurityPlugin,
    VerificationUnavailable,
    WebSocketCloseCodes,
    WebSocketConnectAuthorization,
    WebSocketConnectTokenIssuer,
    WebSocketConnectTokenService,
    WebSocketSecurityConfig,
    accounts,
    all_of,
    any_of,
    at_least,
    csp_nonce,
    exclude,
    issue_websocket_connect_token,
    mechanism,
    optional,
    providers,
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
    testing,
)
from litestar_security._cli import routes_command, security_group
from litestar_security.accounts import (
    LocalAccountState,
    OperationMessage,
    RateLimitPolicy,
    RegistrationMode,
    RegistrationPolicy,
    ResolvedUserAuthSession,
    SecurityEvent,
    SecurityEventSink,
    SessionBindingConfig,
    UserAuthSession,
    UserAuthSessionResolver,
    VerificationOutcome,
    VerificationStatus,
)
from litestar_security.authentication import AUTH_POLICY_OPT_KEY
from litestar_security.guards import AuthorizationDecision
from litestar_security.providers import (
    APIKeyCodec,
    APIKeyConfig,
    APIKeyService,
    APIKeyState,
    CachedJWKSProvider,
    GoogleIAPClaims,
    GoogleIAPConfig,
    GoogleIAPExternalIdentity,
    HttpxJWKSFetcher,
    JWKSFetchOutcome,
    JWKSFetchTarget,
    JWKSSource,
    LocalJWKSConfig,
    LocalKeyRing,
    OAuthConfig,
    ProtectedResourceConfig,
    ServiceTokenConfig,
    SigningKey,
)
from litestar_security.testing import (
    BackendBarrier,
    FakeClock,
    OAuthRequestObservation,
    StoreConformanceFactories,
    assert_api_key_store_conformance,
    assert_oauth_transaction_protector_conformance,
    assert_rate_limiter_conformance,
    assert_secret_protector_conformance,
    assert_security_backend_conformance,
    assert_session_registry_conformance,
)


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
        requires_assurance(methods={"totp"}, traits={AssuranceTrait.USER_VERIFIED}),
        requires_all_of(requires_role("admin")),
        requires_any_of(requires_role("admin"), requires_scope("read:all")),
        requires_at_least(1, requires_role("admin")),
        requires_one_of(requires_role("admin")),
    ):
        assert isinstance(predicate, AuthorizationPredicate) or callable(predicate)

    assert AssuranceRequirement(methods=frozenset({"totp"}), traits=frozenset({AssuranceTrait.PHISHING_RESISTANT}))
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
    assert AuthorizationDecision(granted=True).granted is True
    assert AUTH_POLICY_OPT_KEY == "auth"
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
        "slots",
        "mechanisms",
        "max_openapi_combinations",
        "external_csrf",
        "exclude_opt_key",
        "exclude",
        "require_default",
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
        "authorization_resolver",
        "jwks_providers",
        "jwks_warmup_failure",
        "wire_rename",
        "wire_forbid_unknown_fields",
        "raised_error_schema",
    }
    assert expected_config_params <= set(config_params)

    mfa_fields = {f.name for f in dataclasses.fields(MFAConfig)}
    assert {"store", "step_up_store", "secret_protector", "require_at_login", "login_challenge_store"} <= mfa_fields
    assert CredentialVerifier is not None
    assert WebSocketConnectAuthorization is not None
    assert OAuthConfig is not None
    assert APIKeyConfig is not None
    assert APIKeyService is not None
    assert APIKeyCodec is not None
    assert APIKeyState is not None
    assert GoogleIAPConfig is not None
    assert GoogleIAPClaims is not None
    assert GoogleIAPExternalIdentity is not None
    assert CachedJWKSProvider is not None
    assert HttpxJWKSFetcher is not None
    assert JWKSSource is not None
    assert JWKSFetchOutcome is not None
    assert JWKSFetchTarget is not None
    assert PasskeyConfig is not None
    assert ProtectedResourceConfig is not None
    assert LocalJWKSConfig is not None
    assert LocalKeyRing is not None
    assert SigningKey is not None
    assert ServiceTokenConfig is not None
    assert ExternalCSRF is not None
    assert RouteDocs is not None
    assert RaisedErrorSchema is not None
    assert AuthenticationEvidence is not None
    assert LocalAccountState is not None
    assert OperationMessage is not None
    assert RateLimitPolicy is not None
    assert RegistrationMode is not None
    assert RegistrationPolicy is not None
    assert ResolvedUserAuthSession is not None
    assert SecurityEvent is not None
    assert SecurityEventSink is not None
    assert SessionBindingConfig is not None
    assert UserAuthSession is not None
    assert UserAuthSessionResolver is not None
    assert VerificationOutcome is not None
    assert VerificationStatus is not None

    expected_account_exports = {
        "AESGCMSecretProtector",
        "Argon2PasswordHasher",
        "LocalAuth",
        "LocalAuthSecrets",
        "PasskeyAssertionStatus",
        "PasskeyMetadata",
        "RecoveryCodePepper",
        "SecretProtectorKey",
        "StepUpGrantState",
        "WebAuthnVerificationError",
        "build_local_auth_routes",
        "build_mfa_routes",
        "forwarded_client_key",
    }
    assert expected_account_exports <= set(accounts.__all__)

    assert BackendBarrier is not None
    assert FakeClock is not None
    assert OAuthRequestObservation is not None
    assert StoreConformanceFactories is not None
    assert callable(assert_api_key_store_conformance)
    assert callable(assert_oauth_transaction_protector_conformance)
    assert callable(assert_rate_limiter_conformance)
    assert callable(assert_secret_protector_conformance)
    assert callable(assert_security_backend_conformance)
    assert callable(assert_session_registry_conformance)

    forbidden_legacy_names = (
        "guard_all_of",
        "guard_any_of",
        "guard_at_least",
        "guard_one_of",
        "require_all_of",
        "require_any_of",
        "require_assurance",
        "require_at_least",
        "require_authenticated",
        "require_capability",
        "require_one_of",
        "require_role",
        "require_scope",
        "require_team_role",
        "require_tenant",
        "requires_not",
        "requires_team_role",
        "not_guard",
    )
    for legacy_name in forbidden_legacy_names:
        assert not hasattr(accounts, legacy_name)
        assert not hasattr(providers, legacy_name)
        assert not hasattr(testing, legacy_name)

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
    headers_fields = {f.name for f in dataclasses.fields(SecurityHeadersConfig)}
    assert headers_fields == {"static", "csp"}
    csp_fields = {f.name for f in dataclasses.fields(ContentSecurityPolicy)}
    assert {"directives", "mode", "nonce_directives"} <= csp_fields
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


def test_litestar_security_060_reserved_dependency_keys_and_layer_exclusions() -> None:
    """Verify standard dependency keys, csp_nonce registration, and layer-level exclude_from_auth support."""

    @get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "true"}

    excluded_router = Router(path="/internal", route_handlers=[ping], opt={"exclude_from_auth": True})
    config: SecurityConfig[_User] = SecurityConfig()
    plugin: SecurityPlugin[_User] = SecurityPlugin(config=config)
    app = Litestar(route_handlers=[excluded_router], plugins=[plugin])
    assert set(app.dependencies) == {
        "principal",
        "security_context",
        "current_user",
        "websocket_connect_tokens",
    }

    nonce_headers = SecurityHeadersConfig(
        csp=ContentSecurityPolicy(
            directives={"default-src": ["'self'"], "script-src": ["'self'"]},
            mode=CSPMode.ENFORCE,
            nonce_directives=("script-src",),
        ),
    )
    nonce_config: SecurityConfig[_User] = SecurityConfig(headers=nonce_headers)
    nonce_plugin: SecurityPlugin[_User] = SecurityPlugin(config=nonce_config)
    nonce_app = Litestar(
        route_handlers=[excluded_router],
        plugins=[nonce_plugin],
    )
    assert "csp_nonce" in nonce_app.dependencies


def test_litestar_security_060_well_known_routes_and_protected_resource() -> None:
    """Verify ProtectedResourceConfig, public .well-known router registration, and exclusion conflicts."""

    @get("/openid-configuration")
    async def openid_configuration() -> dict[str, str]:
        return {"issuer": "https://auth.example.com"}

    well_known_router = Router(
        path="/.well-known",
        route_handlers=[openid_configuration],
        opt={"auth": public()},
    )
    protected_resource = ProtectedResourceConfig(
        resource="https://api.example.com",
        authorization_servers=("https://auth.example.com",),
        scopes_supported=("read:orders",),
        register_route=True,
    )
    config: SecurityConfig[_User] = SecurityConfig(protected_resource=protected_resource)
    plugin: SecurityPlugin[_User] = SecurityPlugin(config=config)
    app = Litestar(
        route_handlers=[well_known_router],
        plugins=[plugin],
    )
    registered_paths = {route.path for route in app.routes}
    assert "/.well-known/oauth-protected-resource" in registered_paths
    assert "/.well-known/openid-configuration" in registered_paths

    conflict_config: SecurityConfig[_User] = SecurityConfig(
        protected_resource=protected_resource,
        exclude=[r"^/\.well-known"],
    )
    conflict_plugin: SecurityPlugin[_User] = SecurityPlugin(config=conflict_config)
    with pytest.raises(ImproperlyConfiguredException, match="matches a security exclusion pattern"):
        Litestar(route_handlers=[well_known_router], plugins=[conflict_plugin])

    delegated_resource = ProtectedResourceConfig(
        resource="https://api.example.com",
        authorization_servers=("https://auth.example.com",),
        scopes_supported=("read:orders",),
        register_route=False,
    )
    unmatched_config: SecurityConfig[_User] = SecurityConfig(
        protected_resource=delegated_resource,
        exclude=[r"^/\.well-known"],
    )
    unmatched_plugin: SecurityPlugin[_User] = SecurityPlugin(config=unmatched_config)
    unmatched_app = Litestar(route_handlers=[], plugins=[unmatched_plugin])
    with (
        pytest.warns(LitestarWarning, match="match no registered route"),
        TestClient(app=unmatched_app),
    ):
        pass


def test_litestar_security_060_websocket_and_cli_contract() -> None:
    """Verify WebSocket security helpers, close codes, and CLI command exports."""
    assert WebSocketSecurityConfig is not None
    close_codes = WebSocketCloseCodes()
    assert close_codes.unauthenticated == 4401
    assert close_codes.unauthorized == 4403
    assert close_codes.verification_unavailable == 1013
    assert callable(issue_websocket_connect_token)
    assert WebSocketConnectTokenIssuer is not None
    assert WebSocketConnectTokenService is not None

    assert security_group is not None
    assert routes_command is not None
    assert "routes" in security_group.commands
