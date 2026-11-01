# Standalone MCP, Skills, A2A, Binary Resources, and Auth

## Standalone MCP App & Stdio Transports

Use `MCP(...)` when the application is primarily an MCP server. Use `LitestarMCP(...)` when adding MCP to an existing Litestar app.

```python
from litestar_mcp import MCP, MCPStdioContext

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
    stdio_context = MCPStdioContext(
        client_id="desktop-agent",
        owner_id="alice",
        auth={"sub": "alice", "role": "operator"},
        session={"tenant": "acme"},
        state={"deployment": "production"},
    )
    mcp.run(transport="stdio", stdio_context=stdio_context)
```

`mcp.app` lazily builds the underlying `Litestar` instance; access it after registering standalone decorators. `@mcp.tool`, `@mcp.resource`, and `@mcp.prompt` accept normal Litestar route-handler kwargs (`dependencies`, `guards`, `tags`, DTO options, hooks, `sync_to_thread`). The `name` kwarg names the MCP primitive; use `route_name` when the Litestar route handler itself needs a name.

### Stdio-to-Streamable-HTTP Bridge

Use the bridge when a local MCP client speaks stdio but the real server is an already-running Streamable HTTP endpoint (`httpx2` is included in the core `litestar-mcp` package):

```bash
litestar mcp bridge \
  --endpoint https://api.example.com/mcp \
  --bearer-env MCP_ACCESS_TOKEN

# Serve a Litestar application's MCP endpoint in-process over stdio:
litestar --app app.main:app mcp stdio
```

For programmatic embedding, import `run_stdio_streamable_http_bridge` from `litestar_mcp.mcp.bridge` (or `run_stdio` / `run_stdio_async` from `litestar_mcp.mcp.stdio`).

## Skills Over MCP (`MCPSkillsConfig`)

Configure `MCPConfig(skills=MCPSkillsConfig(...))` to serve `<path>/<name>/SKILL.md` directories over the `io.modelcontextprotocol/skills` extension:

```python
from pathlib import Path

from litestar import Litestar
from litestar_mcp import LitestarMCP, MCPConfig, MCPSkillsConfig

app = Litestar(
    plugins=[
        LitestarMCP(
            MCPConfig(
                name="Skills Server",
                skills=MCPSkillsConfig(
                    paths=[Path("skills")],
                    directory_read=True,
                    max_files_per_skill=512,
                    max_bytes_per_skill=16_777_216,
                ),
            )
        )
    ]
)
```

At startup, `SkillCatalog.from_config` (`litestar_mcp.mcp.skills`) scans immediate child directories of each configured path for a regular (non-symlink) `SKILL.md` file with valid YAML frontmatter whose `name` matches the folder name and declares a non-empty `description`. Every non-hidden regular file in the skill folder is indexed with a `skill://<name>/<relative_path>` URI, MIME type, byte size, and `sha256:<hex>` digest. `resources/read` verifies SHA-256 digests against the startup manifest (`SkillIntegrityError` on disk tampering).

## A2A 1.0 Integration (`LitestarA2A`)

Install `litestar-mcp[a2a]` to mount the official `a2a-sdk` JSON-RPC 1.0 handler on Litestar routes via `LitestarA2A` and `A2AConfig`:

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

## Binary Resources, Tool Results, and Multi-Round-Trip Inputs

Return `MCPResourceLink` from a tool when a stable resource URI can be fetched later. Return `MCPBlobResource` only when the binary must be embedded immediately. Return `MCPInputRequiredResult` when a tool or task requires additional information from the client before proceeding.

```python
from litestar import Response, get, post
from litestar_mcp import (
    MCPInputRequiredResult,
    MCPRequestContext,
    MCPResourceLink,
    get_mcp_request_context,
)


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

## Authentication (`litestar-security`)

`litestar-mcp` `0.14.0` removes `litestar_mcp.auth` and `MCPConfig.auth`. Delegate route authentication and RFC 9728 OAuth 2.1 protected-resource discovery to `litestar-security`:

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
