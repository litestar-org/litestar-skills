"""Upstream contract tests for litestar-mcp 0.16.0."""

import asyncio
import inspect
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, cast

from litestar import Controller, Litestar, Router, get, post
from litestar.di import Provide
from litestar.params import CookieParameter, HeaderParameter, PathParameter, QueryParameter
from litestar.testing import RequestFactory
from litestar_mcp import (
    MCP,
    A2AConfig,
    AfterToolCallHook,
    BeforeToolCallHook,
    BridgeConnectionError,
    BridgeMessageTooLargeError,
    FilesystemSkillSource,
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
    PromptController,
    PromptMessage,
    Skill,
    SkillController,
    SkillFile,
    SkillIntegrityError,
    SkillSource,
    Tool,
    agent,
    get_mcp_request_context,
    mcp_prompt,
    mcp_resource,
    mcp_tool,
    prompt,
    tool,
)
from litestar_mcp.a2a import A2AConfig as A2AModuleConfig
from litestar_mcp.a2a import LitestarA2A as LitestarModuleA2A
from litestar_mcp.agent import (
    Agent,
    AgentChatController,
    AgentGroup,
    AgentRuntime,
    DynamicWorkflow,
    GoogleGenAIClient,
    MockModelClient,
    ModelDelta,
    TurnBudget,
    TurnRequest,
    WorkflowContext,
    WorkflowEngine,
    agent_to_a2a,
    agent_to_mcp,
    discover_mcp_tools,
    mcp_to_tools,
)
from litestar_mcp.agent.sessions import LitestarStoreSessionStore, MemorySessionStore
from litestar_mcp.agent.spec import TRANSFER_TOOL_NAME
from litestar_mcp.core.context import ToolContext
from litestar_mcp.core.observability import (
    GEN_AI_AGENT_NAME,
    GEN_AI_REQUEST_MODEL,
    LITESTAR_MCP_AGENT_GROUP,
    LITESTAR_MCP_TURN_ID,
    SpanManager,
    TelemetryConfig,
)
from litestar_mcp.core.schema_builder import generate_schema_for_handler
from litestar_mcp.mcp import skills as skills_module
from litestar_mcp.mcp.bridge import run_stdio_streamable_http_bridge
from litestar_mcp.mcp.cli import mcp_group
from litestar_mcp.mcp.client import MCPStreamableHTTPClient, mcp_request_headers, prepare_mcp_request
from litestar_mcp.mcp.executor import execute_tool
from litestar_mcp.mcp.registry import ResourceTemplate
from litestar_mcp.mcp.skills import SKILL_URI_PREFIX, SkillCatalog
from litestar_mcp.queues import (
    AgentRegistry,
    PrincipalSnapshot,
    QueuedAgentChatController,
    QueuedTurn,
    QueuedTurnManager,
    agent_turn_channel,
)
from litestar_mcp.utils.handler_signature import (
    get_advertised_handler_parameters,
    parameter_aliases,
    resolve_tool_argument_aliases,
)
from litestar_security import required
from litestar_security.authentication import AUTH_POLICY_OPT_KEY


class _InMemorySkillSource:
    """Async request-aware skill source used for contract verification."""

    def __init__(self, skills: Sequence[Skill]) -> None:
        self._by_name = {skill.name: skill for skill in skills}

    async def list_skills(self, request: Any, /) -> Sequence[Skill]:
        _ = request
        return tuple(self._by_name.values())

    async def get_skill(self, request: Any, name: str, /) -> Skill | None:
        _ = request
        return self._by_name.get(name)

    async def read_file(self, request: Any, skill: Skill, file: SkillFile, /) -> bytes:
        _ = (request, skill)
        return file.content or b""


class _CustomInjectMarker:
    """Custom injection marker exercising generic DI marker resolution."""

    __inject_marker__ = True


