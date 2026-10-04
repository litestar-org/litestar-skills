# Litestar App Deployment

Production deployment patterns for Litestar ASGI applications: server config, IAP authentication, static asset serving, Docker layout.

## ASGI Server Configuration

### Entry Point

Litestar apps use the CLI for server startup:

```bash
# Standard startup (Granian backend via litestar-granian plugin)
litestar run --host 0.0.0.0 --port 8080

# Auto-reload during development
litestar run --reload

# Production multi-worker with Granian v0.16+ supervision, access logs, and worker recycling
litestar run \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 4 \
    --runtime-threads 2 \
    --runtime-mode mt \
    --backpressure 64 \
    --granian-access-log \
    --respawn-failed-workers \
    --workers-max-rss 512 \
    --workers-kill-timeout 30
```

The `LITESTAR_APP` environment variable specifies the application factory or instance:

```bash
export LITESTAR_APP="myapp.asgi:create_app"
```

Register `GranianPlugin(static="auto")` on `Litestar(plugins=[...])` so `litestar run` uses the supervised Granian runner (forwarding `SIGINT`, `SIGTERM`, and `SIGHUP` to the Granian process group with a `--workers-kill-timeout` drain window) and offloads static file delivery (`VitePlugin` `bundle_dir` or `static_files_config`) directly to Granian's Rust HTTP server. For Granian-specific tuning, see [`../../litestar-granian/SKILL.md`](../../litestar-granian/SKILL.md).

### Dockerfile CMD

```dockerfile
ENTRYPOINT ["tini", "--"]
CMD ["litestar", "run", "--host", "0.0.0.0", "--port", "8080"]
```

### Server Backends

Litestar supports multiple ASGI servers:

| Server | Use Case | Notes |
| --- | --- | --- |
| **granian** | Default (via `litestar-granian`) | Rust-based, lower latency, HTTP/2, native static file serving (`GranianPlugin(static="auto")`) |
| **uvicorn** | Fallback | Well-tested, broader middleware ecosystem |

Prefer Granian for new projects. Drop to uvicorn only when Granian's HTTP/2 behavior is incompatible with your deploy target.

## IAP (Identity-Aware Proxy) Authentication

Google Cloud IAP provides authentication at the infrastructure layer. Litestar can consume IAP JWT tokens for user identity.

### How It Works

1. Google Cloud IAP intercepts requests before they reach the application
2. IAP adds the `X-Goog-IAP-JWT-Assertion` header with a signed JWT
3. Litestar middleware verifies the JWT and extracts user identity
4. Users are auto-provisioned on first access (if enabled)

### Authentication Flow

```text
Client -> Cloud IAP -> Load Balancer -> Litestar App
                                          |
                                    X-Goog-IAP-JWT-Assertion header
                                          |
                                    IAPAuthenticationMiddleware
                                          |
                                    verify_iap_token()
                                          |
                                    resolve_iap_user()
                                          |
                                    (auto-provision if new)
```

### Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH_IAP_ENABLED` | `false` | Enable IAP JWT authentication |
| `IAP_AUDIENCE` | `""` | Expected audience claim (required when IAP enabled) |
| `AUTH_IAP_AUTO_PROVISION` | `false` | Auto-create users from IAP token claims |
| `IAP_ALLOWED_DOMAINS` | `[]` | Email domain allowlist for auto-provisioned users |

### IAP Token Verification

The middleware verifies IAP JWTs using Google's public JWKS endpoint:

```python
import asyncio
from collections.abc import Sequence

import jwt

IAP_AUTH_HEADER_KEY = "X-Goog-IAP-JWT-Assertion"
IAP_ISSUER = "https://cloud.google.com/iap"


async def verify_iap_token(raw_token: str, audience: str | Sequence[str]) -> IAPToken:
    """Verify IAP JWT using ES256 algorithm against Google JWKS."""
    jwks_client = await get_jwks_client()
    signing_key = await jwks_client.get_signing_key(raw_token)
    token_data = await asyncio.to_thread(
        jwt.decode,
        raw_token,
        key=signing_key.key,
        algorithms=["ES256"],
        audience=audience,
        issuer=IAP_ISSUER,
        options={"require": ["exp", "iat", "aud", "sub"]},
    )
    return IAPToken(sub=token_data["sub"], email=token_data.get("email"))
```

### User Auto-Provisioning

When `AUTH_IAP_AUTO_PROVISION=true`, users are created automatically from IAP claims:

