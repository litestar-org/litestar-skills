# litestar-security — Providers Reference

A provider is where identity is established. Adding one makes its
authentication mechanism available; route policy decides where that mechanism
is accepted, and the application `authorization_resolver` loads grants for the
verified principal.

## Choosing a Provider

| Provider | Use for |
| --- | --- |
| Local accounts | Session, token, and hybrid applications |
| OAuth / OpenID Connect | Browser sign-in and account linking |
| Google IAP | Verifying the assertion added by the IAP proxy, for one exact audience |
| API keys | Service clients, from a digest-only application store |
| Workload JWTs | Non-user services, through a pinned issuer, audience, and JWKS endpoint |

## Installation Extras

Core install already covers JWT/JWKS validation, API-key authentication, IAP
verification, and OIDC token verification.

| Install | Enables |
| --- | --- |
| `litestar-security[mfa]` | TOTP, recovery codes, step-up; includes the reference `SecretProtector` |
| `litestar-security[passkeys]` | WebAuthn passkeys |
| `litestar-security[oauth]` | OAuth/OIDC provider tree (capability marker; adds no distribution) |
| `litestar-security[argon2]` | Argon2-backed local-password authentication |
| `litestar-security[all]` | Every optional capability |

## OAuth Transaction and Token Protection

The in-memory OAuth references require an `OAuthTransactionProtector` so the
PKCE verifier, nonce, and refreshable provider tokens are never kept as
plaintext. The first-party AES-256-GCM protector supplies that port to both
stores:

```python
from litestar_security.providers.oauth import (
    AESGCMOAuthTransactionProtector,
    MemoryOAuthTransactionStore,
    MemoryTokenVault,
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
token_vault = MemoryTokenVault(
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

from litestar_security import all_of, required, requires_team_role


@get("/teams/{team_id:str}/exports", auth=all_of("api_key", "workload_jwt"))
async def team_exports(team_id: str) -> dict[str, str]:
    return {"team_id": team_id}


@get(
    "/teams/{team_id:str}",
    auth=required(),
    guards=[requires_team_role(team_parameter="team_id", roles={"owner"})],
)
async def team_settings(team_id: str) -> dict[str, str]:
    return {"team_id": team_id}
```

Both credentials must resolve to the same subject, and the effective grants are
the intersection of what each carries.

## Cross-References

- **[Authentication](authentication.md)** — naming these mechanisms in policy.
- **[Authorization](authorization.md)** — turning a verified principal into grants.
- **[Hardening](hardening.md)** — pinning issuers, audiences, and JWKS behavior.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/providers.rst>
- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/jwt-and-jwks.rst>
- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/accounts.rst>
- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/resource-server.rst>
