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
| Static CSP | Adds no send hook |
| Nonce CSP | Generates at least 128 random bits per response; uses one native `before_send` hook |
| Report-only | Emits the standard report-only header |

No CSP report collector is included. Retrieve nonces for script or style tags
with `csp_nonce`.

CSP `connect-src` is complementary browser hardening — it is not server-side
authentication or Origin validation.

## CSRF

Browser sessions require native CSRF coverage, derived automatically for
session-capable policies.

- `auth=public()` excludes a stateless route from native CSRF.
- A public handler that establishes cookie-authenticated state must declare
  `csrf_required=True` (HTTP-only).
- `auth=exclude()` bypasses authentication only; session-capable excluded
  routes keep their derived CSRF coverage.

## Pinning

Pin issuer, audience, algorithms, redirect URIs, discovery origins, JWKS URLs,
network egress, and IAP ingress.

JWKS fresh hits are lock-free; misses use single-flight refresh, bounded
documents, negative caching, stale policy, and explicit sync-worker
normalization. **Keep retired verification keys through the maximum issued-token
lifetime.**

## Secrets

Store private keys, peppers, OAuth client secrets, session secrets, and
attestation roots in application secret management.

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
| OAuth transaction store and token vault | `AESGCMOAuthTransactionProtector` |

Rotate without invalidating still-live envelopes: add the former active
`SecretProtectorKey` or `OAuthTransactionProtectorKey` to `retained_keys`
**before** promoting a new `active_key`.

Check an application-owned replacement with
`litestar_security.testing.assert_secret_protector_conformance` or
`assert_oauth_transaction_protector_conformance`.

## MFA Rollout

Before enabling `MFAConfig.require_at_login` in a deployment:

- Enroll a viable factor for **every** affected account, or those accounts lock
  themselves out.
- Verify the completion routes with the same CSRF and session middleware used
  in production.
- Ensure the MFA-login challenge store **atomically burns** a revealed
  challenge. A process-local implementation is suitable only for a single
  worker.
- Treat the reveal-once challenge and the completion proof like passwords —
  keep both out of application, proxy, and audit logs.

## Cross-References

- **[Providers](providers.md)** — protector construction and rotation order.
- **[WebSockets](websockets.md)** — Origin validation and close-code discipline.
- **[litestar-middleware](../../litestar-middleware/SKILL.md)** — CORS, CSRF, and allowed-hosts configuration.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/hardening.rst>
- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/rate-limiting.rst>
