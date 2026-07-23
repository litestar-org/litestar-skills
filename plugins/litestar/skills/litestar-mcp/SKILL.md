---
name: litestar-mcp
description: "Auto-activate for litestar_mcp, LitestarMCP, MCP, MCPConfig, mcp.app, mcp.run(), @mcp.tool/resource/prompt, MCPAuthConfig, MCPAuthBackend, mcp_tool=, mcp_resource=, Streamable HTTP, stdio, or OIDC MCP endpoints. Not for non-Litestar MCP."
---

# litestar-mcp

`litestar-mcp` exposes explicitly marked Litestar route handlers as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, resources, and prompts over MCP Streamable HTTP and JSON-RPC 2.0.

Mark routes by passing `mcp_tool="name"`, `mcp_resource="name"`, or `mcp_prompt="name"` directly to the Litestar route decorator — Litestar funnels unknown kwargs into `handler.opt`, so no `opt={...}` wrapper is needed. The `@mcp_tool` / `@mcp_resource` / `@mcp_prompt` decorators (importable from `litestar_mcp`) still exist and are worth reaching for when you need the extra fields they expose — `output_schema`, `annotations`, `scopes`, `task_support`, prompt `title`, `arguments`, and `icons`. Route opt keys mirror those names (`mcp_prompt_title`, `mcp_prompt_arguments`, `mcp_prompt_icons`). There is no `opt={"mcp_tool_name": ...}` form and no `mcp_exclude` key; neither is read. To hide a route, simply leave it unmarked (discovery is opt-in).

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O. Pure standalone `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` functions may be sync; keep blocking I/O out of the event loop.

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
| `include_in_schema` | `bool` | `False` | Include the MCP router and all three `/.well-known/*` discovery routes in OpenAPI |
| `name` | `str \| None` | `None` | Server name; defaults to OpenAPI title |
| `instructions` | `str \| None` | `None` | Server instructions advertised to MCP clients |
| `guards` | `list[Any] \| None` | `None` | Litestar guards applied to the MCP router |
| `allowed_origins` | `list[str] \| None` | `None` | Restrict accepted `Origin` headers |
| `include_operations` | `list[str] \| None` | `None` | Only expose matching operation names |
| `exclude_operations` | `list[str] \| None` | `None` | Exclude matching operation names |
| `include_tags` | `list[str] \| None` | `None` | Only expose routes with matching OpenAPI tags |
| `exclude_tags` | `list[str] \| None` | `None` | Exclude routes with matching OpenAPI tags |
| `auth` | `MCPAuthConfig \| None` | `None` | OAuth protected-resource metadata |
| `tasks` | `bool \| MCPTaskConfig` | `False` | Enable experimental in-memory MCP task support |
| `list_page_size` | `int` | `100` | Page size for `tools/list`, `resources/list`, `resources/templates/list`, `prompts/list` (clients page via opaque cursors) |
| `before_tool_call` | `BeforeToolCallHook \| None` | `None` | Observe each `tools/call` before dispatch |
| `after_tool_call` | `AfterToolCallHook \| None` | `None` | Observe each `tools/call` result, exception, and duration |
| `max_blob_bytes` | `int \| None` | `25 * 1024 * 1024` | Maximum raw byte length for base64-embedded blobs; `None` disables the cap |
| `opt_keys` | `MCPOptKeys` | `MCPOptKeys()` | Rename the `handler.opt` keys the plugin reads (e.g. to avoid collisions) |
| `session_store` | `Store \| None` | `None` | Litestar `Store` backing MCP sessions; defaults to an in-memory store |
| `session_max_idle_seconds` | `float` | `3600.0` | Idle timeout before an MCP session is evicted |
| `sse_max_streams` | `int` | `10000` | Max concurrent SSE streams |
| `sse_max_idle_seconds` | `float` | `3600.0` | Idle timeout for an SSE stream |

