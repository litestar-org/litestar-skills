# litestar-mcp — Stateless Protocol Reference

`0.12.0` adopts stateless MCP, protocol `2026-07-28`. This is a breaking change
to the transport, not just a version bump.

## What Was Removed

| Removed | Replacement |
| --- | --- |
| `initialize` handshake and `notifications/initialized` | Nothing — POST each request directly |
| Sessions and the `Mcp-Session-Id` header | Nothing — every request is self-describing |
| `ping` | Nothing |
| `GET /mcp` SSE transport handler | `subscriptions/listen` over POST |
| `DELETE /mcp` session termination | Nothing |
| Replay | `subscriptions/listen` filters |
| `GET /.well-known/mcp-server.json` | `server/discover` |

The transport is now **POST-only and request-scoped**. `/mcp` accepts `POST`
(and `OPTIONS`); no other method is registered.

## Request Metadata

Every request carries protocol, client, method, name, and custom-header
metadata, so the server needs no prior handshake to interpret it. Call
`server/discover` to obtain capabilities.

## Subscriptions

`subscriptions/listen` provides filtered streams over the POST transport,
replacing the removed GET SSE channel.

| Option | Default | Purpose |
| --- | --- | --- |
| `subscription_max_streams` | `10000` | Max concurrent SSE streams |
| `subscription_keepalive_seconds` | `15.0` | Seconds between keepalive pings |
| `subscription_channels` | `None` | Channels backend backing fan-out |

Supply `subscription_channels` with a Channels backend when subscription
delivery must span processes; the default keeps fan-out in-process.

## Tasks Extension

The opt-in `io.modelcontextprotocol/tasks` extension adds durable task records
backed by a Litestar `Store`.

```python
from litestar_mcp import LitestarMCP, MCPConfig, MCPTaskConfig

plugin = LitestarMCP(MCPConfig(tasks=MCPTaskConfig()))
```

Pass `MCPTaskConfig` to configure the backing `Store` (defaults to in-memory)
and the record TTLs. `tasks=True` enables the extension with defaults.

## Multi-Round-Trip Results

Tools, resources, and prompts can return typed multi-round-trip (MRTR)
`input_required` results, letting a server ask the client for more input
mid-call instead of failing.

## Response Caching

| Option | Default | Purpose |
| --- | --- | --- |
| `cache_ttl_ms` | `0` | Response cache lifetime in milliseconds; `0` disables caching |
| `cache_scope` | `"private"` | Whether a cached response may be shared between callers |

Leave `cache_scope="private"` unless a response is genuinely identical for every
caller — `"public"` allows sharing across principals, so it must never be used
for responses derived from `request.user` or `request.auth`.

## Migrating a Client

1. Delete the `initialize` / `notifications/initialized` exchange.
2. Stop sending and storing `Mcp-Session-Id`.
3. Replace manifest discovery from `/.well-known/mcp-server.json` with a
   `server/discover` call.
4. Replace any `GET /mcp` SSE consumption with `subscriptions/listen`.
5. Drop `DELETE /mcp` teardown.

The stdio bridge handles this transparently and additionally forwards
independent request-scoped POST streams concurrently.

## Cross-References

- **[litestar-realtime](../../litestar-realtime/SKILL.md)** — Channels backends for `subscription_channels`.
- **[litestar-auth-guards](../../litestar-auth-guards/SKILL.md)** — guards applied to the MCP router.

## Official References

- <https://github.com/cofin/litestar-mcp/blob/v0.12.0/docs/changelog.rst>
- <https://github.com/cofin/litestar-mcp/tree/v0.12.0>
