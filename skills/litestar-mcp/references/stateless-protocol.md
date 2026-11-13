# litestar-mcp — Stateless Protocol Reference

`litestar-mcp` implements MCP Streamable HTTP (`SUPPORTED_PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26")`):

- **Default `2026-07-28` mode:** Stateless and request-scoped on `POST /mcp`. `GET /mcp` and `DELETE /mcp` return `405 Method Not Allowed`, and `_MODERN_DISALLOWED_METHODS` (`initialize`, `ping`, `resources/subscribe`, `resources/unsubscribe`, `logging/setLevel`) return `-32601` (`404`).
- **Pre-`2026-07-28` compatibility (`2025-11-25`, `2025-06-18`, `2025-03-26`):** Supports stateful sessions (`initialize` issues `Mcp-Session-Id` stored in `MCPSessionStore` with `session_ttl_seconds=3600.0`), `notifications/initialized`, `ping`, `GET /mcp` SSE (`enable_get_sse=True`), `DELETE /mcp` session termination, `resources/subscribe`, `resources/unsubscribe`, and `logging/setLevel`.

## Protocol Modes & Removed Legacy Surfaces

| Feature | `2026-07-28` Stateless Mode | Pre-`2026-07-28` (`2025-*`) / Replacement |
| --- | --- | --- |
| `initialize` / `notifications/initialized` / `ping` | Disallowed (`-32601` / `404`) | Supported for `2025-*` clients |
| Sessions and `Mcp-Session-Id` | Omitted — self-describing requests | Supported via `MCPSessionStore` (`session_ttl_seconds=3600.0`) |
| `GET /mcp` SSE stream | Disallowed (`405`) — use `subscriptions/listen` | Supported when `enable_get_sse=True` |
| `DELETE /mcp` session termination | Disallowed (`405`) | Terminates `Mcp-Session-Id` session |
| `resources/subscribe`, `resources/unsubscribe`, `logging/setLevel` | Disallowed (`-32601` / `404`) | Supported for `2025-*` sessions |
| Replay | Removed | `subscriptions/listen` filters |
| `GET /.well-known/mcp-server.json` | Removed | `server/discover` |
| `MCPConfig.register_agent_card` & MCP-owned `agent-card.json` | Removed | `LitestarA2A` (`litestar-mcp[a2a]`) or `agent_to_a2a` |
| `litestar_mcp.auth` & `MCPConfig.register_oauth_protected_resource` | Removed | `litestar-security` (`MCPConfig(auth=required(...))` / `route_opt`, `ProtectedResourceConfig`) |

In `2026-07-28` mode, `/mcp` accepts only `POST` (and `OPTIONS`) — `GET` and `DELETE` are reserved for `2025-*` sessions (`enable_get_sse=True`).

## Request Metadata And `MCPStreamableHTTPClient`

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
| `params._meta` | `io.modelcontextprotocol/protocolVersion` | `"2026-07-28"` (for modern stateless mode; `2025-*` uses `initialize`) |
| `params._meta` | `io.modelcontextprotocol/clientCapabilities` | Client capability object (`{}` when none) |
| `params._meta` | `io.modelcontextprotocol/clientInfo` | Optional `{"name": ..., "version": ...}` |
| `params._meta` | `progressToken` | Optional string or integer token enabling `notifications/progress` SSE streaming |
| HTTP header | `MCP-Protocol-Version` | Must match `params._meta["io.modelcontextprotocol/protocolVersion"]` |
| HTTP header | `Mcp-Method` | Must match the JSON-RPC `method` |
| HTTP header | `Mcp-Name` | Required for `tools/call`, `resources/read`, `prompts/get`, `tasks/*`, `skills/get`, and `resources/directory/read` |
| HTTP header | `Mcp-Param-<Header>` | Required when an `x-mcp-header`-annotated tool argument is non-null |

Use `MCPStreamableHTTPClient`, `prepare_mcp_request`, and `mcp_request_headers` from `litestar_mcp.mcp.client` (`httpx2`-backed) to stamp `_meta` and transport headers automatically:

```python
from litestar_mcp.mcp.client import (
    MCPStreamableHTTPClient,
    mcp_request_headers,
    prepare_mcp_request,
)

raw_message = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "lookup_product", "arguments": {"sku": "sku-1"}},
}
prepared = prepare_mcp_request(raw_message)
headers = mcp_request_headers(prepared)


async def call_remote_mcp() -> object:
    """Invoke a remote stateless MCP endpoint over Streamable HTTP."""
    async with MCPStreamableHTTPClient("https://api.example.com/mcp") as client:
        await client.list_tools()
        return await client.call_tool("lookup_product", {"sku": "sku-1"})
```

## Subscriptions And Stream Bounds

`subscriptions/listen` provides filtered streams over the `POST /mcp` transport in `2026-07-28` mode (while `GET /mcp` SSE remains available for `2025-*` sessions when `enable_get_sse=True`), gated by optional `MCPConfig(subscription_authorizer=...)`. When a request supplies `params._meta.progressToken`, the response also upgrades to an SSE stream emitting `notifications/progress` (and RFC 5424 `notifications/message` via `MCPRequestContext.log(level, data, logger=None)` when `logging=True`) before the final JSON-RPC response.

