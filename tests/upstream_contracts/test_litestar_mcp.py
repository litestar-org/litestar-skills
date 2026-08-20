import inspect
from importlib.metadata import version
from typing import Any, cast

from litestar_mcp import (
    MCP,
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


def test_litestar_mcp_0130_upstream_contract() -> None:
    """Verify litestar-mcp 0.13.0 public API surface, config defaults, and signatures."""
    assert version("litestar-mcp") == "0.13.0"

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
        MCPConfig,
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

    commands = cast("dict[str, Any]", getattr(mcp_group, "commands"))  # noqa: B009
    assert "list-tools" in commands
    assert "list-resources" in commands
    assert "run" in commands
    assert "bridge" in commands
