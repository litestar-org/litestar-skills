# litestar-security — Providers Reference

A provider is where identity is established. Adding one makes its
authentication mechanism available; route policy decides where that mechanism
is accepted, and the application `authorization_resolver` loads grants for the
verified principal.

## Choosing a Provider

| Provider | Use for | Configuration |
| --- | --- | --- |
| Local accounts | Session cookies, bearer tokens, or hybrid; requires `[argon2,mfa]` | `SecurityConfig(local_auth=LocalAuth.session(...) / .tokens(...) / .hybrid(...))` |
| OAuth / OpenID Connect | Browser sign-in, account linking, OIDC identity | `SecurityConfig(oauth=OAuthConfig(...))` |
| OAuth Protected Resource | RFC 9728 `/.well-known/oauth-protected-resource` metadata and `WWW-Authenticate` challenges | `SecurityConfig(protected_resource=ProtectedResourceConfig(...))` |
| Google IAP | Verifying Google Identity-Aware Proxy JWT assertions | `SecurityConfig(iap=GoogleIAPConfig(...))` |
| API keys | Machine/service clients with digest-only storage | `SecurityConfig(api_key=APIKeyConfig(...))` |
| Local JWKS | Exposing application public keys for issued JWTs | `SecurityConfig(local_jwks=LocalJWKSConfig(...))` |
| Service tokens | Validating incoming workload JWTs from external OIDC issuers | `SecurityConfig(service_token=ServiceTokenConfig(...))` |
| MFA | TOTP, recovery codes, step-up, and login MFA (`require_at_login=False \| "enrolled" \| True`) | `SecurityConfig(mfa=MFAConfig(...))` |
| Passkeys | WebAuthn FIDO2 registration, assertion, and step-up | `SecurityConfig(passkeys=PasskeyConfig(...))` |

## Installation Extras

Core install covers JWT/JWKS validation, API-key authentication, IAP
verification, and OIDC token verification.

| Install | Enables |
| --- | --- |
| `litestar-security[mfa]` | TOTP, recovery codes, step-up; includes reference `SecretProtector` |
| `litestar-security[passkeys]` | WebAuthn passkeys |
| `litestar-security[oauth]` | OAuth/OIDC provider tree |
| `litestar-security[argon2]` | Argon2-backed local-password authentication |
| `litestar-security[all]` | Every optional capability |

## OAuth Transaction and Account Protection

The in-memory OAuth references require an `OAuthTransactionProtector` so the
PKCE verifier, nonce, and refreshable provider tokens are never kept as
plaintext. The first-party AES-256-GCM protector supplies that port to both
stores:

```python
from litestar_security.providers.oauth import (
    AESGCMOAuthTransactionProtector,
    MemoryOAuthAccountStore,
    MemoryOAuthTransactionStore,
    OAuthTransactionProtectorKey,
)


protector = AESGCMOAuthTransactionProtector(
    active_key=OAuthTransactionProtectorKey(
        "v2",
        application_secret_store.get_bytes("oauth-transaction-protector/v2"),
    ),
    retained_keys=(
        OAuthTransactionProtectorKey(
            "v1",
            application_secret_store.get_bytes("oauth-transaction-protector/v1"),
        ),
    ),
)
transactions = MemoryOAuthTransactionStore(protector=protector)
account_store = MemoryOAuthAccountStore(
    provider="github",
    client_id="github-client-id",
    protector=protector,
)
```

Values returned by the secret store are application-owned, exactly 32-byte key
material from a KMS or secret store — never source literals.

**Rotation order:** retain the previous key *before* making the new key active,
then remove it only after envelopes under the earlier version have expired or
been replaced.

An application may supply its own protector. Verify it against the public
contract with
`litestar_security.testing.assert_oauth_transaction_protector_conformance`,
run against a fresh instance factory.

## Local Accounts, Session Binding, and MFA

