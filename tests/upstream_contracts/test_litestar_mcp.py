import asyncio
import inspect
from importlib.metadata import version
from typing import Annotated, Any, cast

from litestar import Controller, Litestar, get, post
from litestar.params import CookieParameter, HeaderParameter, PathParameter, QueryParameter
from litestar_mcp import (
    MCP,
    AfterToolCallHook,
    BeforeToolCallHook,
    BridgeConnectionError,
    BridgeMessageTooLargeError,
    DefaultJWKSCache,
    JWKSCache,
    LitestarMCP,
    LitestarMCPError,
    MCPAuthBackend,
    MCPAuthConfig,
    MCPBlobResource,
    MCPConfig,
    MCPController,
    MCPInputRequiredResult,
    MCPOptKeys,
    MCPRequestContext,
    MCPResourceLink,
    MCPStdioContext,
    MCPTaskConfig,
    MCPToolResult,
    MissingDependencyError,
    OIDCProviderConfig,
    TokenValidator,
    create_oidc_validator,
    get_mcp_request_context,
    mcp_prompt,
    mcp_resource,
    mcp_tool,
)
from litestar_mcp.bridge import run_stdio_streamable_http_bridge
from litestar_mcp.cli import mcp_group
from litestar_mcp.executor import execute_tool
from litestar_mcp.schema_builder import generate_schema_for_handler
from litestar_mcp.utils.handler_signature import (
    get_advertised_handler_parameters,
    parameter_aliases,
    resolve_tool_argument_aliases,
)


def test_litestar_mcp_0132_upstream_contract() -> None:
    """Verify litestar-mcp 0.13.2 public API surface, config defaults, signatures, and wire aliases."""
    assert version("litestar-mcp") == "0.13.2"

    config = MCPConfig()
    assert config.base_path == "/mcp"
    assert config.include_in_schema is False
    assert config.max_blob_bytes == 25 * 1024 * 1024
    assert config.cache_ttl_ms == 0
    assert config.cache_scope == "private"
    assert config.subscription_max_streams == 10000
    assert config.subscription_keepalive_seconds == 15.0
    assert config.list_page_size == 100
    assert config.route_opt is None
    assert config.register_oauth_protected_resource is True
    assert config.register_agent_card is True
    assert MCPOptKeys().tool == "mcp_tool"
    assert MCPOptKeys().resource == "mcp_resource"
    assert MCPOptKeys().prompt == "mcp_prompt"
    assert MCPOptKeys().for_field("description", "tool") == "mcp_description"
    assert MCPOptKeys().for_field("description", "resource") == "mcp_resource_description"
    assert MCPOptKeys().for_field("description", "prompt") == "mcp_prompt_description"

    exported_symbols = (
        LitestarMCP,
        MCP,
        AfterToolCallHook,
        BeforeToolCallHook,
        MCPConfig,
        MCPController,
        MCPOptKeys,
        MCPTaskConfig,
        MCPAuthConfig,
        MCPAuthBackend,
        OIDCProviderConfig,
        create_oidc_validator,
        TokenValidator,
        JWKSCache,
        DefaultJWKSCache,
        MCPBlobResource,
        MCPResourceLink,
        MCPToolResult,
        MCPInputRequiredResult,
        MCPRequestContext,
        MCPStdioContext,
        get_mcp_request_context,
        mcp_tool,
        mcp_resource,
        mcp_prompt,
        LitestarMCPError,
        MissingDependencyError,
        BridgeConnectionError,
        BridgeMessageTooLargeError,
        run_stdio_streamable_http_bridge,
    )
    assert all(symbol is not None for symbol in exported_symbols)

    tool_sig = inspect.signature(mcp_tool)
    expected_tool_params = {
        "name",
        "description",
        "agent_instructions",
        "when_to_use",
        "returns",
        "input_schema",
        "output_schema",
        "annotations",
        "scopes",
        "task_support",
        "task_input_before_start",
    }
    assert expected_tool_params.issubset(tool_sig.parameters.keys())

    resource_sig = inspect.signature(mcp_resource)
    expected_resource_params = {
        "name",
        "uri_template",
        "mime_type",
        "description",
        "agent_instructions",
        "when_to_use",
        "returns",
    }
    assert expected_resource_params.issubset(resource_sig.parameters.keys())

    prompt_sig = inspect.signature(mcp_prompt)
    expected_prompt_params = {"name", "title", "description", "arguments", "icons"}
    assert expected_prompt_params.issubset(prompt_sig.parameters.keys())

    mcp_init_sig = inspect.signature(MCP.__init__)
    expected_mcp_params = {"self", "name", "instructions", "config", "plugins", "route_handlers"}
    assert expected_mcp_params.issubset(mcp_init_sig.parameters.keys())

    commands = cast("dict[str, Any]", getattr(mcp_group, "commands", {}))
    assert "list-tools" in commands
    assert "list-resources" in commands
    assert "run" in commands
    assert "bridge" in commands

    @get("/items", mcp_tool="filter_items", sync_to_thread=False)
    def filter_items(
        category_name_in: Annotated[list[str] | None, QueryParameter(name="categoryNameIn")] = None,
        page_size: Annotated[int, QueryParameter(name="pageSize")] = 20,
        trace_id: Annotated[str | None, HeaderParameter(name="X-Trace-Id")] = None,
        session_cookie: Annotated[str | None, CookieParameter(name="sid")] = None,
    ) -> dict[str, Any]:
        return {
            "category_name_in": category_name_in,
            "page_size": page_size,
            "trace_id": trace_id,
            "session_cookie": session_cookie,
        }

    class NotesController(Controller):
        path = "/notes"

        @get("/{note_id:int}", mcp_tool="get_note", sync_to_thread=False)
        def get_note(self, note_id: Annotated[int, PathParameter()]) -> dict[str, int]:
            return {"id": note_id}

    @post("/optional-body", mcp_tool="optional_body", sync_to_thread=False)
    def optional_body(data: Any = "declared-default") -> dict[str, Any]:
        return {"received": data}

    plugin = LitestarMCP()
    app = Litestar(route_handlers=[filter_items, NotesController, optional_body], plugins=[plugin])
    plugin.on_startup(app)

    filter_handler = plugin.discovered_tools["filter_items"]
    schema = generate_schema_for_handler(filter_handler)
    assert "categoryNameIn" in schema["properties"]
    assert "pageSize" in schema["properties"]
    assert "category_name_in" not in schema["properties"]
    assert parameter_aliases(filter_handler) == {
        "categoryNameIn": "category_name_in",
        "pageSize": "page_size",
    }

    advertised = get_advertised_handler_parameters(filter_handler)
    resolved, consumed, legacy = resolve_tool_argument_aliases(
        {"category_name_in": ["legacy"], "categoryNameIn": ["wire"]},
        advertised,
    )
    assert resolved["categoryNameIn"] == ["wire"]
    assert {"category_name_in", "categoryNameIn"}.issubset(consumed)
    assert legacy == {"category_name_in": "categoryNameIn"}

    note_handler = plugin.discovered_tools["get_note"]
    assert asyncio.run(execute_tool(note_handler, app, {"note_id": 7}, request=None)) == {"id": 7}

    body_handler = plugin.discovered_tools["optional_body"]
    assert asyncio.run(execute_tool(body_handler, app, {}, request=None)) == {"received": "declared-default"}
    assert asyncio.run(execute_tool(body_handler, app, {"data": False}, request=None)) == {"received": False}
    assert asyncio.run(execute_tool(body_handler, app, {"data": {}}, request=None)) == {"received": {}}
