from importlib.metadata import version

from litestar_mcp import (
    MCPBlobResource,
    MCPConfig,
    MCPResourceLink,
    MCPStdioContext,
    MCPToolResult,
)


def test_litestar_mcp_0111_stdio_binary_and_schema_contract() -> None:
    assert version("litestar-mcp") == "0.11.1"
    config = MCPConfig()
    assert config.max_blob_bytes == 25 * 1024 * 1024
    assert config.include_in_schema is False
    assert all(symbol is not None for symbol in (MCPStdioContext, MCPResourceLink, MCPBlobResource, MCPToolResult))