def test_litestar_mcp_0160_upstream_contract() -> None:
    """Verify litestar-mcp 0.16.0 public API surface, config defaults, skills, A2A, signatures, and wire aliases."""
    assert version("litestar-mcp") == "0.16.0"
    assert version("a2a-sdk") == "1.2.1"

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
    assert config.prompt_controllers == ()
    assert config.skill_controllers == ()
    assert not hasattr(config, "auth")
    assert not hasattr(config, "register_oauth_protected_resource")
    assert not hasattr(config, "register_agent_card")

    secured_config = MCPConfig(route_opt={AUTH_POLICY_OPT_KEY: required("api-key")})
    assert secured_config.route_opt is not None
    assert AUTH_POLICY_OPT_KEY in secured_config.route_opt

    assert SKILL_URI_PREFIX == "skill://"
    assert not hasattr(skills_module, "SKILL_FILE_NAME")

    fs_source = FilesystemSkillSource([Path("skills")])
    assert isinstance(fs_source, SkillSource)
    assert any(s.name == "litestar-mcp" for s in fs_source.skills)

    built_skill = Skill.build(
        "dynamic-playbook",
        "Dynamic operational playbook.",
        "# Playbook\nFollow the checklist.\n",
        files={"references/guide.md": "Step 1: Verify."},
    )
    assert built_skill.uri == "skill://dynamic-playbook/SKILL.md"
    assert any(f.relative_path == "references/guide.md" for f in built_skill.files)
    inline_file = SkillFile.from_content("dynamic-playbook", "notes.txt", "hello")
    assert inline_file.uri == "skill://dynamic-playbook/notes.txt"
    assert inline_file.size == 5

    mem_source = _InMemorySkillSource([built_skill])
    assert isinstance(mem_source, SkillSource)

    skills_config = MCPSkillsConfig(paths=[Path("skills")], sources=[mem_source])
    assert skills_config.directory_read is True
    assert skills_config.max_files_per_skill == 512
    assert skills_config.max_bytes_per_skill == 16_777_216
    assert len(skills_config.sources) == 1

    catalog = SkillCatalog.from_config(skills_config)
    dummy_request = RequestFactory().get("/")

    async def _verify_catalog() -> None:
        mcp_skill = await catalog.get(dummy_request, "skill://litestar-mcp/SKILL.md")
        assert mcp_skill is not None
        dyn_skill = await catalog.get(dummy_request, "skill://dynamic-playbook/SKILL.md")
        assert dyn_skill is not None
        listing = await catalog.list_directory(dummy_request, "skill://litestar-mcp")
        assert listing is not None
        file_match = await catalog.get_file(dummy_request, "skill://dynamic-playbook/references/guide.md")
        assert file_match is not None
        raw = await catalog.read_file(dummy_request, file_match)
        assert raw == b"Step 1: Verify."

    asyncio.run(_verify_catalog())

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
        FilesystemSkillSource,
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
        PromptController,
        PromptMessage,
        ResourceTemplate,
        Skill,
        SkillCatalog,
        SkillController,
        SkillFile,
        SkillIntegrityError,
        SkillSource,
        Tool,
        agent,
        get_mcp_request_context,
        mcp_tool,
        mcp_resource,
        mcp_prompt,
        prompt,
        tool,
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

    mcp_run_sig = inspect.signature(MCP.run)
    assert mcp_run_sig.parameters["transport"].default == "streamable-http"

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