> Filters (`include_tags` / `exclude_tags` / `include_operations` / `exclude_operations`) gate both list responses and direct invocation. A filtered tool/resource/template behaves like an unknown name or URI in `tools/call` / `resources/read`; still use `guards` / auth for real access control.

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

### Standalone MCP App

Use `MCP(...)` when the application is primarily an MCP server. Use `LitestarMCP(...)` when adding MCP to an existing Litestar app.

```python
from litestar_mcp import MCP


mcp = MCP("inventory-mcp", instructions="Expose inventory tools.")


@mcp.tool(name="lookup_product", description="Look up a product by SKU.")
def lookup_product(sku: str) -> dict[str, str]:
    return {"sku": sku, "status": "active"}


@mcp.resource(uri="inventory://status", name="inventory_status")
def inventory_status() -> dict[str, str]:
    return {"status": "healthy"}


@mcp.prompt(name="summarize_product")
def summarize_product(sku: str) -> str:
    return f"Summarize product {sku}."


app = mcp.app


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

`mcp.app` lazily builds the underlying `Litestar` instance; access it after registering standalone decorators. `@mcp.tool`, `@mcp.resource`, and `@mcp.prompt` accept normal Litestar route-handler kwargs such as `dependencies`, `guards`, `tags`, DTO options, hooks, and `sync_to_thread`. The `name` kwarg names the MCP primitive; use `route_name` when the Litestar route handler itself needs a name.

`MCP(...)` also accepts `config=`, existing `plugins=`, existing `route_handlers=`, and standard `Litestar(...)` app kwargs. Use that pass-through when a standalone MCP app still needs Litestar middleware, dependencies, CORS, or additional non-MCP routes.

`mcp.run(transport="sse", port=8000)` starts the HTTP/SSE transport through the Litestar CLI, so expose `app = mcp.app` at module scope or set `LITESTAR_APP` for worker/reload discovery. `mcp.run(transport="stdio")` reads line-delimited JSON-RPC from stdin, writes responses to stdout, manually drives ASGI lifespan, and dispatches through the same JSON-RPC router with a synthetic request context.

#### Direct stdio identity

Stdio has no HTTP headers or authentication middleware. Resolve credentials in the host process and inject the resulting identity with the public `MCPStdioContext`:

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

Do not send credentials as invented JSON-RPC headers. Stdio identity is an out-of-band host concern; `MCPStdioContext` carries the already-resolved principal.

#### Stdio-to-Streamable-HTTP bridge

Use the bridge when a local MCP client speaks stdio but the real server is an already-running Streamable HTTP endpoint:

```bash
pip install "litestar-mcp[bridge]"
litestar mcp bridge \
  --endpoint https://api.example.com/mcp \
  --bearer-env MCP_ACCESS_TOKEN
```

The bridge forwards newline-delimited JSON-RPC, preserves the MCP session id and negotiated protocol version, and starts the optional GET SSE stream after `notifications/initialized`. A server that answers GET with `404` or `405` remains usable through POST responses. Stdout contains JSON-RPC only; transport diagnostics go to stderr.

Use `--header "Name: value"` for static headers. Use exactly one of `--bearer-env` or `--bearer-cmd` for a token resolved per request; the bridge retries once with a fresh token after `401`. Match identity-proxy schemes with `--header-name` and `--token-prefix`. `--discover` resolves `endpoints.mcp` from `/.well-known/mcp-server.json`.

For embedding, import `run_stdio_streamable_http_bridge` from `litestar_mcp.bridge`. It accepts injectable AnyIO stdin/stdout streams and a sync or async token provider, then returns process-style status `0` for clean EOF and `1` after emitting a bridge JSON-RPC error.

The default stdin frame limit is 16 MiB. Set `--max-message-size`; use `-1` to disable that limit. This is separate from `MCPConfig.max_blob_bytes`, which limits decoded binary payloads produced by the server.

### Binary Resources And Tool Results

Return `MCPResourceLink` from a tool when a stable resource URI can be fetched later. Return `MCPBlobResource` only when the binary must be embedded immediately. Use `MCPToolResult` when one result needs mixed content blocks, `structuredContent`, `isError`, or `_meta`.

```python
from litestar import Response, get
from litestar_mcp import MCPResourceLink


