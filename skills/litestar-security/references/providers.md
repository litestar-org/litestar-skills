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
| Google IAP | Verifying Google Identity-Aware Proxy JWT assertions | `SecurityConfig(iap=GoogleIAPConfig(...))` |
| API keys | Machine/service clients with digest-only storage | `SecurityConfig(api_key=APIKeyConfig(...))` |
| Local JWKS | Exposing application public keys for issued JWTs | `SecurityConfig(local_jwks=LocalJWKSConfig(...))` |
| Service tokens | Validating incoming workload JWTs from external OIDC issuers | `SecurityConfig(service_token=ServiceTokenConfig(...))` |
| MFA | TOTP, recovery codes, and step-up authentication | `SecurityConfig(mfa=MFAConfig(...))` |
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
