# litestar-security — WebSocket Reference

WebSocket authentication uses the same principal, context, policy, and guards
as HTTP.

## Transport Rules

- Browser cookie authentication additionally requires an **exact allowed
  `Origin`**.
- Non-browser clients may use the `Authorization` header.
- Bearer credentials in query strings are **prohibited**.

Authentication, authorization, and verification availability map to distinct
close codes. Reserve one code for expired authentication and a different one
for a real authorization denial, so the client can refresh in the first case
and stop retrying in the second.

Long-lived sockets may use a bounded detached authorization snapshot refresher
plus an application revocation event source. The runtime does **not** retain a
request database transaction for the socket lifetime.

## Connect Tokens

One-time WebSocket connect tokens are short-lived, HMAC-digested, bound to
route / origin / policy, and atomically consumed. They are the answer when a
browser cannot present the normal credential transport.

This is the pattern often called a WebSocket *ticket*. It is named for what it
authorizes here, because the library already issues access and refresh tokens
to users and "ticket" gave no clue which one a value was.

Configure `SecurityConfig(websocket=WebSocketSecurityConfig(connect_token_store=...))`
to let the plugin inject a `WebSocketConnectTokenIssuer` into an authenticated
mint endpoint. Use the **registered WebSocket handler name** and the **exact
browser Origin** that will open the connection:

```python
from typing import Any

from litestar import post
from litestar.di import NamedDependency

from litestar_security import (
    Principal,
    SecurityContext,
    WebSocketConnectTokenIssuer,
    required,
)


@post("/connect-tokens", auth=required())
async def mint_connect_token(
    principal: NamedDependency[Principal[Any]],
    security_context: NamedDependency[SecurityContext],
    security_epoch: NamedDependency[int],
    websocket_connect_tokens: NamedDependency[WebSocketConnectTokenIssuer],
) -> dict[str, str]:
    issued = await websocket_connect_tokens.issue(
        "reports.socket",
        principal=principal,
        context=security_context,
        origin="https://browser.example",
        security_epoch=security_epoch,
    )
    return {"connect_token": issued.value}
```

The client supplies `connect_token` to the handshake and presents that exact
Origin.

## Security Epoch

The application-owned `security_epoch` dependency must return the account's
current authoritative epoch. Password resets and other security changes then
invalidate outstanding connect tokens.

Local-auth configuration automatically wires its account store for
handshake-time epoch revalidation.

## Manual Control

`issue_websocket_connect_token()` and `WebSocketConnectTokenService` remain
available when an application needs manual control of connect-token bindings or
storage. `InMemoryWebSocketConnectTokenStore` is suitable only for a single
worker — connect tokens must be consumed atomically across the deployment.

## WebSocket Close Codes

The runtime maps security outcomes to standard and application close codes (`WebSocketCloseCodes`):

| Outcome | Code | Meaning |
| --- | --- | --- |
| Unauthenticated | `4401` | Missing or invalid credential, expired connect token |
| Unauthorized | `4403` | Guard denial, missing role or scope |
| Verification Unavailable | `1013` | Fails closed on dependency failure / try again later |

## Cross-References

- **[Authentication](authentication.md)** — policy compilation for WebSocket handlers.
- **[Authorization](authorization.md)** — snapshot refresh for long-lived connections.
- **[litestar-realtime](../../litestar-realtime/SKILL.md)** — socket handlers, Channels backends, and SSE.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/websockets.rst>