@get("/reports/latest-link", mcp_tool="generate_report")
async def generate_report() -> MCPResourceLink:
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
    return Response(content=b"%PDF", media_type="application/pdf")
```

This produces a `resource_link` block from `tools/call`; `resources/read` returns the response bytes as a base64 `blob`. `MCPBlobResource(uri=..., data=..., mime_type=...)` produces an embedded `resource` block directly in a tool result. The plugin enforces `max_blob_bytes` before base64 encoding for helper objects, explicit resource blocks, and `resources/read`. An oversized tool payload becomes a tool result with `isError: true`; an oversized resource becomes a `Resource read failed` JSON-RPC error.

Set resource MIME metadata with `mcp_resource_mime_type=` on a Litestar route, `mime_type=` on `@mcp_resource`, or `mime_type=` on `@mcp.resource`. The handler response `Content-Type` wins during `resources/read`; configured metadata is the fallback and the value advertised by resource listings. The default is `application/json`.

Textual MIME types return `text`: `text/*`, JSON, XML, JavaScript, and YAML types are textual. Other MIME types return base64 `blob`; invalid UTF-8 under an otherwise textual MIME type also falls back to `blob`. Always return the real media type—do not label binary bytes as JSON to avoid blob handling.

### Hiding Routes

Discovery is opt-in: a handler that carries no `mcp_*` marker never appears in MCP. There is no per-route exclude flag — `opt={"mcp_exclude": True}` is ignored.

```python
@get("/internal/metrics")  # unmarked — never exposed to MCP clients
async def metrics() -> dict: ...
```

To drop *marked* routes in bulk, use the `MCPConfig` filters (`exclude_tags` / `exclude_operations`, or an `include_tags` / `include_operations` allowlist). Filtered tools/resources/templates are absent from list responses and fail direct calls as unknown; enforce real access control with `guards` or auth.

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

Direct router use is transport-internal. Current `JSONRPCRouter.dispatch()` takes a parsed request plus `RequestContext`; HTTP builds that context from the live `Request`, while stdio uses `client_id="stdio"`, `owner_id="stdio"`, and `request=None`. Do not import `litestar_mcp.routes.build_jsonrpc_router`; use `LitestarMCP` or `MCP` unless you are maintaining `litestar-mcp` transport internals.

### Pagination, Signatures, And Errors

`tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` use opaque cursor pagination. Clients pass `params.cursor` from `nextCursor` until the response omits it; clients do not send `limit`. Set server page size with `MCPConfig(list_page_size=...)`; invalid cursors return `INVALID_PARAMS` (`-32602`).

Tool arguments are validated against Litestar's `handler.parsed_fn_signature` before dispatch. Do not reference legacy `signature_model` or private validation-context parameter lists.

Tool execution errors stay inside the tool result with `isError: true`; protocol errors such as unknown tool names use JSON-RPC errors. Resource and prompt handler failures use primitive-level JSON-RPC codes and preserve the handler HTTP status in `error.data.statusCode` when a handler response produced one. Do not invent status-code-specific JSON-RPC codes for 401/403/409/429.

### Tool-Call Callbacks

Use `MCPConfig.before_tool_call` and `MCPConfig.after_tool_call` for audit, metrics, or tracing that must fire around `tools/call` regardless of route ownership. Both callbacks receive the MCP tool name, a shallow copy of submitted arguments, and the synthesized `Request`. `after_tool_call` also receives keyword-only `result`, `exception`, and `duration`; it fires for successes, guard failures, handled error responses, and unhandled exceptions. Callback exceptions are logged and swallowed.

### Dependency Providers And Dishka

Litestar `Provide(...)` factory parameters that are user inputs, such as pagination or filter values, remain in tool schemas and forward during `tools/call`. When `dishka.integrations.litestar.setup_dishka()` is attached, provider-factory parameters whose annotated type is resolvable from `app.state.dishka_container` are treated as DI inputs instead of MCP arguments. Dishka remains optional; installs without Dishka should still import and run `litestar_mcp`.

### Built-in OpenAPI Resource

`LitestarMCP` exposes the app OpenAPI schema as:

- URI: `litestar://openapi`
- MIME type: `application/json`
- Method: `resources/read`

This resource is always present in `resources/list`; `MCPConfig.include_in_schema` does not remove it.

`include_in_schema=False` is the default. It hides the plugin-owned `/mcp` path and all three `/.well-known/*` discovery paths from generated OpenAPI, while ordinary application routes—including routes marked for MCP—keep their own OpenAPI visibility. It does not disable the MCP or discovery endpoints at runtime.

Set `include_in_schema=True` to include all plugin-owned paths in OpenAPI:

- `/mcp`
- `/.well-known/oauth-protected-resource`
- `/.well-known/agent-card.json`
- `/.well-known/mcp-server.json`

Do not use this setting to hide an application route. Set `include_in_schema=False` on that route separately, and leave it unmarked if it must also stay out of MCP.

### Auth

Authentication is a Litestar middleware concern. Apps with existing auth middleware get `request.user` / `request.auth` before tool handlers run.

The supported auth paths are:

- Bring your own Litestar auth middleware; MCP routes inherit it.
- Use `MCPAuthBackend` with `OIDCProviderConfig`.
- Build a validator with `create_oidc_validator()` and pass shared JWKS behavior through `JWKSCache` when your app already manages discovery/cache lifetimes.

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

For an identity proxy that supplies a raw token in a custom header, configure the backend explicitly:

```python
from litestar.middleware import DefineMiddleware
from litestar_mcp import MCPAuthBackend, OIDCProviderConfig


DefineMiddleware(
    MCPAuthBackend,
    providers=[
        OIDCProviderConfig(
            issuer="https://cloud.google.com/iap",
            audience="/projects/123/global/backendServices/456",
        )
    ],
    header_name="X-Goog-IAP-JWT-Assertion",
    token_prefix="",
)
```

`header_name` is case-insensitive when read. `token_prefix=""` validates the entire non-empty header value; a non-empty prefix must match exactly and is stripped before validation. Match the bridge’s `--header-name` and `--token-prefix` when it connects through the same proxy.

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-mcp
```

### Step 2: Decide What to Expose

List only the routes that should be callable by AI clients. Mark those routes with `mcp_tool=`, `mcp_resource=`, or `mcp_prompt=` (add `mcp_resource_template=` next to `mcp_resource=` for templated resources). There are no method-based defaults — unmarked routes are never exposed.

### Step 3: Add the Plugin

Wire `LitestarMCP(MCPConfig(name=...))` into `Litestar(plugins=[...])`, or use standalone `MCP(...)` when the app exists only to serve MCP primitives. Use `include_tags` or `include_operations` when you need a second allowlist.

### Step 4: Add Auth

For public endpoints, configure bearer-token validation and `MCPAuthConfig` metadata. For internal deployments, use `guards=[...]` or existing app auth middleware.

### Step 5: Verify

For Streamable HTTP, initialize first: `POST /mcp` with `initialize`, send `notifications/initialized`, then include the returned `Mcp-Session-Id` header on later `tools/list`, `resources/list`, `tools/call`, and `resources/read` requests. Confirm only marked routes appear, call one representative tool, and read one representative resource. Verify both the `text` and `blob` resource paths when the app exposes binary data. For standalone stdio apps, send one line-delimited JSON-RPC request through stdin and confirm the response is written to stdout. For a bridge deployment, verify stdout purity, session continuity, and the configured auth refresh path.

</workflow>

<guardrails>

## Guardrails

- **Mark routes explicitly** - unmarked routes should not appear in MCP clients.
- **Default to allowlists** - `include_tags` / `include_operations` keep the tool set small and also gate direct invocation; pair them with `guards` / auth for authorization.
- **Never expose admin or destructive routes by default** - require a human-confirmation workflow before any irreversible operation.
- **Prefer resources for read-only reference data** - agents may read resources speculatively.
- **Keep DTOs precise** - loose `dict[str, Any]` request schemas produce weak tool contracts.
- **Use `MCPAuthConfig` plus token validation for public MCP** - metadata alone does not authenticate requests.
- **Set `allowed_origins` for browser-accessible MCP clients** - leave it `None` only for trusted server-to-server deployments.
- **Prefer `MCPResourceLink` over inline blobs** - linked resources avoid base64 expansion and let the application enforce authorization when the client reads the resource.
- **Keep `max_blob_bytes` bounded** - base64 embedding increases memory and wire size; disable the cap only behind a stricter application-owned limit.
- **Resolve stdio credentials out of band** - inject the verified principal with `MCPStdioContext`; JSON-RPC messages are not an authentication channel.
- **Treat `MCP` and `LitestarMCP` as public entry points** - avoid private router/service imports unless you are maintaining `litestar-mcp` transport internals.
- **Keep observability callbacks side-effect safe** - `before_tool_call` / `after_tool_call` failures are swallowed, so callbacks must not enforce authorization or business invariants.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering an MCP integration, verify:

- [ ] Existing Litestar apps include `LitestarMCP` in `app.plugins`; standalone apps expose `app = mcp.app`
- [ ] Exposed routes/functions use `mcp_tool=`, `mcp_resource=`, `mcp_prompt=`, `@mcp.tool`, `@mcp.resource`, or `@mcp.prompt`
- [ ] Admin / internal routes are left unmarked, or kept outside `include_*` / inside `exclude_*` — with `guards` or auth enforcing access
- [ ] Auth is configured for the deployment boundary
- [ ] `POST /mcp` `tools/list` returns only intended tools
- [ ] `POST /mcp` `resources/list` includes only intended resources plus `litestar://openapi`
- [ ] Filtered tools/resources/templates fail direct invocation as unknown
- [ ] Provider-declared user inputs appear in tool `inputSchema`; Dishka-resolved service parameters do not
- [ ] `before_tool_call` / `after_tool_call` callbacks are covered when configured, including failure paths
- [ ] Standalone `MCP` SSE or stdio transport is smoke-tested for the chosen deployment mode
- [ ] Direct stdio handlers and guards receive the intended `MCPStdioContext`; task ownership resolves to the intended principal
- [ ] Stdio bridge stdout contains JSON-RPC only; static/dynamic auth, session continuity, SSE fallback, and frame limits match the deployment
- [ ] Binary resource listings advertise the correct MIME type; reads return `text` or base64 `blob` as intended
- [ ] `max_blob_bytes` accepts the largest intended payload and rejects an oversized tool result and resource read
- [ ] OpenAPI contains ordinary application routes and hides plugin-owned paths by default; `include_in_schema=True` exposes all four plugin-owned paths when requested
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

- Use this skill for route marking, Streamable HTTP and stdio behavior, binary content, MCP auth metadata, and verification requests.
- Use [litestar-auth-guards](../litestar-auth-guards/SKILL.md) when auth logic lives in normal Litestar guards or middleware.

## Official References

- <https://github.com/cofin/litestar-mcp/tree/v0.11.1> — audited v0.11.1 source and tests
- <https://cofin.github.io/litestar-mcp/>
- <https://github.com/cofin/litestar-mcp>
- <https://modelcontextprotocol.io/>
- <https://spec.modelcontextprotocol.io/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
