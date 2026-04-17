---
name: litestar-mcp
description: "Auto-activate for litestar_mcp imports, LitestarMCP, MCPConfig, @mcp_tool, @mcp_resource, MCPController. The first-party Litestar plugin exposing route handlers as Model Context Protocol (MCP) tools and resources over JSON-RPC 2.0. Produces LitestarMCP plugin configs, @mcp_tool / @mcp_resource decorators, route filtering (include/exclude tags/operations), OpenAPI-aligned schemas, and OAuth 2.1 / Guard-based auth setups. Use when: exposing a Litestar API to LLM agents, wiring an MCP server, controlling which routes are visible to AI, or aligning MCP tool schemas with OpenAPI. Not for non-Litestar MCP servers (use the upstream Python MCP SDK) or for FastAPI/Django."
---

# litestar-mcp

`litestar-mcp` exposes Litestar route handlers as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools and resources over JSON-RPC 2.0. The plugin discovers routes via the Litestar OpenAPI schema and serves them at `POST /mcp/` (configurable).

GET handlers become **resources** (read-only); POST/PUT/PATCH/DELETE handlers become **tools** (mutations). Per-route overrides via `@mcp_tool`, `@mcp_resource`, or `opt={...}` dicts.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O — handlers exposed via MCP must be `async def`

## Quick Reference

### Install

```bash
pip install litestar-mcp
```

### Basic Setup

```python
from litestar import Litestar, get
from litestar_mcp import LitestarMCP, MCPConfig

@get("/users", name="list_users")
async def get_users() -> list[dict]: ...

app = Litestar(
    route_handlers=[get_users],
    plugins=[LitestarMCP(MCPConfig(name="My API"))],
)
```

The MCP endpoint is mounted at `POST /mcp/` by default.

### MCPConfig

| Option | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | `"litestar"` | Server name reported in `initialize` response |
| `base_path` | `str` | `"/mcp"` | URL prefix for the MCP controller |
| `guards` | `list[Guard]` | `[]` | Litestar guards applied to the MCP controller |
| `allowed_origins` | `list[str]` | `["*"]` | CORS origins for the MCP endpoint |
| `auth` | `OAuthConfig \| None` | `None` | OAuth 2.1 configuration |
| `include_operations` | `list[str] \| None` | `None` | Whitelist of operation names to expose |
| `exclude_operations` | `list[str] \| None` | `None` | Blacklist of operation names to suppress |
| `include_tags` | `list[str] \| None` | `None` | Only expose routes with these OpenAPI tags |
| `exclude_tags` | `list[str] \| None` | `None` | Suppress routes with these OpenAPI tags |

### Default Route Discovery

| HTTP Method | Default MCP Type |
|---|---|
| `GET` | resource |
| `POST` / `PUT` / `PATCH` / `DELETE` | tool |

Override per route with decorators (below).

### `@mcp_tool` — explicit tool

```python
from litestar import post
from litestar_mcp import mcp_tool

@mcp_tool("create_order")
@post("/orders")
async def create_order(data: OrderCreate) -> Order: ...
```

The string argument sets the MCP tool name. Omit it to use the route's `name` attribute.

### `@mcp_resource` — explicit resource

```python
from litestar import get
from litestar_mcp import mcp_resource

@mcp_resource("orders_list")
@get("/orders", name="list_orders")
async def list_orders() -> list[Order]: ...
```

### `opt` dict (no decorator import)

```python
@get("/internal/health", opt={"mcp_exclude": True})
async def health_check() -> dict: ...

@post("/orders", opt={"mcp_tool_name": "place_order"})
async def create_order(data: OrderCreate) -> Order: ...
```

| `opt` key | Type | Description |
|---|---|---|
| `mcp_exclude` | `bool` | Exclude this route from MCP entirely |
| `mcp_tool_name` | `str` | Override MCP tool name |
| `mcp_resource_name` | `str` | Override MCP resource name; implies resource type |

### JSON-RPC Methods

| Method | Description |
|---|---|
| `initialize` | Handshake; returns server name, version, capabilities |
| `ping` | Health check; returns `pong` |
| `resources/list` | List all discoverable MCP resources |
| `resources/read` | Read (call) a specific resource by URI |
| `tools/list` | List all discoverable MCP tools |
| `tools/call` | Invoke a tool by name with arguments |

### Example JSON-RPC Call

```json
POST /mcp/
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_order",
    "arguments": { "product_id": 42, "quantity": 3 }
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{ "type": "text", "text": "{\"id\": 99, \"status\": \"pending\"}" }]
  }
}
```

### Built-in OpenAPI Resource

`LitestarMCP` automatically exposes the Litestar OpenAPI schema as an MCP resource:

- **URI**: `openapi://schema`
- **MIME type**: `application/json`
- **Content**: Full OpenAPI 3.x schema from `/schema/openapi.json`

AI agents read this resource to understand the full API surface before calling tools.