Compose `LocalAuth.session` with `SessionBindingConfig` (`__Host-` cookie
prefix when `secure=True`), `RegistrationPolicy`, `forwarded_client_key`, and
`MFAConfig`:

```python
from litestar_security import MFAConfig
from litestar_security.accounts import (
    AESGCMSecretProtector,
    LocalAuth,
    LocalAuthSecrets,
    RecoveryCodePepper,
    RegistrationMode,
    RegistrationPolicy,
    SecretProtectorKey,
    SessionBindingConfig,
    forwarded_client_key,
)

secret_protector = AESGCMSecretProtector(
    active_key=SecretProtectorKey(key_version="v1", key=totp_protector_key),
)

local_auth = LocalAuth.session(
    accounts=security_backend,
    secrets=LocalAuthSecrets.session(purpose_token_pepper=purpose_token_pepper),
    binding=SessionBindingConfig(
        pepper=session_binding_pepper,
        max_age=86_400 * 7,
        secure=True,
        allow_insecure=False,
        cookie_name="__Host-app-binding",
    ),
    session_resolver=security_backend,
    password_hasher=password_hasher,
    registration=RegistrationPolicy(
        mode=RegistrationMode.PUBLIC,
        require_verification=True,
    ),
    route_prefix="/api/access",
    register_routes=True,
    rate_limiter=rate_limit_service,
    events=event_sink,
    client_key=forwarded_client_key(trusted_proxies=trusted_proxy_cidrs),
)

mfa = MFAConfig(
    store=mfa_service,
    secret_protector=secret_protector,
    recovery_peppers=[RecoveryCodePepper(key_version="v1", key=recovery_code_pepper)],
    login_methods=security_backend,
    events=event_sink,
    step_up_store=step_up_service,
    require_at_login="enrolled",
    login_challenge_store=mfa_login_challenge_service,
    register_routes=True,
    route_prefix="/api/access",
    issuer="my-app",
)
```

## Google IAP (`GoogleIAPConfig` + `CachedJWKSProvider`)

Verify Google Identity-Aware Proxy (`x-goog-iap-jwt-assertion`) tokens with
`CachedJWKSProvider` and `HttpxJWKSFetcher`, and set `jwks_warmup_failure="lazy"`
on `SecurityConfig` so startup does not block on external JWKS reachability.

In **stateful mode** (loading or auto-provisioning an account row), catch
storage exceptions and return `VerificationUnavailable()` so routes fail closed
with `503` instead of misreporting a storage outage as `401`. In **stateless
mode**, construct the `User` directly from verified IAP claims:

```python
from datetime import timedelta

from litestar_security import InvalidCredentials, Principal, VerificationUnavailable
from litestar_security.providers import CachedJWKSProvider, HttpxJWKSFetcher, JWKSSource
from litestar_security.providers.iap import GoogleIAPClaims, GoogleIAPConfig

IAP_JWKS = JWKSSource(
    issuer="https://cloud.google.com/iap",
    jwks_uri="https://www.gstatic.com/iap/verify/public_key-jwk",
    algorithms=frozenset({"ES256"}),
)


class StatefulIAPIdentityResolver:
    def __init__(self, allowed_domains: frozenset[str], *, auto_provision: bool = True) -> None:
        self.allowed_domains = allowed_domains
        self.auto_provision = auto_provision

    async def resolve(self, claims: GoogleIAPClaims) -> Principal[User] | InvalidCredentials | VerificationUnavailable:
        email = (claims.email or "").strip().lower()
        if not email or email.rsplit("@", maxsplit=1)[-1] not in self.allowed_domains:
            return InvalidCredentials(code="unauthorized_domain")
        try:
            user = await load_or_provision_user(email, auto_provision=self.auto_provision)
        except Exception:
            return VerificationUnavailable()
        if user is None or not user.is_active:
            return InvalidCredentials()
        return Principal(id=str(user.id), display_name=user.email, user=user)


iap_config = GoogleIAPConfig(
    audience="/projects/123/global/backendServices/456",
    identity_resolver=StatefulIAPIdentityResolver(allowed_domains=frozenset({"example.com"})),
    jwks=CachedJWKSProvider(entries=[IAP_JWKS], fetcher=HttpxJWKSFetcher(), fetcher_owned=True),
    clock_skew=timedelta(seconds=30),
)
```