```python
async def resolve_iap_user(email: str, user_service: UserService) -> User | None:
    """Validate the IAP email domain against the allowlist and auto-provision missing users when enabled."""
    email_domain = email.rsplit("@", maxsplit=1)[-1].lower()
    if email_domain not in allowed_domains:
        return None

    user = await user_service.get_user_by_email(email)

    if user is None and settings.auth.IAP_AUTO_PROVISION_USERS:
        user = await user_service.create_user(
            UserCreate(
                email=email,
                name=email.split("@")[0],
                password=random_password,
                is_verified=True,
            )
        )
    return user
```

### Dual Authentication (IAP + Local JWT)

The `IAPAuthenticationMiddleware` supports both IAP and local JWT authentication. IAP takes priority when the header is present, with fallback to Bearer token in the Authorization header:

```python
class IAPAuthenticationMiddleware(AbstractAuthenticationMiddleware):
    """Authenticate requests via Google Cloud IAP JWT header first, falling back to local Bearer JWT."""

    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        """Verify X-Goog-IAP-JWT-Assertion when enabled, or fall back to Authorization Bearer token."""
        if self.iap_enabled and self.iap_audience:
            iap_token = connection.headers.get("X-Goog-IAP-JWT-Assertion")
            if iap_token:
                token = await verify_iap_token(iap_token, self.iap_audience)
                user = await self.retrieve_iap_user_handler(token, connection)
                if user:
                    return AuthenticationResult(user=user, auth=token)

        if self.local_auth_enabled:
            auth_header = connection.headers.get("Authorization")
            if auth_header:
                return await self.authenticate_bearer_header(auth_header, connection)
        raise NotAuthorizedException()
```

## Static Asset Serving with Vite

For Vite-specific config (modes, TypeGen, Inertia integration), see [`../../litestar-vite/SKILL.md`](../../litestar-vite/SKILL.md). When running behind Cloud Run, Railway, or an ingress proxy, set `LITESTAR_TRUSTED_PROXIES=*` (or the proxy CIDR) and `RuntimeConfig(trusted_proxies=...)` so `litestar-vite`'s `ProxyHeadersMiddleware` honors `X-Forwarded-Proto` and `X-Forwarded-Host` when generating asset URLs.

### Build Integration

Frontend assets are built during the Docker image build and served by Litestar (or offloaded to Granian via `GranianPlugin(static="auto")`):

```dockerfile
# Install bun for JS bundling
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun

# Install JS dependencies
WORKDIR /app/src/js/web
RUN bun install --frozen-lockfile

# Build frontend assets
RUN uv run litestar assets build \
    && cd src/js/web && bun run build:all
```

### Email Templates

Email templates are built separately using bun:

```dockerfile
# Install email template dependencies
WORKDIR /app/src/js/templates
RUN bun install --frozen-lockfile

# Build email templates
RUN cd src/js/templates && bun run build:emails
```

The built templates are included in the Python wheel and served from the application's static directory.

## Deployment Checklist

- [ ] Set `LITESTAR_APP` environment variable to the application factory
- [ ] Set `LITESTAR_TRUSTED_PROXIES` when deployed behind Cloud Run, Railway, or an ingress load balancer
- [ ] Configure `AUTH_IAP_ENABLED` and `IAP_AUDIENCE` if behind Cloud IAP
- [ ] Set `IAP_ALLOWED_DOMAINS` to restrict auto-provisioned user domains
- [ ] Build frontend assets (Vite) and email templates (bun) in Docker build
- [ ] Use `tini` as init system for proper signal handling
- [ ] Run as non-root user (UID 65532)
- [ ] Expose port 8080 (Cloud Run/GKE convention) or 8000
- [ ] Provide `/health` endpoint for readiness/liveness probes
- [ ] Run background workers as a separate process (`litestar workers run` for `litestar-saq` or `litestar queues run` / `run-consumer` for `litestar-queues`) in production
- [ ] Configure Granian worker count, runtime threads, and static file offload via `GranianPlugin` / CLI flags — see [`../../litestar-granian/SKILL.md`](../../litestar-granian/SKILL.md)

## Cross-references

- Granian server tuning: [`../../litestar-granian/SKILL.md`](../../litestar-granian/SKILL.md)
- Vite asset bundling and TypeGen: [`../../litestar-vite/SKILL.md`](../../litestar-vite/SKILL.md)
- Queue worker deployment (`litestar-queues`): [`../../litestar-queues/SKILL.md`](../../litestar-queues/SKILL.md)
- SAQ worker deployment (`litestar-saq`): [`../../litestar-saq/SKILL.md`](../../litestar-saq/SKILL.md)
- IAP middleware lives in: [middleware.md](../../litestar/references/middleware.md)

## Official References

- <https://docs.litestar.dev/main/usage/cli.html>
- <https://cloud.google.com/iap/docs/identity-howto>
- <https://cloud.google.com/iap/docs/signed-headers-howto>
- <https://docs.litestar.dev/main/usage/middleware/index.html>
