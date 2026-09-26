# litestar-mcp — Stateless Protocol Reference

`litestar-mcp` adheres to the stateless MCP specification (protocol `2026-07-28`). The transport is POST-only and request-scoped.

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

The transport is **POST-only and request-scoped**. `/mcp` accepts `POST` (and `OPTIONS`); no other method is registered on the transport path.

## Request Metadata

Every request supplies the protocol version, JSON-RPC method, and client
capabilities in both `params._meta` and matching HTTP headers. Calls that
address a tool, resource, prompt, or task also supply a matching `Mcp-Name`
header (`tools/call` → `params.name`, `resources/read` → `params.uri`,
`prompts/get` → `params.name`, `tasks/*` → `params.taskId`). Tool schemas that
declare `x-mcp-header` properties also require matching `Mcp-Param-<Header>`
headers when those arguments are present. Call `server/discover` to obtain
capabilities.

| Surface | Key / Header | Purpose |
| --- | --- | --- |
| `params._meta` | `io.modelcontextprotocol/protocolVersion` | Must be `"2026-07-28"` |
| `params._meta` | `io.modelcontextprotocol/clientCapabilities` | Client capability object (`{}` when none) |
| `params._meta` | `io.modelcontextprotocol/clientInfo` | Optional `{"name": ..., "version": ...}` |
| HTTP header | `MCP-Protocol-Version` | Must match `params._meta["io.modelcontextprotocol/protocolVersion"]` |
| HTTP header | `Mcp-Method` | Must match the JSON-RPC `method` |
| HTTP header | `Mcp-Name` | Required for `tools/call`, `resources/read`, `prompts/get`, and `tasks/*` |
| HTTP header | `Mcp-Param-<Header>` | Required when an `x-mcp-header`-annotated tool argument is non-null |

## Subscriptions

`subscriptions/listen` provides filtered streams over the POST transport, replacing the removed GET SSE channel.

| Option | Default | Purpose |
| --- | --- | --- |
| `subscription_max_streams` | `10000` | Max concurrent SSE streams |
| `subscription_keepalive_seconds` | `15.0` | Seconds between keepalive pings |
| `subscription_channels` | `None` | Channels backend backing fan-out |

Supply `subscription_channels` with a Channels backend when subscription delivery must span processes; the default keeps fan-out in-process.

## Tasks Extension

The opt-in `io.modelcontextprotocol/tasks` extension adds task records backed by a Litestar `Store`.

```python
from litestar_mcp import LitestarMCP, MCPConfig, MCPTaskConfig

plugin = LitestarMCP(MCPConfig(tasks=MCPTaskConfig()))
```

Pass `MCPTaskConfig` to configure the backing `Store` (defaults to in-memory) and the record TTLs. `tasks=True` enables the extension with defaults.

## Multi-Round-Trip Results

Tools, resources, and prompts can return typed multi-round-trip (MRTR) `input_required` results via `MCPInputRequiredResult`, letting a server ask the client for more input mid-call instead of failing.

## Response Caching

| Option | Default | Purpose |
| --- | --- | --- |
| `cache_ttl_ms` | `0` | Response cache lifetime in milliseconds; `0` disables caching |
| `cache_scope` | `"private"` | Whether a cached response may be shared between callers |

Leave `cache_scope="private"` unless a response is genuinely identical for every caller — `"public"` allows sharing across principals, so it must never be used for responses derived from `request.user` or `request.auth`.

## Migrating a Client

1. Delete the `initialize` / `notifications/initialized` exchange.
2. Stop sending and storing `Mcp-Session-Id`.
3. Replace manifest discovery from `/.well-known/mcp-server.json` with a `server/discover` call.
4. Replace any `GET /mcp` SSE consumption with `subscriptions/listen`.
5. Drop `DELETE /mcp` teardown.

The stdio bridge handles this transparently and additionally forwards independent request-scoped POST streams concurrently.

## Cross-References

- **[Litestar Channels & SSE](../../litestar/references/channels-and-sse.md)** — Channels backends for `subscription_channels`.
- **[Litestar Auth & Guards](../../litestar/references/auth-and-guards.md)** — guards applied to the MCP router.

## Official References

- <https://github.com/cofin/litestar-mcp/blob/v0.13.2/docs/changelog.rst>
- <https://github.com/cofin/litestar-mcp/tree/v0.13.2>
