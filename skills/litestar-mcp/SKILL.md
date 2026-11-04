---
name: litestar-mcp
description: "Use when working with litestar_mcp, LitestarMCP, MCP, MCPConfig, MCPSkillsConfig, LitestarA2A, A2AConfig, @mcp.tool/resource/prompt, mcp_tool=, or stdio MCP. Not for non-Litestar MCP SDK servers."
---

# litestar-mcp

`litestar-mcp` exposes explicitly marked Litestar route handlers as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, resources, and prompts over JSON-RPC 2.0, and provides an optional [A2A 1.0](https://a2a-protocol.org/) adapter (`LitestarA2A`) backed by the official `a2a-sdk`.

`litestar-mcp` follows the stateless MCP specification (protocol `2026-07-28` with backward compatibility for `2025-06-18` and `2025-03-26`). The MCP transport is POST-only and request-scoped: each request supplies protocol version, method, and capabilities. Call `server/discover` for capabilities. Features include the `io.modelcontextprotocol/skills` catalog (`MCPSkillsConfig`), durable task execution over `litestar-queues` (`QueueTaskExecutor`, `DurableWorkflowEngine`), the stdio-to-HTTP bridge (`httpx2`), standards-backed `LitestarA2A` (`litestar-mcp[a2a]`), and route authentication integration with `litestar-security`. See [Stateless Protocol](references/stateless-protocol.md).

Mark routes by passing `mcp_tool="name"`, `mcp_resource="name"`, or `mcp_prompt="name"` directly to the Litestar route decorator — Litestar funnels unknown kwargs into `handler.opt`, so no `opt={...}` wrapper is needed. Use the decorator forms for structured metadata: `@mcp_tool` adds schemas, annotations, scopes, and task policy; `@mcp_prompt` adds title, arguments, and icons. Route description keys are `mcp_description`, `mcp_resource_description`, and `mcp_prompt_description`; `MCPOptKeys` can rename every key the plugin reads. There is no `opt={"mcp_tool_name": ...}` form or `mcp_exclude` key. To hide a route, leave it unmarked.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O. Pure standalone `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` functions may be sync; keep blocking I/O out of the event loop.

## Quick Reference

### Install

```bash
pip install litestar-mcp
```

The stdio-to-Streamable-HTTP bridge is included in the core package (`httpx2`). Install the `a2a` extra when mounting the optional A2A 1.0 SDK adapter (`LitestarA2A`):

```bash
pip install "litestar-mcp[a2a]"
```

### Basic Setup

```python
from litestar import Litestar, get, post
from litestar_mcp import LitestarMCP, MCPConfig


@get("/users", mcp_tool="list_users")
async def list_users() -> list[dict[str, str | int]]:
    """List all registered users."""
    return [{"id": 1, "name": "Alice"}]


@post("/analyze", mcp_tool="analyze_data")
async def analyze_data(data: dict[str, str]) -> dict[str, int]:
    """Analyze provided key-value dataset."""
    return {"count": len(data)}


@get("/config", mcp_resource="app_config")
async def get_app_config() -> dict[str, bool]:
    """Read the active application configuration."""
    return {"debug": False}


app = Litestar(
    route_handlers=[list_users, analyze_data, get_app_config],
    plugins=[LitestarMCP(MCPConfig(name="My API"))],
)
```

The transport and discovery surface across the ecosystem is:

| Endpoint | Owner | Purpose |
| --- | --- | --- |
| `POST /mcp` | `LitestarMCP` | The only MCP transport route. JSON-RPC endpoint for `server/discover`, `tools/*`, `resources/*`, `resources/templates/list`, `resources/directory/read`, `prompts/*`, `skills/*`, `completion/complete`, `subscriptions/listen`, and optional `tasks/*` methods |
| `POST /a2a` | `LitestarA2A` (`litestar-mcp[a2a]`) | Optional A2A 1.0 JSON-RPC and SSE streaming endpoint |
| `GET /.well-known/agent-card.json` | `LitestarA2A` (`litestar-mcp[a2a]`) | Standard A2A 1.0 agent card discovery route (with `ETag` and `Cache-Control`) |
| `GET /.well-known/oauth-protected-resource` | `SecurityPlugin` (`litestar-security`) | RFC 9728 OAuth 2.1 protected-resource metadata via `SecurityConfig(protected_resource=ProtectedResourceConfig(...))` |

### MCPConfig

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `base_path` | `str` | `"/mcp"` | URL prefix for the MCP transport endpoint |
| `include_in_schema` | `bool` | `False` | Include the `/mcp` router in OpenAPI |
| `name` | `str \| None` | `None` | Server name; defaults to OpenAPI title |
| `instructions` | `str \| None` | `None` | Server instructions advertised to MCP clients |
| `guards` | `list[Any] \| None` | `None` | Litestar guards applied to the MCP router |
| `route_opt` | `dict[str, Any] \| None` | `None` | Route `opt` mapping merged into the mounted MCP router (e.g., `{AUTH_POLICY_OPT_KEY: required("api-key", "oidc")}` with `litestar-security`) |
| `allowed_origins` | `list[str] \| None` | `None` | Restrict accepted `Origin` headers |
| `include_operations` | `list[str] \| None` | `None` | Only expose matching operation names |
| `exclude_operations` | `list[str] \| None` | `None` | Exclude matching operation names |
| `include_tags` | `list[str] \| None` | `None` | Only expose routes with matching OpenAPI tags |
| `exclude_tags` | `list[str] \| None` | `None` | Exclude routes with matching OpenAPI tags |
| `tasks` | `bool \| MCPTaskConfig` | `False` | Enable MCP task support (`io.modelcontextprotocol/tasks`). Pass `MCPTaskConfig` to configure the backing `Store` and record TTLs |
| `skills` | `MCPSkillsConfig \| None` | `None` | Enable the `io.modelcontextprotocol/skills` catalog serving `<path>/<name>/SKILL.md` directories |
| `opt_keys` | `MCPOptKeys` | `MCPOptKeys()` | Rename the `handler.opt` keys the plugin reads |
| `cache_ttl_ms` | `int` | `0` | Response cache lifetime in milliseconds; `0` disables caching |
| `cache_scope` | `Literal["private", "public"]` | `"private"` | Whether cached responses may be shared between callers |
| `subscription_max_streams` | `int` | `10000` | Max concurrent SSE streams |
| `subscription_keepalive_seconds` | `float` | `15.0` | Seconds between SSE keepalive pings |
| `stream_queue_capacity` | `int` | `256` | Maximum queued progress notifications per request stream |
| `stream_cleanup_timeout` | `float` | `5.0` | Positive finite seconds allowed for cooperative stream producer cleanup |
| `subscription_channels` | `Any \| None` | `None` | Channels backend backing `subscriptions/listen` fan-out |
| `list_page_size` | `int` | `100` | Page size for `tools/list`, `resources/list`, `resources/templates/list`, `skills/list`, `prompts/list`, and `resources/directory/read` |
| `before_tool_call` | `BeforeToolCallHook \| None` | `None` | Observe each `tools/call` before dispatch |
| `after_tool_call` | `AfterToolCallHook \| None` | `None` | Observe each `tools/call` result, exception, and duration |
| `max_blob_bytes` | `int \| None` | `25 * 1024 * 1024` | Maximum raw byte length for base64-embedded blobs; `None` disables the cap |

> Filters (`include_tags` / `exclude_tags` / `include_operations` / `exclude_operations`) gate both list responses and direct invocation. A filtered tool/resource/template behaves like an unknown name or URI in `tools/call` / `resources/read`; still use `guards` or `route_opt` auth policies for real access control.

### Route Marking

```python
from litestar import get, post


@get("/products", mcp_resource="product_list")
async def list_products() -> list[dict[str, str]]:
    """List all available products in the catalog."""
    return [{"id": "sku-1", "name": "Widget"}]


@post("/cart/items", mcp_tool="add_to_cart")
async def add_to_cart(data: dict[str, int]) -> dict[str, str]:
    """Add a product item to the shopping cart."""
    return {"status": "added"}


@get(
    "/products/{product_id:int}",
    mcp_resource="product",
    mcp_resource_template="shop://products/{product_id}",
)
async def get_product(product_id: int) -> dict[str, int | str]:
    """Fetch details for a single product by identifier."""
    return {"id": product_id, "name": "Widget"}


@get("/products/{product_id:int}/blurb", mcp_prompt="product_blurb")
async def product_blurb(product_id: int) -> str:
    """Write a short marketing blurb for a product."""
    return f"Product {product_id} is top tier."
```

`mcp_resource_template` takes effect alongside `mcp_resource` — the resource supplies the name the template binds to. A handler can expose more than one MCP role (a tool and a resource) at once; the description-override keys (`mcp_description` vs `mcp_resource_description`) are kind-specific so each surface can carry its own prose.

Register prompts not bound to a route with the `@mcp_prompt` decorator plus `LitestarMCP(prompts=[...])`:

```python
from litestar import Litestar
from litestar_mcp import LitestarMCP, mcp_prompt


@mcp_prompt("summarize", description="Summarize a document for the user.")
def summarize(text: str) -> str:
    """Produce a summarization prompt for the supplied text."""
    return f"Summarize the following:\n\n{text}"


app = Litestar(plugins=[LitestarMCP(prompts=[summarize])])
```

Use structured metadata when the agent needs sharper tool selection:

```python
from litestar import post
from litestar_mcp import mcp_tool


@post("/reports")
@mcp_tool(
    name="generate_report",
    description="Generate a report for an existing account.",
    agent_instructions="Ensure account ID exists before calling.",
    when_to_use="Use after the user has confirmed the account and date range.",
    returns="A report id and queued status.",
    scopes=["reports:write"],
    task_support="optional",
)
async def generate_report(data: dict[str, str]) -> dict[str, str]:
    """Create a new reporting job."""
    return {"report_id": "rep-123", "status": "queued"}
```

### Accessing Request Context And Progress

Retrieve active MCP scope and metadata inside tool, resource, or prompt handlers with `get_mcp_request_context()`. When the client supplies a progress token (`params._meta.progressToken`), call `await ctx.report_progress(...)` to stream `notifications/progress` SSE events over the active request stream:

```python
from litestar import post
from litestar_mcp import MCPRequestContext, get_mcp_request_context


@post("/agent-session", mcp_tool="record_session")
async def record_session(note: str) -> dict[str, str]:
    """Record a note attached to the calling MCP client."""
    ctx: MCPRequestContext = get_mcp_request_context()
    if ctx.progress_token is not None:
        await ctx.report_progress(0.5, total=1.0, message="Recording session note")
    return {
        "client_id": ctx.client_id,
        "owner_id": ctx.owner_id or "anonymous",
        "note": note,
    }
```

### Standalone MCP App, Skills Catalog, A2A 1.0, Binary Results, and Auth

- **Standalone `MCP(...)` & Stdio**: Use `mcp = MCP("inventory-mcp")` with `@mcp.tool(...)`, `@mcp.resource(uri=..., name=...)`, and `@mcp.prompt(...)` when the app exists solely as an MCP server (`app = mcp.app`). Run over HTTP/SSE (`mcp.run(transport="sse", port=8000)`) or line-delimited stdio (`mcp.run(transport="stdio", stdio_context=MCPStdioContext(...))`). Proxy a local stdio client to a remote Streamable HTTP endpoint via `litestar mcp bridge --endpoint https://api.example.com/mcp --bearer-env MCP_ACCESS_TOKEN` or serve in-process via `litestar --app app.main:app mcp stdio`.
- **Skills Over MCP (`MCPSkillsConfig`)**: Pass `skills=MCPSkillsConfig(paths=[Path("skills")], directory_read=True)` to `MCPConfig` to expose `<path>/<name>/SKILL.md` directories over the `io.modelcontextprotocol/skills` extension (`skills/list`, `skills/get`, `resources/directory/read`, and `resources/read` with SHA-256 integrity checks).
- **A2A 1.0 Adapter (`LitestarA2A`)**: Install `litestar-mcp[a2a]` and mount `LitestarA2A(agent_card=card, request_handler=handler, config=A2AConfig(path="/a2a", agent_card_path="/.well-known/agent-card.json"))` to expose `POST /a2a` (JSON-RPC 2.0 + SSE streaming) and `GET /.well-known/agent-card.json`.
- **Binary Resources & Multi-Round-Trip Inputs**: Return `MCPResourceLink(name=..., uri=..., mime_type=..., size=...)` from tools to link binary resources fetched via `resources/read` (or `MCPBlobResource` for inline base64 blobs bounded by `MCPConfig.max_blob_bytes`). Return `MCPInputRequiredResult(input_requests={...}, request_state=...)` when a tool requires interactive client confirmation (`ctx.input_responses`).
- **Authentication (`litestar-security`)**: Attach auth policies via `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required("oidc")})` and publish RFC 9728 metadata (`GET /.well-known/oauth-protected-resource`) via `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`.

See [Standalone MCP, Skills, A2A, Binary Resources, and Auth](references/advanced-patterns.md) for complete code patterns.

### CLI Commands

```bash
litestar mcp list-tools
litestar mcp list-resources
litestar mcp run list_users
litestar mcp stdio
litestar mcp bridge --endpoint http://127.0.0.1:8000/mcp
```

### Hiding Routes & JSON-RPC Calls

Discovery is opt-in: unmarked routes never appear in MCP (`opt={"mcp_exclude": True}` is ignored). Use `MCPConfig` filters (`include_tags`, `exclude_tags`, `include_operations`, `exclude_operations`) to gate both list responses and direct invocation, paired with `guards` or `route_opt` auth policies for access control.

Every HTTP `POST /mcp` request requires `params._meta` (`io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities`) plus matching `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method`, and (for named calls) `Mcp-Name` headers:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "add_to_cart",
    "arguments": { "product_id": 42, "quantity": 3 },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

### Pagination, Signatures, Callbacks, Dishka, and OpenAPI

- **Pagination**: `tools/list`, `resources/list`, `resources/templates/list`, `skills/list`, `prompts/list`, and `resources/directory/read` use opaque cursor pagination (`params.cursor` -> `nextCursor`, page size `MCPConfig(list_page_size=100)`).
- **Signatures & Wire Aliases**: Tool arguments validate against `handler.parsed_fn_signature`. Query parameter wire names (`QueryParameter(name=...)` / `Parameter(query=...)`, including `advanced-alchemy` and `sqlspec` filter providers) are advertised in `inputSchema` and dispatched under their wire alias.
- **Tool-Call Callbacks**: `MCPConfig.before_tool_call` and `MCPConfig.after_tool_call` observe `tools/call` around dispatch (exceptions are logged and swallowed).
- **Dishka Integration**: When `setup_dishka()` is attached, provider parameters resolvable from `app.state.dishka_container` are injected as DI services and excluded from MCP tool schemas.
- **Built-in OpenAPI Resource**: `LitestarMCP` always exposes `litestar://openapi` (`application/json`) in `resources/list`. `include_in_schema=False` (default on `MCPConfig` and `A2AConfig`) hides `/mcp`, `/a2a`, and `/.well-known/agent-card.json` from generated OpenAPI while keeping marked application routes visible.

<workflow>

## Workflow

1. **Install**: Run `pip install litestar-mcp` (or `pip install "litestar-mcp[a2a]"` when mounting `LitestarA2A`).
2. **Decide What to Expose**: Mark only intended AI-callable routes with `mcp_tool=`, `mcp_resource=` (plus `mcp_resource_template=` for URI templates), or `mcp_prompt=`. Unmarked routes are never exposed.
3. **Add the Plugin**: Wire `LitestarMCP(MCPConfig(name=...))` into `Litestar(plugins=[...])`, or use standalone `MCP(...)` (`app = mcp.app`). Add `skills=MCPSkillsConfig(paths=[Path("skills")])` for `io.modelcontextprotocol/skills` and `LitestarA2A(agent_card, request_handler, config=A2AConfig(...))` for A2A 1.0.
4. **Add Auth**: Attach `litestar-security` route policies via `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` and publish RFC 9728 metadata via `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`, or configure `guards=[...]`.
5. **Verify**: `POST /mcp` `server/discover`, `tools/list`, `resources/list`, `tools/call`, and `resources/read` (plus `skills/*` when enabled). Confirm only marked routes appear and verify auth and blob size limits.

</workflow>

<guardrails>

## Guardrails

- **Mark routes explicitly** - unmarked routes should not appear in MCP clients.
- **Default to allowlists** - `include_tags` / `include_operations` keep the tool set small and gate direct invocation; pair them with `guards` or `route_opt` auth policies for authorization.
- **Never expose admin or destructive routes by default** - require a human-confirmation workflow or multi-round-trip verification (`MCPInputRequiredResult`) before any irreversible operation.
- **Prefer resources for read-only reference data** - agents may read resources speculatively.
- **Keep DTOs precise** - loose `dict[str, Any]` request schemas produce weak tool contracts.
- **Delegate auth and RFC 9728 metadata to `litestar-security`** - use `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` and `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`.
- **Set `allowed_origins` for browser-accessible MCP clients** - leave it `None` only for trusted server-to-server deployments.
- **Prefer `MCPResourceLink` over inline blobs** - linked resources avoid base64 expansion and let the application enforce authorization when the client reads the resource.
- **Keep `max_blob_bytes` bounded** - base64 embedding increases memory and wire size; disable the cap only behind a stricter application-owned limit.
- **Resolve stdio credentials out of band** - inject the verified principal with `MCPStdioContext`; JSON-RPC messages are not an authentication channel.
- **Treat `MCP`, `LitestarMCP`, and `LitestarA2A` as public entry points** - avoid private router/service imports.
- **Keep observability callbacks side-effect safe** - `before_tool_call` / `after_tool_call` failures are swallowed, so callbacks must not enforce authorization or business invariants.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering an MCP integration, verify:

- [ ] Existing Litestar apps include `LitestarMCP` in `app.plugins`; standalone apps expose `app = mcp.app`
- [ ] Exposed routes/functions use `mcp_tool=`, `mcp_resource=`, `mcp_prompt=`, `@mcp.tool`, `@mcp.resource`, or `@mcp.prompt`
- [ ] Admin / internal routes are left unmarked, or kept outside `include_*` / inside `exclude_*` — with `guards` or `route_opt` auth policies enforcing access
- [ ] Auth is configured for the deployment boundary (`MCPConfig(route_opt=...)`, `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`, `guards=[...]`, or custom middleware)
- [ ] `POST /mcp` `tools/list` returns only intended tools
- [ ] `POST /mcp` `resources/list` includes only intended resources plus `litestar://openapi` (and indexed skill files when `MCPSkillsConfig` is enabled)
- [ ] When `MCPSkillsConfig` is enabled, `skills/list`, `skills/get`, `resources/directory/read`, and `resources/read` verify `skill://` URIs and SHA-256 digests
- [ ] When `LitestarA2A` is enabled, `GET /.well-known/agent-card.json` and `POST /a2a` match the `AgentCard` JSON-RPC 1.0 interface URL
- [ ] Filtered tools/resources/templates fail direct invocation as unknown
- [ ] Provider-declared user inputs appear in tool `inputSchema`; Dishka-resolved service parameters do not
- [ ] `before_tool_call` / `after_tool_call` callbacks are covered when configured, including failure paths
- [ ] Standalone `MCP` SSE or stdio transport is smoke-tested for the chosen deployment mode
- [ ] Direct stdio handlers and guards receive the intended `MCPStdioContext`; task ownership resolves to the intended principal
- [ ] Stdio bridge stdout contains JSON-RPC only; static/dynamic auth, concurrent request-scoped streams, and frame limits match the deployment
- [ ] Binary resource listings advertise the correct MIME type; reads return `text` or base64 `blob` as intended
- [ ] `max_blob_bytes` accepts the largest intended payload and rejects oversized tool results and resource reads
- [ ] OpenAPI contains ordinary application routes and hides plugin-owned paths (`/mcp`, `/a2a`, `/.well-known/agent-card.json`) by default unless `include_in_schema=True` is set
- [ ] Exposed handlers performing I/O are `async def`; sync standalone functions are pure/non-blocking and return JSON-serializable types
- [ ] Tool argument DTOs are specific enough for generated schemas

</validation>

<example>

## Example

**Task:** Expose product listing as a resource and add-to-cart as a tool. Hide internal metrics.

```python
from litestar import Litestar, get, post
from litestar_mcp import LitestarMCP, MCPConfig


@get("/products", mcp_resource="product_list", tags=["public"])
async def list_products() -> list[dict[str, str]]:
    """List public catalog products."""
    return [{"id": "prod-1", "name": "Widget"}]


@post("/cart/items", mcp_tool="add_to_cart", tags=["public"])
async def add_to_cart(data: dict[str, int]) -> dict[str, str]:
    """Add product to user shopping cart."""
    return {"status": "success"}


@get("/internal/metrics")
async def metrics() -> dict[str, int]:
    """Internal metrics endpoint."""
    return {"cpu_percent": 12}


app = Litestar(
    route_handlers=[list_products, add_to_cart, metrics],
    plugins=[
        LitestarMCP(
            MCPConfig(
                name="E-Commerce API",
                include_tags=["public"],
            )
        )
    ],
)
```

</example>

## References Index

- **[Standalone MCP, Skills, A2A, Binary Resources, and Auth](references/advanced-patterns.md)** — standalone `MCP(...)`, `MCPStdioContext`, stdio-to-HTTP bridge, `MCPSkillsConfig`, `LitestarA2A` / `A2AConfig`, `MCPResourceLink` / `MCPBlobResource`, `MCPInputRequiredResult`, and `litestar-security` auth wiring.
- **[Stateless Protocol](references/stateless-protocol.md)** — the POST-only transport, `server/discover`, `subscriptions/listen`, progress reporting, the tasks and skills extensions, `LitestarA2A`, MRTR results, response caching, and client migration.

## Cross-References

- Use this skill for route marking, transport and stdio behavior, `MCPSkillsConfig`, `LitestarA2A`, binary content, and verification requests.
- Use [litestar-security](../litestar-security/SKILL.md) for `SecurityPlugin`, `SecurityConfig`, `ProtectedResourceConfig`, and `AUTH_POLICY_OPT_KEY` / `required(...)` route policies.
- Use [Litestar auth & guards](../litestar/references/auth-and-guards.md) when auth logic lives in normal Litestar guards or middleware.

## Official References

- <https://github.com/cofin/litestar-mcp>
- <https://pypi.org/project/litestar-mcp/>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>
- <https://a2a-protocol.org/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
