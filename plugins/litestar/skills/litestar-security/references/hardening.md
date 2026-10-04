# litestar-security — Hardening Reference

Operational rules for production deployments.

## Security Headers

Static security headers use Litestar's native response-header configuration and
are backfilled onto **every** response, including framework error responses.

`SecurityHeadersConfig.hardened()` is the recommended opt-in baseline: HSTS,
frame, content-type, and referrer protection. A handler that explicitly sets a
configured header keeps its own value.

## Content Security Policy

CSP is optional and has **no guessed allowlist** — the application supplies
every directive.

| Mode | Behavior |
| --- | --- |
| Static CSP (`CSPMode.ENFORCE`) | Adds no send hook; enforces declared policy |
| Nonce CSP | Generates at least 128 random bits per response; uses one native `before_send` hook |
| Report-only (`CSPMode.REPORT_ONLY`) | Emits the standard `Content-Security-Policy-Report-Only` header |

```python
from litestar import get
from litestar_security import csp_nonce, public
from litestar_security.headers import CSPMode, ContentSecurityPolicy, SecurityHeadersConfig

headers_config = SecurityHeadersConfig(
    csp=ContentSecurityPolicy(
        directives={
            "default-src": ["'self'"],
            "script-src": ["'self'"],
        },
        mode=CSPMode.ENFORCE,
        nonce_directives=("script-src",),
    ),
)


@get("/app", auth=public(), sync_to_thread=False)
def render_page(csp_nonce: csp_nonce) -> dict[str, str]:
    return {"nonce": csp_nonce}
```

No CSP report collector is included. Retrieve per-request nonces for script or
style tags with `csp_nonce` (a `NamedDependency[str]` alias registered when
`ContentSecurityPolicy.nonce_directives` is non-empty).

CSP `connect-src` is complementary browser hardening — it is not server-side
authentication or Origin validation.

## CSRF

Browser sessions require native CSRF coverage, derived automatically for
session-capable policies.

- `auth=public()` excludes a stateless route from native CSRF.
- A public handler that establishes cookie-authenticated state must declare
  `csrf_required=True` (HTTP-only).
- `auth=exclude()` derives no CSRF demand from default mechanisms and writes no
  native CSRF exclusion, leaving the route to Litestar's own CSRF middleware
  unless `csrf_required=True` is declared.

## Rate Limiting

Local authentication protects sensitive routes with `StoreRateLimiter` and
`RateLimitPolicy`. Default policies cover login, registration, recovery,
verification, refresh rotation, MFA, and passkey flows.

Custom rate limiters implement `RateLimiter` or wrap a distributed `Store`. Use `UnlimitedRateLimiter` when limiting is handled entirely by edge proxies.

## Pinning

Pin issuer, audience, algorithms, redirect URIs, discovery origins, JWKS URLs,
network egress, and IAP ingress.

JWKS fresh hits are lock-free; misses use single-flight refresh, bounded
documents, negative caching, stale policy, and explicit sync-worker
normalization. **Keep retired verification keys through the maximum issued-token
lifetime.**

## Secrets and HKDF Subkey Derivation

Store private keys, peppers, OAuth client secrets, session secrets, and
attestation roots in application secret management.

When deriving multiple purpose-specific 32-byte keys (`purpose-token-pepper`,
`recovery-code-pepper`, `totp-protector`, `session-binding-pepper`,
`api-key-pepper`, `session-cookie-secret`, `capability-signing`) from a single
high-entropy application `SECRET_KEY`, use `HKDF` with `SHA256` and a distinct
`info` label per purpose so no two subsystems share raw key material:

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_subkey(master_secret: str, info: bytes, *, length: int = 32) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info,
    ).derive(master_secret.encode("utf-8"))


purpose_token_pepper = derive_subkey(secret_key, b"app.auth.purpose-token-pepper.v1")
recovery_code_pepper = derive_subkey(secret_key, b"app.auth.recovery-code-pepper.v1")
totp_protector_key = derive_subkey(secret_key, b"app.auth.totp-protector.v1")
session_binding_pepper = derive_subkey(secret_key, b"app.auth.session-binding-pepper.v1")
api_key_pepper = derive_subkey(secret_key, b"app.auth.api-key-pepper.v1")
session_cookie_secret = derive_subkey(secret_key, b"app.auth.session-cookie-secret.v1")
capability_signing_key = derive_subkey(secret_key, b"app.auth.capability-signing.v1")
```

Never log raw credentials, nonces, refresh tokens, API keys, recovery codes,
passkey challenges, or MFA login challenges.

Use shared atomic rate-limit, revocation, and MFA-login challenge stores across
workers, and monitor verification-unavailable outcomes.

## Protector Key Rotation

MFA and OAuth transaction protectors use application-owned AES-256-GCM key
material — each an exact 32-byte key from a KMS or secret store.

| Purpose | Construct |
| --- | --- |
| `MFAConfig.secret_protector` | `AESGCMSecretProtector` |
| OAuth transaction store and account store | `AESGCMOAuthTransactionProtector` |

Rotate without invalidating still-live envelopes: add the former active
`SecretProtectorKey` or `OAuthTransactionProtectorKey` to `retained_keys`
**before** promoting a new `active_key`.

Check an application-owned replacement with
`litestar_security.testing.assert_secret_protector_conformance` or
`assert_oauth_transaction_protector_conformance`.

## MFA Rollout

`MFAConfig.require_at_login` supports three modes:

- `False` (default) — MFA is used for step-up authentication; login succeeds on
  primary factor alone.
- `"enrolled"` — Login requires MFA completion only for accounts that have
  already enrolled a viable factor, allowing phased rollout.
- `True` — Login requires MFA completion for **every** account.

Before enabling `MFAConfig(require_at_login=True)` in a deployment:

- Use `require_at_login="enrolled"` during migration and enroll a viable factor
  for **every** affected account first, or unenrolled accounts lock themselves
  out.
- Verify the completion routes with the same CSRF and session middleware used
  in production.
- Ensure the MFA-login challenge store **atomically burns** a revealed
  challenge. A process-local implementation is suitable only for a single
  worker.
- Treat the reveal-once challenge and the completion proof like passwords —
  keep both out of application, proxy, and audit logs.

## Audit Events and Store Conformance Testing

Implement `SecurityEventSink` (`async def emit(self, event: SecurityEvent) -> None`)
and pass it to `LocalAuth`, `MFAConfig`, and custom audit hooks (such as MCP
`after_tool_call` callbacks) to persist structured `SecurityEvent` records.

Verify custom database-backed stores and rate limiters against the upstream
contract using `litestar_security.testing`:

- `assert_rate_limiter_conformance`
- `assert_api_key_store_conformance`
- `assert_security_backend_conformance`
- `assert_session_registry_conformance`
- `assert_secret_protector_conformance`
- `assert_oauth_transaction_protector_conformance`

## Cross-References

- **[Providers](providers.md)** — protector construction and rotation order.
- **[WebSockets](websockets.md)** — Origin validation and close-code discipline.
- **[Litestar middleware](../../litestar/references/middleware.md)** — CORS, CSRF, and allowed-hosts configuration.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/hardening.rst>
- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/rate-limiting.rst>
