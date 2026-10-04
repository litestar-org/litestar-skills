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
| `MCPConfig.register_agent_card` and MCP-owned `GET /.well-known/agent-card.json` | `LitestarA2A` (`litestar-mcp[a2a]`) |
| `litestar_mcp.auth` and `MCPConfig.auth` / `MCPConfig.register_oauth_protected_resource` | `litestar-security` (`MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` and `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`) |

The transport is **POST-only and request-scoped**. `/mcp` accepts `POST` (and `OPTIONS`); no other method is registered on the transport path.

## Request Metadata

Every request supplies the protocol version, JSON-RPC method, and client
capabilities in both `params._meta` and matching HTTP headers. Calls that
address a tool, resource, prompt, skill, directory, or task also supply a matching `Mcp-Name`
header (`tools/call` → `params.name`, `resources/read` → `params.uri`,
`prompts/get` → `params.name`, `tasks/*` → `params.taskId`, `skills/get` → `params.uri`,
`resources/directory/read` → `params.uri`). Tool schemas that
declare `x-mcp-header` properties also require matching `Mcp-Param-<Header>`
headers when those arguments are present. Call `server/discover` to obtain
capabilities.

| Surface | Key / Header | Purpose |
| --- | --- | --- |
| `params._meta` | `io.modelcontextprotocol/protocolVersion` | Must be `"2026-07-28"` |
| `params._meta` | `io.modelcontextprotocol/clientCapabilities` | Client capability object (`{}` when none) |
| `params._meta` | `io.modelcontextprotocol/clientInfo` | Optional `{"name": ..., "version": ...}` |
| `params._meta` | `progressToken` | Optional string or integer token enabling `notifications/progress` SSE streaming |
| HTTP header | `MCP-Protocol-Version` | Must match `params._meta["io.modelcontextprotocol/protocolVersion"]` |
| HTTP header | `Mcp-Method` | Must match the JSON-RPC `method` |
| HTTP header | `Mcp-Name` | Required for `tools/call`, `resources/read`, `prompts/get`, `tasks/*`, `skills/get`, and `resources/directory/read` |
| HTTP header | `Mcp-Param-<Header>` | Required when an `x-mcp-header`-annotated tool argument is non-null |

## Subscriptions And Stream Bounds

`subscriptions/listen` provides filtered streams over the POST transport, replacing the removed GET SSE channel. When a request supplies `params._meta.progressToken`, the response also upgrades to an SSE stream emitting `notifications/progress` events before the final JSON-RPC response.

| Option | Default | Purpose |
| --- | --- | --- |
| `subscription_max_streams` | `10000` | Max concurrent SSE streams |
| `subscription_keepalive_seconds` | `15.0` | Seconds between keepalive pings |
| `stream_queue_capacity` | `256` | Max queued progress notifications per request stream |
| `stream_cleanup_timeout` | `5.0` | Seconds allowed for cooperative stream producer cleanup |
| `subscription_channels` | `None` | Channels backend backing fan-out |

Supply `subscription_channels` with a Channels backend when subscription delivery must span processes; the default keeps fan-out in-process.

## Tasks Extension

The opt-in `io.modelcontextprotocol/tasks` extension adds task records backed by a Litestar `Store`.

```python
from litestar_mcp import LitestarMCP, MCPConfig, MCPTaskConfig

plugin = LitestarMCP(MCPConfig(tasks=MCPTaskConfig()))
```

Pass `MCPTaskConfig` to configure the backing `Store` (defaults to in-memory) and the record TTLs. `tasks=True` enables the extension with defaults.

## Skills Extension

The opt-in `io.modelcontextprotocol/skills` extension exposes `<path>/<name>/SKILL.md` directories as a deterministic catalog (`SkillCatalog` in `litestar_mcp.mcp.skills`).

```python
from pathlib import Path

from litestar_mcp import LitestarMCP, MCPConfig, MCPSkillsConfig

plugin = LitestarMCP(
    MCPConfig(
        skills=MCPSkillsConfig(
            paths=[Path("skills")],
            directory_read=True,
            max_files_per_skill=512,
            max_bytes_per_skill=16_777_216,
        )
    )
)
```

When configured, `server/discover` advertises `capabilities.extensions["io.modelcontextprotocol/skills"] = {"directoryRead": True}` and registers `skills/list`, `skills/get`, `resources/directory/read` (when `directory_read=True`), and `skill://` support in `resources/read` and `resources/list` with SHA-256 digest verification on every file read.

## Multi-Round-Trip Results

Tools, resources, and prompts can return typed multi-round-trip (MRTR) `input_required` results via `MCPInputRequiredResult`, letting a server ask the client for more input mid-call instead of failing.

## Response Caching

| Option | Default | Purpose |
| --- | --- | --- |
| `cache_ttl_ms` | `0` | Response cache lifetime in milliseconds; `0` disables caching |
| `cache_scope` | `"private"` | Whether a cached response may be shared between callers |

Cacheable methods are `server/discover`, `tools/list`, `resources/list`, `resources/templates/list`, `resources/read`, `prompts/list`, `skills/list`, and `skills/get`. Leave `cache_scope="private"` unless a response is genuinely identical for every caller — `"public"` allows sharing across principals, so it must never be used for responses derived from `request.user` or `request.auth`.

## Migrating a Client

1. Delete the `initialize` / `notifications/initialized` exchange.
2. Stop sending and storing `Mcp-Session-Id`.
3. Replace manifest discovery from `/.well-known/mcp-server.json` with a `server/discover` call.
4. Replace any `GET /mcp` SSE consumption with `subscriptions/listen`.
5. Drop `DELETE /mcp` teardown.
6. Use `LitestarA2A` (`litestar-mcp[a2a]`) for `/.well-known/agent-card.json` and `/a2a`, and `litestar-security` (`ProtectedResourceConfig`) for `/.well-known/oauth-protected-resource`.

The stdio bridge handles MCP transport headers transparently and forwards independent request-scoped POST streams concurrently.

## Cross-References

- **[Litestar Channels & SSE](../../litestar/references/channels-and-sse.md)** — Channels backends for `subscription_channels`.
- **[litestar-security](../../litestar-security/SKILL.md)** — `SecurityPlugin`, `ProtectedResourceConfig`, and `AUTH_POLICY_OPT_KEY` / `required(...)` route policies.
- **[Litestar Auth & Guards](../../litestar/references/auth-and-guards.md)** — guards applied to the MCP router.

## Official References

- <https://github.com/cofin/litestar-mcp/releases/tag/v0.14.0>
- <https://cofin.github.io/litestar-mcp/>
