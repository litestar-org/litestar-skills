---
name: litestar-mcp
description: "Auto-activate for litestar_mcp, LitestarMCP, MCPConfig, MCPAuthConfig, MCPAuthBackend, mcp_tool=, mcp_resource=, Streamable HTTP, or OIDC MCP endpoints. Not for non-Litestar MCP."
---

# litestar-mcp

`litestar-mcp` exposes explicitly marked Litestar route handlers as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools and resources over MCP Streamable HTTP and JSON-RPC 2.0.

Mark routes with `mcp_tool="name"` or `mcp_resource="name"` directly on Litestar route decorators. Do not use the removed `@mcp_tool` / `@mcp_resource` decorator API or `opt={"mcp_tool_name": ...}` wrappers.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O - handlers exposed through MCP must be `async def`

## Quick Reference

### Install

```bash
pip install litestar-mcp
```

### Basic Setup

```python
from litestar import Litestar, get, post
from litestar.openapi.config import OpenAPIConfig
from litestar_mcp import LitestarMCP, MCPConfig


@get("/users", mcp_tool="list_users")
async def list_users() -> list[dict]:
    return [{"id": 1, "name": "Alice"}]


@post("/analyze", mcp_tool="analyze_data")
async def analyze_data(data: dict) -> dict:
    return {"count": len(data)}


@get("/config", mcp_resource="app_config")
async def get_app_config() -> dict:
    return {"debug": False}


app = Litestar(
    route_handlers=[list_users, analyze_data, get_app_config],
    plugins=[LitestarMCP(MCPConfig(name="My API"))],
    openapi_config=OpenAPIConfig(title="My API", version="1.0.0"),
)
```

The default MCP surface is:

| Endpoint | Purpose |
| --- | --- |
| `GET /mcp` | Server-Sent Events stream when requested by the client |
| `POST /mcp` | JSON-RPC endpoint for `initialize`, `ping`, `tools/*`, `resources/*`, and optional task methods |
| `GET /.well-known/mcp-server.json` | MCP server manifest |
| `GET /.well-known/agent-card.json` | Agent card metadata |
| `GET /.well-known/oauth-protected-resource` | OAuth protected-resource metadata when auth is configured |

### MCPConfig

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `base_path` | `str` | `"/mcp"` | URL prefix for the MCP Streamable HTTP endpoint |
| `include_in_schema` | `bool` | `False` | Include MCP routes in OpenAPI |
| `name` | `str \| None` | `None` | Server name; defaults to OpenAPI title |
| `guards` | `list[Any] \| None` | `None` | Litestar guards applied to the MCP router |
| `allowed_origins` | `list[str] \| None` | `None` | Restrict accepted `Origin` headers |
| `include_operations` | `list[str] \| None` | `None` | Only expose matching operation names |
| `exclude_operations` | `list[str] \| None` | `None` | Exclude matching operation names |
| `include_tags` | `list[str] \| None` | `None` | Only expose routes with matching OpenAPI tags |
| `exclude_tags` | `list[str] \| None` | `None` | Exclude routes with matching OpenAPI tags |
| `auth` | `MCPAuthConfig \| None` | `None` | OAuth protected-resource metadata |
| `tasks` | `bool \| MCPTaskConfig` | `False` | Enable experimental in-memory MCP task support |

### Route Marking

```python
from litestar import get, post


@get("/products", mcp_resource="product_list")
async def list_products() -> list[dict]: ...


@post("/cart/items", mcp_tool="add_to_cart")
async def add_to_cart(data: CartItem) -> Cart: ...


@get("/products/{product_id:int}", mcp_resource_template="shop://products/{product_id}")
async def get_product(product_id: int) -> dict: ...
```

Use structured metadata when the agent needs sharper tool selection:

```python
@post(
    "/reports",
    mcp_tool="generate_report",
    mcp_description="Generate a report for an existing account.",
    mcp_when_to_use="Use after the user has confirmed the account and date range.",
    mcp_returns="A report id and queued status.",
)
async def generate_report(data: ReportRequest) -> ReportQueued: ...
```

### Excluding Routes

```python
@get("/internal/metrics", opt={"mcp_exclude": True})
async def metrics() -> dict: ...
```

### JSON-RPC Call

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "add_to_cart",
    "arguments": { "product_id": 42, "quantity": 3 }
  }
}
```

### Built-in OpenAPI Resource

`LitestarMCP` exposes the app OpenAPI schema as:

- URI: `litestar://openapi`
- MIME type: `application/json`
- Method: `resources/read`

