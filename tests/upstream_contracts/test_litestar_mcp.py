import asyncio
import inspect
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, cast

from litestar import Controller, Litestar, get, post
from litestar.params import CookieParameter, HeaderParameter, PathParameter, QueryParameter
from litestar_mcp import (
    MCP,
    A2AConfig,
    AfterToolCallHook,
    BeforeToolCallHook,
    BridgeConnectionError,
    BridgeMessageTooLargeError,
    LitestarA2A,
    LitestarMCP,
    LitestarMCPError,
    MCPBlobResource,
    MCPConfig,
    MCPController,
    MCPInputRequiredResult,
    MCPOptKeys,
    MCPRequestContext,
    MCPResourceLink,
    MCPSkillsConfig,
    MCPStdioContext,
    MCPTaskConfig,
    MCPToolResult,
    MissingDependencyError,
    get_mcp_request_context,
    mcp_prompt,
    mcp_resource,
    mcp_tool,
)
from litestar_mcp.a2a import A2AConfig as A2AModuleConfig
from litestar_mcp.a2a import LitestarA2A as LitestarModuleA2A
from litestar_mcp.core.schema_builder import generate_schema_for_handler
from litestar_mcp.mcp.bridge import run_stdio_streamable_http_bridge
from litestar_mcp.mcp.cli import mcp_group
from litestar_mcp.mcp.executor import execute_tool
from litestar_mcp.mcp.registry import ResourceTemplate
from litestar_mcp.mcp.skills import (
    SKILL_FILE_NAME,
    SKILL_URI_PREFIX,
    Skill,
    SkillCatalog,
    SkillFile,
    SkillIntegrityError,
)
from litestar_mcp.utils.handler_signature import (
    get_advertised_handler_parameters,
    parameter_aliases,
    resolve_tool_argument_aliases,
)
from litestar_security import required
from litestar_security.authentication import AUTH_POLICY_OPT_KEY


def test_litestar_mcp_0140_upstream_contract() -> None:
    """Verify litestar-mcp 0.14.0 public API surface, config defaults, skills, A2A, signatures, and wire aliases."""
    assert version("litestar-mcp") == "0.14.0"

    config = MCPConfig()
    assert config.base_path == "/mcp"
    assert config.include_in_schema is False
    assert config.max_blob_bytes == 25 * 1024 * 1024
    assert config.cache_ttl_ms == 0
    assert config.cache_scope == "private"
    assert config.subscription_max_streams == 10000
    assert config.subscription_keepalive_seconds == 15.0
    assert config.stream_queue_capacity == 256
    assert config.stream_cleanup_timeout == 5.0
    assert config.list_page_size == 100
    assert config.route_opt is None
    assert config.skills is None
    assert not hasattr(config, "auth")
    assert not hasattr(config, "register_oauth_protected_resource")
    assert not hasattr(config, "register_agent_card")

    secured_config = MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required("api-key")})
    assert secured_config.route_opt is not None
    assert AUTH_POLICY_OPT_KEY in secured_config.route_opt

    skills_config = MCPSkillsConfig(paths=[Path("skills")])
    assert skills_config.directory_read is True
    assert skills_config.max_files_per_skill == 512
    assert skills_config.max_bytes_per_skill == 16_777_216
    assert SKILL_URI_PREFIX == "skill://"
    assert SKILL_FILE_NAME == "SKILL.md"
    catalog = SkillCatalog.from_config(skills_config)
    assert catalog.get("skill://litestar-mcp/SKILL.md") is not None
    assert catalog.list_directory("skill://litestar-mcp") is not None

    a2a_config = A2AConfig()
    assert a2a_config.path == "/a2a"
    assert a2a_config.agent_card_path == "/.well-known/agent-card.json"
    assert cast("Any", a2a_config).guards == ()
    assert a2a_config.route_opt == {}
    assert a2a_config.context_builder is None
    assert a2a_config.include_in_schema is False
    assert a2a_config.agent_card_max_age == 300
    assert a2a_config.stream_cleanup_timeout == 5.0
    assert A2AConfig is A2AModuleConfig
    assert LitestarA2A is LitestarModuleA2A

    assert MCPOptKeys().tool == "mcp_tool"
    assert MCPOptKeys().resource == "mcp_resource"
    assert MCPOptKeys().prompt == "mcp_prompt"
    assert MCPOptKeys().for_field("description", "tool") == "mcp_description"
    assert MCPOptKeys().for_field("description", "resource") == "mcp_resource_description"
    assert MCPOptKeys().for_field("description", "prompt") == "mcp_prompt_description"

    exported_symbols = (
        LitestarMCP,
        LitestarA2A,
        MCP,
        A2AConfig,
        AfterToolCallHook,
        BeforeToolCallHook,
        MCPConfig,
        MCPController,
        MCPOptKeys,
        MCPSkillsConfig,
        MCPTaskConfig,
        MCPBlobResource,
        MCPResourceLink,
        MCPToolResult,
        MCPInputRequiredResult,
        MCPRequestContext,
        MCPStdioContext,
        ResourceTemplate,
        Skill,
        SkillCatalog,
        SkillFile,
        SkillIntegrityError,
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

    progress_sig = inspect.signature(MCPRequestContext.report_progress)
    assert {"self", "progress", "total", "message"}.issubset(progress_sig.parameters.keys())

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
    assert "stdio" in commands

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
