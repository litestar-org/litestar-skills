---
name: litestar-mcp
description: "Auto-activate for litestar_mcp, LitestarMCP, MCP, MCPConfig, MCPSkillsConfig, SkillController, LitestarA2A, A2AConfig, @mcp.tool/resource/prompt, mcp_tool=, or stdio MCP. Not for non-Litestar MCP SDK servers."
---

# litestar-mcp

`litestar-mcp` exposes explicitly marked Litestar route handlers and class-based `SkillController` / `PromptController` definitions as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, resources, prompts, and skills over JSON-RPC 2.0, provides a multi-agent runtime (`litestar_mcp.agent`) with distributed queue execution (`litestar_mcp.queues`), and includes an optional [A2A 1.0](https://a2a-protocol.org/) adapter (`LitestarA2A`) backed by `a2a-sdk`.

Version `0.16.0` follows the stateless MCP specification (protocol `2026-07-28`). The MCP transport is **POST-only and request-scoped**: the legacy `initialize` handshake, sessions and `Mcp-Session-Id`, `ping`, `GET` and `DELETE` transport handlers, replay, and `/.well-known/mcp-server.json` are removed. Each request supplies protocol version, method, and client capabilities; named calls also supply matching name or URI metadata. Call `server/discover` for capabilities. Version `0.16.0` also ships:

- **Static and dynamic `io.modelcontextprotocol/skills` catalogs** (`MCPSkillsConfig(paths=..., sources=...)`, `FilesystemSkillSource`, async request-aware `SkillSource` protocol, and in-memory `Skill.build` / `Skill.from_content` / `SkillFile.from_content`).
- **Class-based `SkillController` and `PromptController`** (`@tool`, `@prompt`, `PromptMessage`) with recursive discovery across nested `Router` / `DishkaRouter` / `litestar-autowire` trees and automatic `RESERVED_KWARGS` parameter aliasing.
- **Universal dependency injection** across HTTP routes, MCP `tools/call` / `prompts/get`, and standalone `AgentRuntime` (`Tool.execute`): Litestar `Provide` / `Dependency`, Dishka `FromDishka[T]`, generic `Annotated[T, Inject()]` / `Depends(fn)` markers, and `ToolContext(container=..., dependency_resolver=...)`.
- **Streamable HTTP client and stdio bridge** (`MCPStreamableHTTPClient`, `prepare_mcp_request`, `mcp_request_headers`, and `run_stdio_streamable_http_bridge`) powered by `httpx2` in core.
- **Agent runtime, workflows, and protocol bridges** (`litestar_mcp.agent`: `Agent`, `AgentGroup`, `AgentRuntime`, `GoogleGenAIClient` defaulting to `gemini-3.8-flash`, `AgentChatController`, `DynamicWorkflow`, `WorkflowEngine`, `agent_to_mcp`, `agent_to_a2a`, `mcp_to_tools`, `discover_mcp_tools`), plus optional distributed queue execution (`litestar_mcp.queues`: `QueuedAgentChatController`, `QueuedTurnManager`, `AgentRegistry`) and OpenTelemetry GenAI spans (`TelemetryConfig`, `SpanManager`).
- **Standards-backed A2A 1.0 and OAuth 2.1 discovery**: `LitestarA2A` / `A2AConfig` (`litestar-mcp[a2a]`, `a2a-sdk>=1.1.4`) and `litestar-security` route authentication policies plus RFC 9728 `/.well-known/oauth-protected-resource` discovery. See [Stateless Protocol](references/stateless-protocol.md).

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

The stdio-to-Streamable-HTTP bridge and `MCPStreamableHTTPClient` are included in the core package (`httpx2`). Install optional extras for A2A, Gemini models, distributed queues, or OpenTelemetry spans:

```bash
pip install "litestar-mcp[a2a]"
pip install "litestar-mcp[google-genai]"
pip install "litestar-mcp[queues]"
pip install "litestar-mcp[opentelemetry]"
```

| Extra | Dependencies | Unlocks |
| --- | --- | --- |
| *(core)* | `litestar>=2.15.0`, `httpx2>=0.1.3`, `msgspec>=0.18.0`, `anyio>=4.0` | `LitestarMCP`, `MCP`, `SkillController`, `PromptController`, `MCPSkillsConfig`, `MCPStreamableHTTPClient`, stdio bridge, `litestar_mcp.agent` core |
| `a2a` | `a2a-sdk>=1.1.4`, `protobuf>=5.29.5` | `LitestarA2A`, `A2AConfig`, `agent_to_a2a` |
| `google-genai` | `google-genai>=2.29.0` | `GoogleGenAIClient` (default model `gemini-3.8-flash`) |
| `queues` | `litestar-queues>=0.12.0` | `QueuedAgentChatController`, `QueuedTurnManager`, `QueuedTurn`, `AgentRegistry` |
| `opentelemetry` | `opentelemetry-api>=1.20.0` | `TelemetryConfig`, `SpanManager` (GenAI semantic convention spans) |

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
| `POST /agent/chat`, `POST /agent/turns`, `GET /agent/sessions/{session_id}` | `AgentChatController` (`litestar_mcp.agent`) | In-process SSE streaming chat, synchronous turn execution, and owner-scoped session history |
| `POST /agent/turns`, `GET /agent/turns/{turn_id}/stream` | `QueuedAgentChatController` (`litestar-mcp[queues]`) | Distributed `202 Accepted` turn enqueueing and `ChannelsPlugin`-backed SSE replay streaming |

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
| `skills` | `MCPSkillsConfig \| None` | `None` | Enable the `io.modelcontextprotocol/skills` catalog from filesystem `paths` and/or async `sources` (`SkillSource`) |
| `prompt_controllers` | `Sequence[type[Any]]` | `()` | `PromptController` subclasses mounted into the MCP router |
| `skill_controllers` | `Sequence[type[Any]]` | `()` | `SkillController` subclasses mounted into the MCP router |
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

### Class-Based `SkillController` And `PromptController`

Use `PromptController` to group `@prompt` methods with shared `prefix`, `instructions`, `guards`, and `dependencies`. Use `SkillController(PromptController)` to unify `@tool` methods, `@prompt` methods, `instructions`, `tags`, `examples`, `guards`, and `dependencies` into a single skill class usable across MCP (`LitestarMCP`), `Agent(skills=[...])`, and A2A (`agent_to_a2a` projects `to_agent_skill()` onto `AgentCard.skills`).

```python
from litestar import Litestar, Router
from litestar.di import Provide
from litestar_mcp import (
    LitestarMCP,
    MCPConfig,
    PromptMessage,
    SkillController,
    prompt,
    tool,
)


async def provide_tenant_prefix() -> str:
    """Provide the active tenant prefix."""
    return "acme"


class OrdersSkillController(SkillController):
    """Order search and summarization skill."""

    name = "orders"
    description = "Search orders and draft customer order summaries."
    instructions = "Verify order IDs before mutating state."
    tags = ("commerce", "orders")
    examples = ("Search orders matching 'widget'",)
    dependencies = {"tenant_prefix": Provide(provide_tenant_prefix)}

    @tool(description="Search orders by query string.")
    async def search_orders(self, query: str, tenant_prefix: str) -> dict[str, str]:
        """Search orders within the current tenant."""
        return {"matched": f"{tenant_prefix}:{query}"}

    @prompt(description="Draft a customer order summary.")
    async def summarize_order(self, order_id: str) -> list[PromptMessage]:
        """Build prompt messages for summarizing an order."""
        return [
            PromptMessage.user(f"Summarize order {order_id}"),
            PromptMessage.assistant(f"Order {order_id} summary ready."),
        ]


api_router = Router(path="/v1", route_handlers=[OrdersSkillController])

app = Litestar(
    route_handlers=[api_router],
    plugins=[LitestarMCP(MCPConfig(name="Orders MCP"))],
)
```

- **Recursive router discovery**: `LitestarMCP` recursively discovers and deduplicates `SkillController` and `PromptController` subclasses registered on `MCPConfig(skill_controllers=[...], prompt_controllers=[...])`, top-level `route_handlers`, or nested `Router` / `DishkaRouter` trees (including controllers auto-mounted by `litestar-autowire`).
- **Prompt namespacing**: `SkillController.qualify_prompt_name(name)` namespaces prompts under `self.prefix or self.name` (e.g., `"orders/summarize_order"`).
- **`RESERVED_KWARGS` parameter aliasing**: Tool parameters whose names collide with Litestar's reserved handler kwargs (`query`, `headers`, `cookies`, `state`, `socket`, `scope`, `receive`, `send`, `body`) are automatically aliased to `_mcp_param_<name>` with `Parameter(query="<name>")` on the internal Litestar endpoint while preserving `<name>` in the MCP `inputSchema` and `tool.execute(...)`.

### Universal Dependency Injection (`Provide`, `FromDishka`, `Inject`, `ToolContext`)

`@tool`, `SkillController`, `PromptController`, and `LitestarMCP` support four dependency injection styles across HTTP dispatch, MCP `tools/call` / `prompts/get`, and standalone `AgentRuntime` execution (`await tool.execute(args, context=ctx)`):

1. **Litestar `Provide` / `Dependency`**: Declare `dependencies={"svc": Provide(provide_svc)}` on `@tool(dependencies=...)`, the enclosing `SkillController` / `Controller`, or `LitestarMCP.register_tool`. User-facing filter/pagination inputs produced by `Provide` stay in `inputSchema`; service dependencies are excluded from `inputSchema` and injected at call time.
2. **Dishka `FromDishka[T]`**: Annotate parameters with `FromDishka[T]`. Controller endpoints are automatically wrapped with `dishka.integrations.litestar.inject` when Dishka is installed, and `Tool.execute` resolves `FromDishka[T]` from `request.state.dishka_container`, `app.state.dishka_container`, or `ToolContext(dishka_container=...)` (opening a request scope automatically when given an `APP`-scoped container).
3. **Third-party DI markers (`Inject()` / `Depends(fn)`)**: Annotate parameters with `Annotated[T, Inject()]` (Wireup, aioinject, dependency-injector, svcs, that-depends, fast-depends, lagom, punq, or any marker setting `__inject_marker__ = True`) or `Annotated[T, Depends(fn)]`. Containers are resolved from `ToolContext(container=...)` or `request.state` / `app.state` (`wireup_container`, `svcs_registry`, `di_container`, `container`).
4. **Custom `ToolContext.dependency_resolver`**: Pass `ToolContext(dependency_resolver=lambda name, type_hint, ctx: ...)` when executing tools outside an HTTP request.

```python
from typing import Annotated

from dishka.integrations.litestar import FromDishka
from litestar_mcp import Tool, tool
from litestar_mcp.core.context import ToolContext


class InventoryRepo:
    """Repository for inventory lookups."""

    async def stock_for(self, sku: str) -> int:
        """Return current stock count for SKU."""
        _ = sku
        return 42


@tool(description="Check stock level for a SKU.")
async def check_stock(sku: str, repo: FromDishka[InventoryRepo]) -> dict[str, int | str]:
    """Check stock using Dishka-injected repository."""
    return {"sku": sku, "stock": await repo.stock_for(sku)}


class CustomMarker:
    """Custom DI marker recognized by extract_di_parameter."""

    __inject_marker__ = True


async def _lookup_with_marker(
    sku: str,
    repo: Annotated[InventoryRepo, CustomMarker()],
) -> dict[str, int | str]:
    return {"sku": sku, "stock": await repo.stock_for(sku)}


lookup_tool: Tool = tool(name="lookup_stock", description="Lookup stock.")(_lookup_with_marker)
ctx = ToolContext(dependency_resolver=lambda _name, hint, _ctx: InventoryRepo() if hint is InventoryRepo else None)
```

### Accessing Request Context And Progress

Retrieve active MCP scope and metadata inside tool, resource, or prompt handlers with `get_mcp_request_context()`. Or annotate a `@tool` parameter with `ToolContext` or `Request` / `ASGIConnection` (automatically excluded from `inputSchema`). When the client supplies a progress token (`params._meta.progressToken`), call `await ctx.report_progress(...)` to stream `notifications/progress` SSE events over the active request stream:

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

### Standalone MCP App

Use `MCP(...)` when the application is primarily an MCP server. Use `LitestarMCP(...)` when adding MCP to an existing Litestar app.

```python
from litestar_mcp import MCP

mcp = MCP("inventory-mcp", instructions="Expose inventory tools.")


@mcp.tool(name="lookup_product", description="Look up a product by SKU.")
def lookup_product(sku: str) -> dict[str, str]:
    """Return product status for the requested SKU."""
    return {"sku": sku, "status": "active"}


@mcp.resource(uri="inventory://status", name="inventory_status")
def inventory_status() -> dict[str, str]:
    """Return inventory service health."""
    return {"status": "healthy"}


@mcp.prompt(name="summarize_product")
def summarize_product(sku: str) -> str:
    """Create a prompt summarizing a product."""
    return f"Summarize product {sku}."


app = mcp.app


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

`mcp.app` lazily builds the underlying `Litestar` instance; access it after registering standalone decorators. `@mcp.tool`, `@mcp.resource`, and `@mcp.prompt` accept normal Litestar route-handler kwargs such as `dependencies`, `guards`, `tags`, DTO options, hooks, and `sync_to_thread`. The `name` kwarg names the MCP primitive; use `route_name` when the Litestar route handler itself needs a name.

`MCP(...)` also accepts `config=`, existing `plugins=`, existing `route_handlers=`, and standard `Litestar(...)` app kwargs.

`mcp.run(transport="streamable-http", port=8000)` (the default `transport`) starts the Streamable HTTP transport through the Litestar CLI, so expose `app = mcp.app` at module scope or set `LITESTAR_APP` for worker/reload discovery. `mcp.run(transport="stdio")` reads line-delimited JSON-RPC from stdin, writes responses to stdout, manually drives ASGI lifespan, and dispatches through the same JSON-RPC router with a synthetic request context.

#### Direct stdio identity

Stdio has no HTTP headers or authentication middleware. Resolve credentials in the host process and inject the resulting identity with `MCPStdioContext`:

```python
from litestar_mcp import MCP, MCPStdioContext

mcp = MCP("inventory-mcp")
stdio_context = MCPStdioContext(
    client_id="desktop-agent",
    owner_id="alice",
    auth={"sub": "alice", "role": "operator"},
    session={"tenant": "acme"},
    state={"deployment": "production"},
)
mcp.run(transport="stdio", stdio_context=stdio_context)
```

The synthetic Litestar request exposes `user`, `auth`, `session`, and `state` to handlers, guards, resources, and dependency providers. Mapping values are copied per dispatch, so handler mutations do not alter the supplied context or leak into later calls. Task ownership resolves in this order: explicit `owner_id`, `auth["sub"]`, `user.id`, `user.sub`, then `"stdio"`.

#### Stdio-to-Streamable-HTTP bridge and `MCPStreamableHTTPClient`

Use the bridge when a local MCP client speaks stdio but the real server is an already-running Streamable HTTP endpoint (`httpx2` is included in the core `litestar-mcp` package):

```bash
litestar mcp bridge \
  --endpoint https://api.example.com/mcp \
  --bearer-env MCP_ACCESS_TOKEN
```

Or serve a Litestar application's MCP endpoint in-process over stdio without opening a socket:

```bash
litestar --app app.main:app mcp stdio
```

For programmatic HTTP client calls, use `MCPStreamableHTTPClient` (along with `prepare_mcp_request` and `mcp_request_headers`) from `litestar_mcp.mcp.client`:

```python
from litestar_mcp.mcp.client import MCPStreamableHTTPClient


async def invoke_remote_tool() -> object:
    """List and invoke tools on a remote Streamable HTTP MCP server."""
    async with MCPStreamableHTTPClient(
        "https://api.example.com/mcp",
        headers={"Authorization": "Bearer token"},
    ) as client:
        await client.list_tools()
        return await client.call_tool("lookup_product", {"sku": "sku-1"})
```

The bridge forwards newline-delimited JSON-RPC. It forwards independent request-scoped POST streams in parallel, multiplexes subscription responses, maps cancellation to stream closure, and lazily maps annotated tool parameters to MCP headers. Stdout contains JSON-RPC only; transport diagnostics go to stderr.

Use `--header "Name: value"` for static headers. Use exactly one of `--bearer-env` or `--bearer-cmd` for a token resolved per request; the bridge retries once with a fresh token after `401`. Match identity-proxy schemes with `--header-name` and `--token-prefix`.

For programmatic embedding, import `run_stdio_streamable_http_bridge` from `litestar_mcp.mcp.bridge` (or `run_stdio` / `run_stdio_async` from `litestar_mcp.mcp.stdio`).

The default stdin frame limit is 16 MiB. Set `--max-message-size`; use `-1` to disable that limit. This is separate from `MCPConfig.max_blob_bytes`, which limits decoded binary payloads produced by the server.

### Skills Over MCP (`MCPSkillsConfig`, `SkillSource`, `FilesystemSkillSource`, `Skill.build`)

Configure `MCPConfig(skills=MCPSkillsConfig(...))` to serve static `<path>/<name>/SKILL.md` directories (`FilesystemSkillSource`) and/or dynamic, request-aware `SkillSource` backends over the `io.modelcontextprotocol/skills` extension:

```python
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from litestar import Litestar
from litestar_mcp import (
    LitestarMCP,
    MCPConfig,
    MCPSkillsConfig,
    Skill,
    SkillFile,
    SkillSource,
)


class TenantSkillSource:
    """Async request-aware SkillSource serving in-memory tenant playbooks."""

    def __init__(self, skills: Sequence[Skill]) -> None:
        self._skills = {skill.name: skill for skill in skills}

    async def list_skills(self, request: Any, /) -> Sequence[Skill]:
        """Return skills visible to the current request."""
        _ = request
        return tuple(self._skills.values())

    async def get_skill(self, request: Any, name: str, /) -> Skill | None:
        """Look up a single skill by name for the current request."""
        _ = request
        return self._skills.get(name)

    async def read_file(self, request: Any, skill: Skill, file: SkillFile, /) -> bytes:
        """Read raw bytes for an indexed skill file."""
        _ = (request, skill)
        return file.content or b""


runbook_skill = Skill.build(
    "incident-runbook",
    "Operational runbook for incident triage.",
    "# Incident Runbook\nVerify service health before paging.\n",
    files={"references/escalation.md": "Escalate P0 incidents within 5 minutes."},
)
source: SkillSource = TenantSkillSource([runbook_skill])

app = Litestar(
    plugins=[
        LitestarMCP(
            MCPConfig(
                name="Skills Server",
                skills=MCPSkillsConfig(
                    paths=[Path("skills")],
                    sources=[source],
                    directory_read=True,
                    max_files_per_skill=512,
                    max_bytes_per_skill=16_777_216,
                ),
            )
        )
    ]
)
```

- **Static and dynamic composition**: `MCPSkillsConfig` requires at least one entry in `paths` or `sources`. `SkillCatalog.from_config` composes `paths` first (via `FilesystemSkillSource`, which scans immediate child directories for regular `SKILL.md` files and locks SHA-256 digests at startup) followed by `sources` (`SkillSource` protocol). Earlier sources win on duplicate skill names with a warning.
- **In-memory skill builders**: Build skills without disk files via `Skill.build(name, description, body, *, metadata=None, files=None)`, `Skill.from_content(skill_md, files=None)`, and `SkillFile.from_content(skill_name, relative_path, content)`. Every `SkillFile` carries a `skill://<name>/<relative_path>` URI, MIME type, byte size, and `sha256:<hex>` digest verified on `catalog.read_file(request, match)`.
- **Request-aware `SkillCatalog` methods**: `catalog.list_skills(request)`, `get_skill(request, name)`, `get(request, uri)`, `get_file(request, uri)`, `list_directory(request, uri)`, `resource_entries(request)`, and `read_file(request, match)` are async and accept the active Litestar `Request` so dynamic `SkillSource` backends can filter by tenant or principal.
- **Discovery and methods**: When enabled, `server/discover` advertises `"io.modelcontextprotocol/skills": {"directoryRead": True}` under `capabilities.extensions` and exposes `skills/list`, `skills/get`, `resources/directory/read` (when `directory_read=True`), and `skill://` reads via `resources/read` (`SkillIntegrityError` fails the read if the content does not match the manifest digest).

### Agent Runtime, `AgentGroup`, Workflows, And Protocol Bridges

`litestar_mcp.agent` provides a provider-neutral multi-agent runtime, DAG workflow engine, and bidirectional MCP / A2A bridges. Install `litestar-mcp[google-genai]` for `GoogleGenAIClient` (defaulting to `model="gemini-3.8-flash"` and accepting an optional `httpx2.AsyncClient` via `http_client=`), `litestar-mcp[queues]` for distributed `litestar-queues` execution (`QueuedAgentChatController`, `QueuedTurnManager`, `AgentRegistry`), and `litestar-mcp[opentelemetry]` for GenAI semantic convention spans (`TelemetryConfig`, `SpanManager`).

```python
from litestar import Litestar
from litestar.di import Provide
from litestar_mcp import SkillController, tool
from litestar_mcp.agent import (
    Agent,
    AgentChatController,
    AgentGroup,
    AgentRuntime,
    DynamicWorkflow,
    GoogleGenAIClient,
    TurnBudget,
    WorkflowContext,
    WorkflowEngine,
    agent_to_a2a,
    agent_to_mcp,
)
from litestar_mcp.core.observability import SpanManager, TelemetryConfig


class BillingSkill(SkillController):
    """Billing skill shared across MCP, AgentRuntime, and A2A."""

    name = "billing"
    description = "Inspect and refund customer invoices."
    tags = ("finance", "billing")

    @tool(description="Refund an invoice by ID.")
    async def refund_invoice(self, invoice_id: str) -> dict[str, str]:
        """Process an invoice refund."""
        return {"invoice_id": invoice_id, "status": "refunded"}


billing_specialist = Agent(
    name="billing_specialist",
    description="Handles billing and invoice refunds.",
    instructions="Verify invoice IDs before issuing refunds.",
    skills=(BillingSkill,),
)

coordinator = Agent(
    name="support_coordinator",
    description="Triages customer requests and delegates to specialists.",
    instructions="Transfer billing questions to billing_specialist.",
)

support_group = AgentGroup(
    coordinator=coordinator,
    specialists=(billing_specialist,),
)

runtime = AgentRuntime(
    support_group,
    default_model=GoogleGenAIClient(model="gemini-3.8-flash"),
    budget=TurnBudget(max_turns=10, max_tool_calls=25, timeout_seconds=120.0),
    span_manager=SpanManager(TelemetryConfig(enable_spans=True)),
)

workflow = DynamicWorkflow(name="triage-pipeline")
workflow.add_node(
    "classify",
    handler=lambda ctx: f"ticket:{ctx.state.get('ticket_id', 'unknown')}",
)
workflow.add_node(
    "resolve",
    agent=billing_specialist,
    depends_on=("classify",),
    prompt=lambda ctx: f"Resolve {ctx.step_results['classify'].output}",
)
workflow_engine = WorkflowEngine(default_runtime=runtime)

app = Litestar(
    route_handlers=[AgentChatController],
    dependencies={"runtime": Provide(lambda: runtime, sync_to_thread=False)},
    plugins=[
        agent_to_mcp(support_group, path="/mcp"),
        agent_to_a2a(
            support_group,
            path="/a2a",
            base_url="https://api.example.com",
            runtime=runtime,
        ),
    ],
)
```

- **`Agent` and `AgentGroup`**: `AgentGroup(coordinator=..., specialists=(...,))` synthesizes a `transfer_to_agent` tool (`TRANSFER_TOOL_NAME`) on the coordinator with a `Literal[...]` of specialist names and switches the active agent mid-turn when invoked.
- **Sessions**: `AgentRuntime` defaults to `MemorySessionStore`; use `LitestarStoreSessionStore(store)` from `litestar_mcp.agent.sessions` to persist multi-turn conversation history in a Litestar `Store` scoped by `ToolContext.owner_key()`.
- **Remote MCP tools**: Convert tools from a `LitestarMCP` plugin or `MCPStreamableHTTPClient` with `mcp_to_tools(client)` or `await discover_mcp_tools("https://api.example.com/mcp")`.
- **Distributed queues (`litestar_mcp.queues`)**: Mount `QueuedAgentChatController` with `QueuedTurnManager` and `AgentRegistry` (`set_agent_registry`, `set_channels_service`) to enqueue turns via `POST /agent/turns` (`202 Accepted`) and stream frames over Litestar `ChannelsPlugin` at `GET /agent/turns/{turn_id}/stream`.

### A2A 1.0 Integration (`LitestarA2A`)

Install `litestar-mcp[a2a]` to mount the official `a2a-sdk` JSON-RPC 1.0 handler on Litestar routes via `LitestarA2A` and `A2AConfig` (lazy-exported from `litestar_mcp` and `litestar_mcp.a2a`), or bridge an `Agent` / `AgentGroup` directly with `agent_to_a2a(...)`:

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from litestar import Litestar
from litestar_mcp import A2AConfig, LitestarA2A


class SupportAgentExecutor(AgentExecutor):
    """Execute A2A requests against application services."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Process an incoming A2A message or task."""
        _ = (context, event_queue)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel an active A2A task."""
        _ = (context, event_queue)


card = AgentCard(
    name="Support Agent",
    description="Answers customer support inquiries.",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=True),
    skills=[
        AgentSkill(
            id="triage_ticket",
            name="Triage Ticket",
            description="Classify and route support tickets.",
            tags=["support"],
        )
    ],
    supported_interfaces=[
        AgentInterface(
            url="https://api.example.com/a2a",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
    ],
)

request_handler = DefaultRequestHandler(
    agent_executor=SupportAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=card,
)

app = Litestar(
    plugins=[
        LitestarA2A(
            agent_card=card,
            request_handler=request_handler,
            config=A2AConfig(path="/a2a", agent_card_path="/.well-known/agent-card.json"),
        )
    ]
)
```

`LitestarA2A` validates at startup that `agent_card.supported_interfaces` includes an absolute `JSONRPC` 1.0 URL whose path ends with `A2AConfig.path`, and raises `ValueError` on route collisions. It registers:

- `POST /a2a` (`A2AConfig.path`) — JSON-RPC 2.0 and SSE streaming endpoint (`SendMessage`, `SendStreamingMessage`, `GetTask`, `ListTasks`, `CancelTask`, `SubscribeToTask`, push notification config methods, and `GetExtendedAgentCard`). JSON-RPC notifications (requests without `id`) are declined with `204 No Content`.
- `GET /.well-known/agent-card.json` (`A2AConfig.agent_card_path`) — public agent card discovery endpoint with `ETag` (`304 Not Modified` on `If-None-Match`) and `Cache-Control: public, max-age=300` (`A2AConfig.agent_card_max_age`).

| `A2AConfig` Option | Type | Default | Description |
| --- | --- | --- | --- |
| `path` | `str` | `"/a2a"` | Mount path of the A2A JSON-RPC route |
| `agent_card_path` | `str` | `"/.well-known/agent-card.json"` | Mount path of the public agent card route |
| `guards` | `Sequence[Guard]` | `()` | Litestar guards applied to the JSON-RPC route |
| `route_opt` | `dict[str, Any]` | `{}` | Extra `opt` entries merged into the JSON-RPC route (e.g., `{AUTH_POLICY_OPT_KEY: required("oidc")}`) |
| `context_builder` | `Callable[[Request, ServerCallContext], ServerCallContext \| Awaitable[ServerCallContext]] \| None` | `None` | Callback to authorize tenants or enrich the SDK `ServerCallContext` |
| `include_in_schema` | `bool` | `False` | Include `/a2a` and `/.well-known/agent-card.json` in OpenAPI |
| `agent_card_max_age` | `int` | `300` | `Cache-Control` `max-age` in seconds for the agent card |
| `stream_cleanup_timeout` | `float` | `5.0` | Positive finite seconds allowed for stream producer cleanup |

When using Dishka (`setup_dishka`), `LitestarA2A` populates `context.call_context.state` with `auth`, `headers`, and `litestar_state` (`request.scope["state"]`). Inside `AgentExecutor.execute`, open a fresh `Scope.REQUEST` child container from your root `AsyncContainer` (`async with self._container(scope=Scope.REQUEST) as req_container:`) when resolving request-scoped services across streaming or task lifecycles.

### Binary Resources And Tool Results

Return `MCPResourceLink` from a tool when a stable resource URI can be fetched later. Return `MCPBlobResource` only when the binary must be embedded immediately. Use `MCPToolResult` when one result needs mixed content blocks, `structuredContent`, `isError`, or `_meta`. Use `MCPInputRequiredResult` when multi-round-trip client inputs are requested.

```python
from litestar import Response, get
from litestar_mcp import MCPResourceLink


@get("/reports/latest-link", mcp_tool="generate_report")
async def generate_report() -> MCPResourceLink:
    """Provide a linked resource pointing to the generated report."""
    return MCPResourceLink(
        name="report.pdf",
        uri="litestar://latest_report",
        mime_type="application/pdf",
        size=4,
    )


@get(
    "/reports/latest",
    mcp_resource="latest_report",
    mcp_resource_mime_type="application/pdf",
)
async def latest_report() -> Response[bytes]:
    """Stream binary content for the latest report."""
    return Response(content=b"%PDF", media_type="application/pdf")
```

This produces a `resource_link` block from `tools/call`; `resources/read` returns the response bytes as a base64 `blob`. `MCPBlobResource(uri=..., data=..., mime_type=...)` produces an embedded `resource` block directly in a tool result. The plugin enforces `max_blob_bytes` before base64 encoding for helper objects, explicit resource blocks, and `resources/read`. An oversized tool payload becomes a tool result with `isError: true`; an oversized resource becomes a `Resource read failed` JSON-RPC error.

Set resource MIME metadata with `mcp_resource_mime_type=` on a Litestar route, `mime_type=` on `@mcp_resource`, or `mime_type=` on `@mcp.resource`. The handler response `Content-Type` wins during `resources/read`; configured metadata is the fallback and the value advertised by resource listings. The default is `application/json`.

Textual MIME types return `text`: `text/*`, JSON, XML, JavaScript, and YAML types are textual. Other MIME types return base64 `blob`; invalid UTF-8 under an otherwise textual MIME type also falls back to `blob`.

### Multi-Round-Trip Inputs

Return `MCPInputRequiredResult` when a tool or task requires additional information from the client before proceeding:

```python
from litestar import post
from litestar_mcp import MCPInputRequiredResult, MCPRequestContext, get_mcp_request_context


@post("/deploy", mcp_tool="deploy_service")
async def deploy_service(environment: str) -> MCPInputRequiredResult | dict[str, str]:
    """Deploy service with confirmation on production."""
    ctx: MCPRequestContext = get_mcp_request_context()
    if environment == "production":
        if not ctx.input_responses or "confirm" not in ctx.input_responses:
            return MCPInputRequiredResult(
                input_requests={
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirm production deployment",
                    }
                },
                request_state="awaiting_confirmation",
            )
    return {"status": "deployed", "environment": environment}
```

### CLI Commands

The `litestar-mcp` CLI extension provides commands under the `mcp` group:

```bash
# List all registered tools in the application
litestar mcp list-tools

# List all registered resources in the application
litestar mcp list-resources

# Run a specific tool or resource handler locally
litestar mcp run list_users

# Serve the Litestar app's MCP endpoint in-process over stdio
litestar mcp stdio

# Proxy local stdio JSON-RPC to a running Streamable HTTP MCP endpoint
litestar mcp bridge --endpoint http://127.0.0.1:8000/mcp
```

### Hiding Routes

Discovery is opt-in: a handler that carries no `mcp_*` marker never appears in MCP. There is no per-route exclude flag — `opt={"mcp_exclude": True}` is ignored.

```python
from litestar import get


@get("/internal/metrics")
async def metrics() -> dict[str, int]:
    """Internal metrics handler omitted from MCP."""
    return {"active_connections": 42}
```

To drop marked routes in bulk, use `MCPConfig` filters (`exclude_tags` / `exclude_operations`, or `include_tags` / `include_operations` allowlists). Filtered tools/resources/templates are absent from list responses and fail direct calls as unknown; enforce real access control with `guards` or `route_opt` auth policies.

### JSON-RPC Call

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

### Pagination, Signatures, And Errors

`tools/list`, `resources/list`, `resources/templates/list`, `skills/list`, `prompts/list`, and `resources/directory/read` use opaque cursor pagination. Clients pass `params.cursor` from `nextCursor` until the response omits it; clients do not send `limit`. Set server page size with `MCPConfig(list_page_size=...)`; invalid cursors return `INVALID_PARAMS` (`-32602`).

Tool arguments are validated against Litestar's `handler.parsed_fn_signature` before dispatch:

- **Controller and route path parameters**: Handlers declared on `Controller` classes or standalone routes resolve path parameters per application (`app.state`) without requiring weak-referenceable handler objects.
- **Omitted vs. explicit falsey bodies**: Omitting an optional `data` body preserves the handler's declared default, while explicit falsey JSON values (`null`, `false`, `0`, `""`, `[]`, `{}`) pass through unchanged.
- **Parameter wire aliases**: Query parameter wire names declared via `QueryParameter(name=...)` or `Parameter(query=...)` (`ParameterKwarg.name`, including `advanced-alchemy` and `sqlspec` `create_filter_dependencies` providers such as `categoryNameIn`, `currentPage`, `pageSize`) are advertised in `inputSchema` and dispatched under their wire alias. `HeaderParameter` and `CookieParameter` annotations are skipped for query wire-name resolution. For backwards compatibility, callers sending the Python parameter name are rewritten to the wire name with a warning; when both are supplied, the wire name wins.
- **Reserved Litestar kwargs on `@tool` methods**: Parameters named after Litestar's `RESERVED_KWARGS` (`query`, `headers`, `cookies`, `state`, `socket`, `scope`, `receive`, `send`, `body`) on `@tool` functions and `SkillController` methods are aliased to `_mcp_param_<name>` on the synthesized Litestar route handler while remaining `<name>` in MCP `inputSchema` and `tool.execute(...)`.

Tool execution errors stay inside the tool result with `isError: true`; protocol errors such as unknown tool names use JSON-RPC errors. Resource and prompt handler failures use primitive-level JSON-RPC codes and preserve the handler HTTP status in `error.data.statusCode` when a handler response produced one.

### Tool-Call Callbacks

Use `MCPConfig.before_tool_call` and `MCPConfig.after_tool_call` for audit, metrics, or tracing that must fire around `tools/call` regardless of route ownership. Both callbacks receive the MCP tool name, a shallow copy of submitted arguments, and the synthesized `Request`. `after_tool_call` also receives keyword-only `result`, `exception`, and `duration`; it fires for successes, guard failures, handled error responses, and unhandled exceptions. Callback exceptions are logged and swallowed.

### Built-in OpenAPI Resource

`LitestarMCP` exposes the app OpenAPI schema as:

- URI: `litestar://openapi`
- MIME type: `application/json`
- Method: `resources/read`

This resource is always present in `resources/list`; `MCPConfig.include_in_schema` does not remove it.

`include_in_schema=False` is the default on both `MCPConfig` and `A2AConfig`. It hides the plugin-owned `/mcp` path (and `/a2a` plus `/.well-known/agent-card.json` when `LitestarA2A` is used) from generated OpenAPI, while ordinary application routes—including routes marked for MCP—keep their own OpenAPI visibility. Set `include_in_schema=True` on `MCPConfig` or `A2AConfig` to include those plugin-owned routes in OpenAPI.

### Auth

Authentication and RFC 9728 OAuth 2.1 protected-resource discovery are handled by `litestar-security` (or your existing Litestar middleware and guards):

- Attach `litestar-security` authentication policies to the mounted MCP router with `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` (and to A2A with `A2AConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})`).
- Publish `GET /.well-known/oauth-protected-resource` with `litestar-security`'s `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`.
- Enforce fine-grained role, scope, tenant, or capability checks on individual routes, `SkillController` / `PromptController` classes, or routers with `litestar-security` guards (`requires_scope`, `requires_role`, `requires_tenant`, `requires_capability`) or custom Litestar `guards=[...]`.

```python
from litestar import Litestar
from litestar_mcp import LitestarMCP, MCPConfig
from litestar_security import SecurityConfig, SecurityPlugin, required
from litestar_security.authentication import AUTH_POLICY_OPT_KEY
from litestar_security.providers.oauth import ProtectedResourceConfig

security_config = SecurityConfig(
    protected_resource=ProtectedResourceConfig(
        resource="https://api.example.com/mcp",
        authorization_servers=("https://company.okta.com",),
        scopes_supported=("mcp:read", "mcp:write"),
    ),
)

mcp_config = MCPConfig(
    name="Protected MCP API",
    route_opt={AUTH_POLICY_OPT_KEY: required("oidc")},
)

app = Litestar(
    route_handlers=[],
    plugins=[
        SecurityPlugin(security_config),
        LitestarMCP(mcp_config),
    ],
)
```

When connecting through an identity proxy (such as Google Cloud IAP) with `litestar mcp bridge` or `litestar mcp stdio`, match the proxy's header scheme using `--header-name X-Goog-IAP-JWT-Assertion --token-prefix ""`.

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-mcp
```

Install `litestar-mcp[a2a]` for `LitestarA2A` / `agent_to_a2a`, `litestar-mcp[google-genai]` for `GoogleGenAIClient`, `litestar-mcp[queues]` for `QueuedAgentChatController`, and `litestar-mcp[opentelemetry]` for `TelemetryConfig` / `SpanManager`.

### Step 2: Decide What to Expose

List only the routes and controllers that should be callable by AI clients. Mark HTTP routes with `mcp_tool=`, `mcp_resource=`, or `mcp_prompt=` (add `mcp_resource_template=` next to `mcp_resource=` for templated resources), or group cohesive tools, prompts, instructions, and guards in a `SkillController` or `PromptController`. Unmarked routes are never exposed.

### Step 3: Add the Plugin

Wire `LitestarMCP(MCPConfig(name=...))` into `Litestar(plugins=[...])`, or use standalone `MCP(...)` when the app exists only to serve MCP primitives. Add `skills=MCPSkillsConfig(paths=[Path("skills")], sources=[...])` to serve filesystem or dynamic `SkillSource` catalogs over `io.modelcontextprotocol/skills`, and `LitestarA2A` (or `agent_to_a2a`) when exposing an A2A 1.0 endpoint. Use `include_tags` or `include_operations` when you need a second allowlist.

### Step 4: Add Auth

Attach `litestar-security` route policies via `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` and publish RFC 9728 metadata via `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`. For internal deployments or custom middleware, use `guards=[...]`, `route_opt={...}`, or existing app auth middleware.

### Step 5: Verify

`POST /mcp` each JSON-RPC request directly (or via `MCPStreamableHTTPClient`) — `server/discover` for capabilities, then `tools/list`, `resources/list`, `prompts/list`, `tools/call`, and `resources/read` (plus `skills/list`, `skills/get`, and `resources/directory/read` when `MCPSkillsConfig` is enabled). Confirm only marked routes and registered `SkillController` / `PromptController` primitives appear, call one representative tool, and read one representative resource. Verify both `text` and `blob` resource paths when exposing binary data. For standalone stdio apps, send one line-delimited JSON-RPC request through stdin and confirm the response is written to stdout. For bridge deployments, verify stdout purity, concurrent request streams, and auth refresh paths.

</workflow>

<guardrails>

## Guardrails

- **Mark routes explicitly** - unmarked routes should not appear in MCP clients.
- **Default to allowlists** - `include_tags` / `include_operations` keep the tool set small and gate direct invocation; pair them with `guards` or `route_opt` auth policies for authorization.
- **Never expose admin or destructive routes by default** - require a human-confirmation workflow or multi-round-trip verification (`MCPInputRequiredResult`) before any irreversible operation.
- **Prefer resources for read-only reference data** - agents may read resources speculatively.
- **Keep DTOs precise** - loose `dict[str, Any]` request schemas produce weak tool contracts.
- **Use `SkillController` to share tools and instructions across MCP, `Agent`, and A2A** - avoid duplicating tool wrappers for HTTP/MCP and `AgentRuntime`.
- **Delegate auth and RFC 9728 metadata to `litestar-security`** - `litestar_mcp.auth` was removed in `0.14.0`; use `MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required(...)})` and `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`.
- **Set `allowed_origins` for browser-accessible MCP clients** - leave it `None` only for trusted server-to-server deployments.
- **Prefer `MCPResourceLink` over inline blobs** - linked resources avoid base64 expansion and let the application enforce authorization when the client reads the resource.
- **Keep `max_blob_bytes` bounded** - base64 embedding increases memory and wire size; disable the cap only behind a stricter application-owned limit.
- **Resolve stdio credentials out of band** - inject the verified principal with `MCPStdioContext`; JSON-RPC messages are not an authentication channel.
- **Treat `MCP`, `LitestarMCP`, `SkillController`, `PromptController`, `AgentRuntime`, and `LitestarA2A` as public entry points** - avoid private router/service imports.
- **Keep observability callbacks side-effect safe** - `before_tool_call` / `after_tool_call` failures are swallowed, so callbacks must not enforce authorization or business invariants.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering an MCP integration, verify:

- [ ] Existing Litestar apps include `LitestarMCP` in `app.plugins`; standalone apps expose `app = mcp.app`
- [ ] Exposed routes/controllers use `mcp_tool=`, `mcp_resource=`, `mcp_prompt=`, `SkillController`, `PromptController`, `@tool`, `@prompt`, `@mcp.tool`, `@mcp.resource`, or `@mcp.prompt`
- [ ] Admin / internal routes are left unmarked, or kept outside `include_*` / inside `exclude_*` — with `guards` or `route_opt` auth policies enforcing access
- [ ] Auth is configured for the deployment boundary (`MCPConfig(route_opt=...)`, `SecurityConfig(protected_resource=ProtectedResourceConfig(...))`, `guards=[...]`, or custom middleware)
- [ ] `POST /mcp` `tools/list` returns only intended tools (including `SkillController` tools mounted in nested `Router` / `DishkaRouter` trees)
- [ ] `POST /mcp` `resources/list` includes only intended resources plus `litestar://openapi` (and indexed skill files when `MCPSkillsConfig` is enabled)
- [ ] When `MCPSkillsConfig` is enabled, `skills/list`, `skills/get`, `resources/directory/read`, and `resources/read` verify `skill://` URIs and SHA-256 digests across both filesystem `paths` and dynamic `sources`
- [ ] When `LitestarA2A` or `agent_to_a2a` is enabled, `GET /.well-known/agent-card.json` and `POST /a2a` match the `AgentCard` JSON-RPC 1.0 interface URL
- [ ] Filtered tools/resources/templates fail direct invocation as unknown
- [ ] Provider-declared user inputs appear in tool `inputSchema`; injected DI parameters (`Provide`, `FromDishka`, `Inject`, `Depends`, `ToolContext`, `Request`) do not
- [ ] `before_tool_call` / `after_tool_call` callbacks are covered when configured, including failure paths
- [ ] Standalone `MCP` `streamable-http` or `stdio` transport is smoke-tested for the chosen deployment mode
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

- **[Stateless Protocol](references/stateless-protocol.md)** — the POST-only transport, `server/discover`, `subscriptions/listen`, progress reporting, `MCPStreamableHTTPClient`, the tasks and dynamic skills extensions, `SkillController` / `PromptController`, `LitestarA2A`, MRTR results, response caching, and client migration.

## Cross-References

- Use this skill for route marking, `SkillController` / `PromptController`, transport and stdio behavior, `MCPSkillsConfig` (`FilesystemSkillSource` and `SkillSource`), `MCPStreamableHTTPClient`, `LitestarA2A`, binary content, and verification requests.
- Use [litestar-ai](../litestar-ai/SKILL.md) for deep multi-agent orchestration patterns (`Agent`, `AgentGroup`, `AgentRuntime`, `DynamicWorkflow`, `QueuedAgentChatController`, and Google ADK comparison).
- Use [litestar-security](../litestar-security/SKILL.md) for `SecurityPlugin`, `SecurityConfig`, `ProtectedResourceConfig`, and `AUTH_POLICY_OPT_KEY` / `required(...)` route policies.
- Use [Litestar auth & guards](../litestar/references/auth-and-guards.md) when auth logic lives in normal Litestar guards or middleware.

## Official References

- <https://github.com/cofin/litestar-mcp/releases/tag/v0.16.0> — audited v0.16.0 release
- <https://cofin.github.io/litestar-mcp/>
- <https://github.com/cofin/litestar-mcp>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>
- <https://a2a-protocol.org/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