### Auth

Authentication is a Litestar middleware concern. Apps with existing auth middleware get `request.user` / `request.auth` before tool handlers run.

For OIDC-backed MCP endpoints, pair `MCPAuthConfig` metadata with token validation:

```python
from litestar import Litestar
from litestar.middleware import DefineMiddleware
from litestar_mcp import LitestarMCP, MCPAuthBackend, MCPConfig, OIDCProviderConfig
from litestar_mcp.auth import MCPAuthConfig


app = Litestar(
    route_handlers=[...],
    plugins=[
        LitestarMCP(
            MCPConfig(
                auth=MCPAuthConfig(
                    issuer="https://company.okta.com",
                    audience="api://mcp-tools",
                )
            )
        )
    ],
    middleware=[
        DefineMiddleware(
            MCPAuthBackend,
            providers=[
                OIDCProviderConfig(
                    issuer="https://company.okta.com",
                    audience="api://mcp-tools",
                )
            ],
            user_resolver=lambda claims, app: MyUser(sub=claims["sub"]),
        )
    ],
)
```

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-mcp
```

### Step 2: Decide What to Expose

List only the routes that should be callable by AI clients. Mark those routes with `mcp_tool=`, `mcp_resource=`, or `mcp_resource_template=`. Do not rely on route method defaults.

### Step 3: Add the Plugin

Wire `LitestarMCP(MCPConfig(name=...))` into `Litestar(plugins=[...])`. Use `include_tags` or `include_operations` when you need a second allowlist.

### Step 4: Add Auth

For public endpoints, configure bearer-token validation and `MCPAuthConfig` metadata. For internal deployments, use `guards=[...]` or existing app auth middleware.

### Step 5: Verify

Hit `POST /mcp` with `tools/list` and `resources/list`. Confirm only marked routes appear. Call one representative tool and read one representative resource.

</workflow>

<guardrails>

## Guardrails

- **Mark routes explicitly** - unmarked routes should not appear in MCP clients.
- **Default to allowlists** - `include_tags` / `include_operations` prevent accidental exposure when route sets grow.
- **Never expose admin or destructive routes by default** - require a human-confirmation workflow before any irreversible operation.
- **Prefer resources for read-only reference data** - agents may read resources speculatively.
- **Keep DTOs precise** - loose `dict[str, Any]` request schemas produce weak tool contracts.
- **Use `MCPAuthConfig` plus token validation for public MCP** - metadata alone does not authenticate requests.
- **Set `allowed_origins` for browser-accessible MCP clients** - leave it `None` only for trusted server-to-server deployments.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering an MCP integration, verify:

- [ ] `LitestarMCP` is in `app.plugins`
- [ ] Exposed routes use `mcp_tool=`, `mcp_resource=`, or `mcp_resource_template=`
- [ ] Admin / internal routes use `opt={"mcp_exclude": True}` or are outside the allowlist
- [ ] Auth is configured for the deployment boundary
- [ ] `POST /mcp` `tools/list` returns only intended tools
- [ ] `POST /mcp` `resources/list` includes only intended resources plus `litestar://openapi`
- [ ] Exposed handlers are `async def` and return JSON-serializable types
- [ ] Tool argument DTOs are specific enough for generated schemas

</validation>

<example>

## Example

**Task:** Expose product listing as a resource and add-to-cart as a tool. Hide internal metrics.

```python
from litestar import Litestar, get, post
from litestar_mcp import LitestarMCP, MCPConfig


@get("/products", mcp_resource="product_list", tags=["public"])
async def list_products() -> list[dict]:
    return [{"id": 1, "name": "Widget"}]


@post("/cart/items", mcp_tool="add_to_cart", tags=["public"])
async def add_to_cart(data: CartItem) -> Cart: ...


@get("/internal/metrics", opt={"mcp_exclude": True})
async def metrics() -> dict: ...


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

- Use this skill for route marking, Streamable HTTP endpoint behavior, MCP auth metadata, and verification requests.
- Use [litestar-auth-guards](../litestar-auth-guards/SKILL.md) when auth logic lives in normal Litestar guards or middleware.

## Official References

- <https://docs.litestar-mcp.litestar.dev/>
- <https://github.com/litestar-org/litestar-mcp>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
