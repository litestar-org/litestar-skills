---
name: litestar-mcp
description: "Auto-activate for litestar_mcp, LitestarMCP, MCPConfig, MCPAuthConfig, MCPAuthBackend, mcp_tool=, mcp_resource=, Streamable HTTP, or OIDC MCP endpoints. Not for non-Litestar MCP."
---

# litestar-mcp

`litestar-mcp` exposes explicitly marked Litestar route handlers as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, resources, and prompts over MCP Streamable HTTP and JSON-RPC 2.0.

Mark routes by passing `mcp_tool="name"`, `mcp_resource="name"`, or `mcp_prompt="name"` directly to the Litestar route decorator — Litestar funnels unknown kwargs into `handler.opt`, so no `opt={...}` wrapper is needed. The `@mcp_tool` / `@mcp_resource` / `@mcp_prompt` decorators (importable from `litestar_mcp`) still exist and are worth reaching for when you need the extra fields they expose — `output_schema`, `annotations`, `scopes`, `task_support`, prompt `arguments`. There is no `opt={"mcp_tool_name": ...}` form and no `mcp_exclude` key; neither is read. To hide a route, simply leave it unmarked (discovery is opt-in).

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
| `POST /mcp` | JSON-RPC endpoint for `initialize`, `ping`, `tools/*`, `resources/*`, `prompts/*`, `completion/complete`, and optional task methods |
| `DELETE /mcp` | Terminate the current MCP session |
| `GET /.well-known/mcp-server.json` | MCP server manifest |
| `GET /.well-known/agent-card.json` | Agent card metadata |
| `GET /.well-known/oauth-protected-resource` | OAuth protected-resource metadata (always registered; populated from `auth`) |

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
| `list_page_size` | `int` | `100` | Page size for `tools/list`, `resources/list`, `resources/templates/list`, `prompts/list` (clients page via opaque cursors) |
| `opt_keys` | `MCPOptKeys` | `MCPOptKeys()` | Rename the `handler.opt` keys the plugin reads (e.g. to avoid collisions) |
| `session_store` | `Store \| None` | `None` | Litestar `Store` backing MCP sessions; defaults to an in-memory store |
| `session_max_idle_seconds` | `float` | `3600.0` | Idle timeout before an MCP session is evicted |
| `sse_max_streams` | `int` | `10000` | Max concurrent SSE streams |
| `sse_max_idle_seconds` | `float` | `3600.0` | Idle timeout for an SSE stream |

> Filters (`include_tags` / `exclude_tags` / `include_operations` / `exclude_operations`) gate what is **advertised** in `tools/list` / `resources/list` / `prompts/list`. As of `litestar-mcp` 0.7.0 they do **not** gate `tools/call` / `resources/read` ([cofin/litestar-mcp#62](https://github.com/cofin/litestar-mcp/issues/62)), so they are an advertisement filter, not an access boundary — use `guards` / auth to actually restrict invocation.

### Route Marking

```python
from litestar import get, post


@get("/products", mcp_resource="product_list")
async def list_products() -> list[dict]: ...


@post("/cart/items", mcp_tool="add_to_cart")
async def add_to_cart(data: CartItem) -> Cart: ...


@get(
    "/products/{product_id:int}",
    mcp_resource="product",
    mcp_resource_template="shop://products/{product_id}",
)
async def get_product(product_id: int) -> dict: ...


@get("/products/{product_id:int}/blurb", mcp_prompt="product_blurb")
async def product_blurb(product_id: int) -> str:
    """Write a short marketing blurb for a product."""
    ...
```

`mcp_resource_template` only takes effect alongside `mcp_resource` — the resource supplies the name the template binds to. A handler can expose more than one MCP role (a tool and a resource) at once; the description-override keys (`mcp_description` vs `mcp_resource_description`) are kind-specific so each surface can carry its own prose.

Register prompts not bound to a route with the `@mcp_prompt` decorator plus `LitestarMCP(prompts=[...])`:

```python
from litestar_mcp import LitestarMCP, mcp_prompt


@mcp_prompt("summarize", description="Summarize a document for the user.")
def summarize(text: str) -> str:
    return f"Summarize the following:\n\n{text}"


app = Litestar(plugins=[LitestarMCP(prompts=[summarize])])
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

### Hiding Routes

Discovery is opt-in: a handler that carries no `mcp_*` marker never appears in MCP. There is no per-route exclude flag — `opt={"mcp_exclude": True}` is ignored.

```python
@get("/internal/metrics")  # unmarked — never exposed to MCP clients
async def metrics() -> dict: ...
```

To drop *marked* routes from discovery in bulk, use the `MCPConfig` filters (`exclude_tags` / `exclude_operations`, or an `include_tags` / `include_operations` allowlist). Remember these gate advertisement only ([cofin/litestar-mcp#62](https://github.com/cofin/litestar-mcp/issues/62)) — enforce real access control with `guards` or auth.

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

List only the routes that should be callable by AI clients. Mark those routes with `mcp_tool=`, `mcp_resource=`, or `mcp_prompt=` (add `mcp_resource_template=` next to `mcp_resource=` for templated resources). There are no method-based defaults — unmarked routes are never exposed.

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
- **Default to allowlists for discovery** - `include_tags` / `include_operations` keep the advertised tool set small as route counts grow, but they only filter discovery — pair them with `guards` / auth, which actually gate invocation.
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
- [ ] Admin / internal routes are left unmarked, or kept outside `include_*` / inside `exclude_*` — with `guards` or auth enforcing access
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


@get("/internal/metrics")  # unmarked — stays out of MCP
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

- <https://cofin.github.io/litestar-mcp/>
- <https://github.com/cofin/litestar-mcp>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