### OAuth 2.1 Auth

```python
from litestar_mcp import MCPConfig, OAuthConfig

config = MCPConfig(
    name="My Secured API",
    auth=OAuthConfig(
        issuer="https://auth.example.com",
        client_id="mcp-client",
        scopes=["read", "write"],
    ),
)
```

PKCE is enforced. Token validation uses the issuer's JWKS endpoint.

### Guard-based Auth (simpler)

```python
config = MCPConfig(
    name="My API",
    guards=[requires_api_key],
)
```

### Filtering

```python
config = MCPConfig(
    name="Public API",
    include_tags=["public"],
    exclude_operations=["admin:delete_user", "admin:list_users"],
)
```

`include_operations` / `exclude_operations` match against route `name` attributes.

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-mcp
```

### Step 2: Decide What to Expose

List the routes that should be callable by AI agents. Use OpenAPI tags to group them (e.g., `tags=["public"]`). Routes that touch admin operations, internal metrics, or sensitive data should NOT be exposed.

### Step 3: Add the Plugin

Wire `LitestarMCP(MCPConfig(name=...))` into `Litestar(plugins=[...])`. Set `include_tags` or `include_operations` to start with an explicit allowlist.

### Step 4: Annotate Per-Route (optional)

For routes that need explicit MCP names or type overrides, use `@mcp_tool("name")`, `@mcp_resource("name")`, or `opt={"mcp_tool_name": "..."}`.

### Step 5: Add Auth

For public-facing MCP endpoints, set `OAuthConfig`. For internal use, set `guards=[...]` with API-key or session-based guards.

### Step 6: Verify

Hit `POST /mcp/` with a `tools/list` request. Confirm only intended routes appear. Hit `tools/call` for a sample mutation; confirm input validation works.

</workflow>

<guardrails>

## Guardrails

- **Default to allowlists, not blocklists** — `include_tags` is safer than `exclude_*`. Adding a new route shouldn't accidentally expose it to AI.
- **Never expose admin / destructive routes by default** — use `opt={"mcp_exclude": True}` or filter by tag.
- **Prefer resources for idempotent reads** — AI agents may call resources speculatively during reasoning. Tools have side effects; gate them behind explicit confirmation.
- **Tool argument validation runs against the OpenAPI request schema** — keep DTOs precise; loose `dict[str, Any]` schemas let agents pass anything.
- **Use `OAuthConfig` for public MCP endpoints** — JSON-RPC over HTTP is reachable from anywhere; raw API keys leak.
- **Pin `base_path`** — default `/mcp` is fine but document if changed.
- **Don't expose internal metrics, debug, or system routes** — `opt={"mcp_exclude": True}` or `exclude_tags=["internal"]`.
- **Guard the MCP controller with the same Guards as your normal API** if it shares user context.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering an MCP integration, verify:

- [ ] `LitestarMCP` is in `app.plugins`
- [ ] `MCPConfig.name` is meaningful (used in agent UIs)
- [ ] An allowlist (`include_tags` or `include_operations`) is set, not a pure blocklist
- [ ] Admin / internal routes are excluded
- [ ] Auth is configured (`auth=OAuthConfig` or `guards=[...]`)
- [ ] `POST /mcp/` `tools/list` returns only intended routes
- [ ] All exposed handlers are `async def` and return JSON-serializable types
- [ ] Tool arg schemas (DTOs) are precise — no loose `dict[str, Any]`

</validation>

<example>

## Example

**Task:** Expose product listing as a resource and "add to cart" as a tool. Hide internal metrics.

```python
from litestar import Litestar, get, post
from litestar_mcp import LitestarMCP, MCPConfig, mcp_tool, mcp_resource

@mcp_resource("product_list")
@get("/products", name="list_products", tags=["public"])
async def list_products() -> list[dict]:
    return [{"id": 1, "name": "Widget"}]

@mcp_tool("add_to_cart")
@post("/cart/items", name="cart:add", tags=["public"])
async def add_to_cart(data: CartItem) -> Cart: ...

@get("/internal/metrics", opt={"mcp_exclude": True})
async def metrics() -> dict: ...

app = Litestar(
    route_handlers=[list_products, add_to_cart, metrics],
    plugins=[LitestarMCP(MCPConfig(
        name="E-Commerce API",
        include_tags=["public"],
    ))],
)
```

</example>

---

## Notes

- `tools/call` arguments are validated against the route's OpenAPI request schema before dispatch.
- Response content is serialized to JSON string and wrapped in MCP `TextContent`.
- `LitestarMCP` does not affect normal HTTP routing — all existing endpoints continue to work unchanged.
- Use `exclude_operations` or `opt={"mcp_exclude": True}` to keep internal/admin routes hidden from MCP clients.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app, Guards, OpenAPI, plugin lifecycle.

## Official References

- <https://github.com/litestar-org/litestar-mcp>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