## API Keys and Self-Service Rotation

Configure `APIKeyConfig` on `SecurityConfig(api_key=...)` for request
authentication, and use `APIKeyService` with `APIKeyCodec` to mint and rotate
reveal-once keys with an overlap window:

```python
from datetime import UTC, datetime, timedelta

from litestar_security.context import CredentialRestrictions
from litestar_security.providers import APIKeyConfig, APIKeyService
from litestar_security.providers.api_key import APIKeyCodec

api_key_config = APIKeyConfig(
    store=api_key_store,
    pepper=api_key_pepper,
    identity_resolver=api_key_identity_resolver,
    usage_sink=api_key_usage_sink,
)

issuer = APIKeyService(
    config=APIKeyConfig(store=api_key_store, pepper=api_key_pepper),
    codec=APIKeyCodec(pepper=api_key_pepper),
    clock=lambda: datetime.now(UTC),
)

issued = await issuer.issue(subject_id=str(user.id), expires_at=None)
rotated = await issuer.rotate(
    current_key_id=issued.key_id,
    subject_id=str(user.id),
    restrictions=CredentialRestrictions(),
    expires_at=None,
    overlap=timedelta(hours=24),
)
```

## Purpose-Bound Capability Tokens (`LocalKeyRing`)

For short-lived signed URLs (such as signed file downloads), use `LocalKeyRing`
to mint and verify purpose-bound capability JWTs:

```python
from datetime import UTC, datetime, timedelta

from litestar_security import InvalidCredentials, VerificationUnavailable
from litestar_security.providers import LocalKeyRing, SigningKey

key_ring = LocalKeyRing(
    issuer="https://app.example.com",
    active_signing_key=SigningKey(key_id="local-1", algorithm="HS256", private_key=signing_secret),
)

token = await key_ring.mint_capability(
    purpose="signed-download",
    subject=str(user_id),
    audience="app-downloads",
    lifetime=timedelta(hours=1),
    claims={"workspace_id": str(workspace_id), "storage_path": "exports/report.csv"},
)

verified = await key_ring.verify_capability(
    token,
    purpose="signed-download",
    audience="app-downloads",
    now=datetime.now(UTC),
)
if isinstance(verified, (InvalidCredentials, VerificationUnavailable)):
    raise RuntimeError("Capability verification failed")
```

## Multi-Mechanism Routes

Because credential grants intersect rather than union, combining mechanisms
narrows rather than widens authority:

```python
from litestar import get

from litestar_security import all_of, required, requires_tenant_role


@get("/tenants/{tenant_id:str}/exports", auth=all_of("api-key", "service-jwt"))
async def tenant_exports(tenant_id: str) -> dict[str, str]:
    return {"tenant_id": tenant_id}


@get(
    "/tenants/{tenant_id:str}",
    auth=required(),
    guards=[requires_tenant_role(tenant_parameter="tenant_id", roles={"owner"})],
)
async def tenant_settings(tenant_id: str) -> dict[str, str]:
    return {"tenant_id": tenant_id}
```

Both credentials must resolve to the same subject, and the effective grants are
the intersection of what each carries.

## Cross-References

- **[Authentication](authentication.md)** — naming these mechanisms in policy.
- **[Authorization](authorization.md)** — turning a verified principal into grants.
- **[Hardening](hardening.md)** — pinning issuers, audiences, and JWKS behavior.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/providers.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/jwt-and-jwks.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/accounts.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/resource-server.rst>