def test_litestar_mcp_0160_controllers_universal_di_and_reserved_kwargs() -> None:
    """Verify SkillController, PromptController, universal DI, router discovery, and RESERVED_KWARGS aliasing."""

    async def provide_prefix() -> str:
        return "ord"

    class OrdersSkillController(SkillController):
        name = "orders"
        description = "Order lookup and summarization skill."
        instructions = "Always validate order IDs before mutating state."
        tags = ("commerce", "orders")
        examples = ("Search orders matching 'widget'",)
        dependencies = {"prefix": Provide(provide_prefix)}

        async def _search_orders(self, query: str, prefix: str) -> dict[str, str]:
            return {"matched": f"{prefix}:{query}"}

        search_orders = tool(name="search_orders", description="Search orders by query string.")(_search_orders)

        @prompt(description="Draft a customer order summary.")
        async def summarize_order(self, order_id: str) -> list[PromptMessage]:
            return [
                PromptMessage.user(f"Summarize order {order_id}"),
                PromptMessage.assistant(f"Order {order_id} summary ready."),
            ]

    controller_instance = OrdersSkillController()
    assert controller_instance.qualify_prompt_name("summarize_order") == "orders/summarize_order"
    assert controller_instance.get_instructions() == "Always validate order IDs before mutating state."
    controller_tools = controller_instance.get_tools()
    assert len(controller_tools) == 1
    assert controller_tools[0].name == "search_orders"
    assert "query" in controller_tools[0].input_schema["properties"]
    assert "prefix" not in controller_tools[0].input_schema["properties"]

    agent_skill = controller_instance.to_agent_skill()
    assert agent_skill["id"] == "orders"
    assert agent_skill["tags"] == ["commerce", "orders"]

    nested_router = Router(path="/v1", route_handlers=[OrdersSkillController])
    plugin = LitestarMCP()
    app = Litestar(route_handlers=[nested_router], plugins=[plugin])
    plugin.on_startup(app)

    assert "search_orders" in plugin.discovered_tools
    assert "orders/summarize_order" in plugin.discovered_prompts
    search_handler = plugin.discovered_tools["search_orders"]
    assert "_mcp_param_query" in inspect.signature(search_handler.fn).parameters
    assert asyncio.run(execute_tool(search_handler, app, {"query": "widget"}, request=None)) == {
        "matched": "ord:widget"
    }

    class _TenantService:
        def __init__(self, tenant: str) -> None:
            self.tenant = tenant

    async def _inspect_tenant(
        resource_id: str,
        svc: Annotated[_TenantService, _CustomInjectMarker()],
    ) -> dict[str, str]:
        return {"tenant": svc.tenant, "resource_id": resource_id}

    inspect_tenant: Tool = tool(name="inspect_tenant", description="Inspect tenant context.")(_inspect_tenant)

    assert "resource_id" in inspect_tenant.input_schema["properties"]
    assert "svc" not in inspect_tenant.input_schema["properties"]

    ctx = ToolContext(
        dependency_resolver=lambda _name, annotation, _ctx: (
            _TenantService("acme") if annotation is _TenantService else None
        )
    )
    assert asyncio.run(inspect_tenant.execute({"resource_id": "r-1"}, context=ctx)) == {
        "tenant": "acme",
        "resource_id": "r-1",
    }