| Option | Default | Purpose |
| --- | --- | --- |
| `subscription_max_streams` | `10000` | Max concurrent SSE streams |
| `subscription_keepalive_seconds` | `15.0` | Seconds between keepalive pings |
| `stream_queue_capacity` | `256` | Max queued progress notifications per request stream |
| `stream_cleanup_timeout` | `5.0` | Seconds allowed for cooperative stream producer cleanup |
| `subscription_channels` | `None` | Channels backend backing fan-out |

Supply `subscription_channels` with a Channels backend when subscription delivery must span processes; the default keeps fan-out in-process.

## Tasks Extension

The `io.modelcontextprotocol/tasks` extension adds task records backed by a Litestar `Store` (default `MCPConfig.tasks=None`; auto-enables `QueueTaskExecutor` when `QueuePlugin` is registered unless `tasks=False`, or configure explicitly via `MCPTaskConfig(store=..., executor=...)`).

```python
from litestar_mcp import LitestarMCP, MCPConfig, MCPTaskConfig

plugin = LitestarMCP(MCPConfig(tasks=MCPTaskConfig()))
```

Pass `MCPTaskConfig` to configure the backing `Store` (defaults to in-memory) and the record TTLs. `tasks=True` enables the extension with defaults.

## Skills Extension (`MCPSkillsConfig`, `SkillSource`, `FilesystemSkillSource`, `Skill.build`)

The opt-in `io.modelcontextprotocol/skills` extension exposes static `<path>/<name>/SKILL.md` directories (`FilesystemSkillSource`) and/or async, request-aware `SkillSource` backends as a unified `SkillCatalog` (`litestar_mcp.mcp.skills`).

```python
from pathlib import Path

from litestar_mcp import (
    FilesystemSkillSource,
    LitestarMCP,
    MCPConfig,
    MCPSkillsConfig,
    Skill,
    SkillFile,
)

filesystem_source = FilesystemSkillSource([Path("skills")])
dynamic_skill = Skill.build(
    "tenant-guide",
    "Dynamic tenant guide.",
    "# Tenant Guide\nFollow tenant-specific steps.\n",
    files={"references/checklist.md": SkillFile.from_content("tenant-guide", "references/checklist.md", "Check 1")},
)

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

- `MCPSkillsConfig` accepts `paths: Sequence[Path] = ()`, `sources: Sequence[SkillSource] = ()` (requiring at least one entry in `paths` or `sources`), `expose_as_prompts: bool = False`, and `list_changed: bool = True`.
- `SkillCatalog.from_config` composes `paths` first (as a `FilesystemSkillSource`) followed by `sources`; earlier sources win on duplicate skill names with a warning.
- `SkillCatalog` methods (`list_skills(request)`, `get_skill(request, name)`, `get(request, uri)`, `get_file(request, uri)`, `list_directory(request, uri)`, `resource_entries(request)`, and `read_file(request, match)`) are async and accept the active `Request`.
- When configured, `server/discover` advertises `capabilities.extensions["io.modelcontextprotocol/skills"]` (`directoryRead` and `listChanged`), registers `skills/list`, `skills/get`, `resources/directory/read` (when `directory_read=True`), and `skill://` support in `resources/read` and `resources/list` with SHA-256 digest verification (`SkillIntegrityError`), and optionally exposes skills as read-only MCP prompts when `expose_as_prompts=True`.

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
6. Use `MCPStreamableHTTPClient` (or `prepare_mcp_request(..., log_level=...)` + `mcp_request_headers(..., session_id=..., tool_schema=...)`) for Streamable HTTP requests, `LitestarA2A` / `agent_to_a2a` (`litestar-mcp[a2a]`) for `/.well-known/agent-card.json` and `/a2a`, and `litestar-security` (`ProtectedResourceConfig`) for `/.well-known/oauth-protected-resource` (plus `MCPConfig(auth=...)` or `route_opt`).

The stdio bridge handles MCP transport headers transparently and forwards independent request-scoped POST streams concurrently.

## Cross-References

- **[Litestar Channels & SSE](../../litestar/references/channels-and-sse.md)** — Channels backends for `subscription_channels` and `QueuedAgentChatController`.
- **[advanced-patterns.md](advanced-patterns.md)** — `Agent`, `AgentGroup`, `AgentRuntime`, `DynamicWorkflow`, and `QueuedAgentChatController` orchestration patterns.
- **[litestar-security](../../litestar-security/SKILL.md)** — `SecurityPlugin`, `ProtectedResourceConfig`, and `AUTH_POLICY_OPT_KEY` / `required(...)` route policies.
- **[Litestar Auth & Guards](../../litestar/references/auth-and-guards.md)** — guards applied to the MCP router.

## Official References

- <https://github.com/cofin/litestar-mcp>
- <https://pypi.org/project/litestar-mcp/>
- <https://cofin.github.io/litestar-mcp/>