def test_litestar_mcp_0160_agent_runtime_workflow_and_bridges() -> None:
    """Verify Agent, AgentGroup, AgentRuntime, GoogleGenAIClient defaults, DynamicWorkflow, and MCP/A2A bridges."""
    genai_sig = inspect.signature(GoogleGenAIClient.__init__)
    assert genai_sig.parameters["model"].default == "gemini-3.8-flash"
    assert "http_client" in genai_sig.parameters

    async def _fetch_order_status(order_id: str) -> dict[str, str]:
        return {"order_id": order_id, "status": "shipped"}

    fetch_order_status: Tool = tool(name="fetch_order_status", description="Fetch order status.")(_fetch_order_status)

    class BillingSkill(SkillController):
        name = "billing"
        description = "Billing operations."
        tags = ("finance",)

        async def _refund_invoice(self, invoice_id: str) -> dict[str, str]:
            return {"invoice_id": invoice_id, "refunded": "true"}

        refund_invoice = tool(name="refund_invoice", description="Refund invoice.")(_refund_invoice)

    specialist = Agent(
        name="billing_specialist",
        description="Handles billing inquiries.",
        instructions="Resolve billing questions.",
        tools=(fetch_order_status,),
        skills=(BillingSkill,),
    )
    coordinator = Agent(
        name="triage_coordinator",
        description="Routes requests to specialists.",
        instructions="Delegate billing questions to billing_specialist.",
    )
    group = AgentGroup(coordinator=coordinator, specialists=(specialist,))
    assert TRANSFER_TOOL_NAME == "transfer_to_agent"
    assert group.get_agent("billing_specialist") is specialist

    mock_model = MockModelClient(
        responses=[
            [
                ModelDelta(
                    event_type="tool_call",
                    call_id="call-1",
                    tool_name="transfer_to_agent",
                    arguments={"target_agent": "billing_specialist"},
                )
            ],
            [ModelDelta(event_type="delta", text="Invoice refunded by specialist.")],
        ]
    )
    store = MemorySessionStore()
    runtime = AgentRuntime(
        group,
        default_model=mock_model,
        budget=TurnBudget(max_turns=5, max_tool_calls=10, timeout_seconds=30.0),
        sessions=store,
    )

    turn_resp = asyncio.run(runtime.run_turn(TurnRequest(user_message="Refund my invoice", session_id="sess-1")))
    assert turn_resp.output == "Invoice refunded by specialist."
    assert turn_resp.content == "Invoice refunded by specialist."
    assert turn_resp.agent_name == "billing_specialist"

    history = asyncio.run(runtime.get_history(ToolContext(), turn_resp.session_id))
    assert history is not None
    assert len(history) >= 2

    workflow = DynamicWorkflow(name="order-pipeline")

    async def step_ingest(ctx: WorkflowContext) -> str:
        return f"ingested:{ctx.state['item']}"

    async def step_verify(ctx: WorkflowContext) -> str:
        prior = ctx.step_results["ingest"].output
        return f"verified:{prior}"

    workflow.add_node("ingest", handler=step_ingest)
    workflow.add_node("verify", handler=step_verify, depends_on=("ingest",))
    engine = WorkflowEngine(default_runtime=runtime)
    wf_ctx = asyncio.run(engine.execute_run(workflow, {"item": "sku-9"}))
    assert wf_ctx.step_results["verify"].output == "verified:ingested:sku-9"
    assert wf_ctx.node_outputs["verify"] == "verified:ingested:sku-9"

    mcp_bridge_plugin = agent_to_mcp(specialist, path="/mcp")
    assert isinstance(mcp_bridge_plugin, LitestarMCP)
    bridge_app = Litestar(route_handlers=[], plugins=[mcp_bridge_plugin])
    mcp_bridge_plugin.on_startup(bridge_app)
    bridged_tools = mcp_to_tools(mcp_bridge_plugin)
    bridged_names = {t.name for t in bridged_tools}
    assert {"fetch_order_status", "refund_invoice"}.issubset(bridged_names)

    a2a_bridge_plugin = agent_to_a2a(
        specialist,
        path="/a2a",
        base_url="https://api.example.com",
        runtime=runtime,
    )
    assert isinstance(a2a_bridge_plugin, LitestarA2A)
    skill_ids = {s.id for s in a2a_bridge_plugin.agent_card.skills}
    assert "billing" in skill_ids

    raw_msg = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "fetch_order_status", "arguments": {"order_id": "100"}},
    }
    prepared = prepare_mcp_request(raw_msg)
    headers = mcp_request_headers(prepared)
    assert prepared["method"] == "tools/call"
    assert "io.modelcontextprotocol/protocolVersion" in prepared["params"]["_meta"]
    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "fetch_order_status"
    assert mcp_request_headers({"method": "server/discover"})["Mcp-Method"] == "server/discover"
    assert MCPStreamableHTTPClient is not None
    assert discover_mcp_tools is not None
    assert AgentChatController is not None
    assert LitestarStoreSessionStore is not None


def test_litestar_mcp_0160_queues_and_observability() -> None:
    """Verify distributed queue primitives and OpenTelemetry SpanManager contracts."""
    assert QueuedAgentChatController is not None
    assert QueuedTurnManager is not None
    assert QueuedTurn is not None
    assert PrincipalSnapshot is not None
    assert agent_turn_channel("turn-42") == "litestar_mcp:agent:turn-42"

    registry = AgentRegistry()
    sample_agent = Agent(name="worker_agent", instructions="Handle queued turns.")
    worker_runtime = AgentRuntime(sample_agent, default_model=MockModelClient())
    registry.register("worker_agent", worker_runtime)
    assert registry.get("worker_agent") is worker_runtime
    assert registry.get("unknown_agent") is None

    telemetry = TelemetryConfig(enable_spans=False)
    span_manager = SpanManager(telemetry)
    assert span_manager.is_enabled is False
    assert GEN_AI_AGENT_NAME == "gen_ai.agent.name"
    assert GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert LITESTAR_MCP_AGENT_GROUP == "litestar_mcp.agent.group"
    assert LITESTAR_MCP_TURN_ID == "litestar_mcp.turn.id"
