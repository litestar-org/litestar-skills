---
name: litestar-ai
description: Auto-activate for Google ADK, LlmAgent, Runner, SQLSpecSessionService, google-genai, AgentRuntime, SpecTree, DynamicWorkflow, FunctionTool, or SSE agent chats. Not for offline ML training.
---

# Litestar AI & Custom Agent Engineering

Build production AI agents, multi-agent specialist hierarchies, multi-step workflows, and structured LLM services in Litestar using either **Google ADK (`google-adk` + `sqlspec.extensions.adk`)** or a **native `google-genai` + `msgspec` agent runtime**.

## Code Style Rules

- **PEP 604 unions only**: `T | None`, never `Optional[T]`. Use built-in `list` and `dict` generics.
- **Async all I/O**: every model call, tool execution, session read/write, memory search, and cache lookup must be `async`.
- **`msgspec.Struct` wire contracts**: define request, response, SSE event, and runtime state payloads as `msgspec.Struct` (unless the project already standardizes on Pydantic).
- **Short-lived database transactions**: never hold open database connections across LLM generation turns; bind request-scoped services via an invocation-scoped `RunContextRegistry` token and acquire DB sessions inside individual tool calls or persistence steps.
- **Google-style docstrings**: document every agent factory, tool function, runtime service, and controller handler. Tool docstrings and parameter types define the model-visible tool schema.

## Quick Reference

### Architecture Selection (Match-Your-Stack)

| Pattern | Primary Signals | Best For |
| --- | --- | --- |
| **Google ADK + SQLSpec** (`google.adk` + `sqlspec.extensions.adk`) | `LlmAgent`, `App`, `Runner`, `SQLSpecSessionService`, `SQLSpecMemoryService`, `FunctionTool`, `SkillToolset` | Multi-turn conversational agents using ADK's built-in `sub_agents` delegation, `ContextCacheConfig`, `EventsCompactionConfig`, and `BasePlugin` callbacks backed by SQLSpec stores |
| **Native `google-genai` + `msgspec` Runtime** (`google.genai` + `msgspec` + `sqlspec`) | `AgentRuntime`, `AgentSpec`, `SpecTree`, `DynamicWorkflow`, `WorkflowEngine`, `declare`, `CacheRegistry`, `CompactionPolicy` | Explicit control over DAG workflows (`WorkflowNode`), parallel tool execution (`asyncio.gather`) with live SSE events, optimistic session locking (`expected_version`), and custom prompt slot fencing |
| **Structured-Output Domain Service** (`google.genai` + `GenerateContentConfig`) | `response_mime_type="application/json"`, `response_schema`, `embed_content`, `tenacity.retry` | Single-shot or batch classification, entity extraction, and embedding pipelines without multi-turn conversation state |
| **MCP Server Surface** (`litestar-mcp`) | `LitestarMCP`, `MCPConfig`, `mcp_tool=`, `mcp_resource=` | Exposing Litestar route handlers or domain services to external MCP clients (use `litestar-mcp`) |

### Session State Scope Prefixes

| Prefix | Lifetime | Typical Keys | Persistence Behavior |
| --- | --- | --- | --- |
| `app:*` | Application-wide | `app:catalog_version`, `app:feature_flags` | Shared across all users and sessions for `app_name` |
| `user:*` | Principal-scoped | `user:preferred_region`, `user:output_format` | Shared across sessions belonging to the same `(workspace_id, user_id)` |
| *(unprefixed)* | Session-scoped | `usage.total_tokens`, `compaction`, `workspace_id` | Persisted on the individual conversation session row |
| `temp:*` | Single turn | `temp:run_context_token`, `temp:dynamic_instruction`, `temp:tool_calls` | Invocation-local only; stripped before database persistence |

### Public SSE Event Contract

| `event` | Payload Shape (`data`) | Purpose |
| --- | --- | --- |
| `session` | `{"session_id": "...", "compacted_through_seq": 12}` | Emitted first so the client can bind the active session ID |
| `tool_call` | `{"id": "...", "name": "...", "author": "...", "args": {...}}` | Model requested a tool invocation |
| `tool_start` | `{"id": "...", "name": "...", "author": "...", "args": {...}}` | Parallel tool runner or workflow node started execution |
| `tool_end` | `{"id": "...", "name": "...", "author": "...", "status": "completed" \| "error", "result_preview": "..."}` | Tool finished with bounded JSON preview |
| `delta` | `{"text": "..."}` | Incremental assistant Markdown text chunk (thoughts excluded) |
| `ping` | `{}` | Keep-alive frame emitted on idle intervals before terminal frame |
| `complete` | `{"prompt_tokens": ..., "output_tokens": ..., "total_tokens": ..., "cached_tokens": ..., "finish_reason": "STOP"}` | Terminal success frame with aggregated turn token usage |
| `error` | `{"code": "...", "message": "..."}` | Terminal error frame (`session_turn_limit`, `llm_calls_exhausted`, `session_conflict`, `stream_error`) |

<workflow>

### 1. Choose the Agent Runtime Pattern

1. Inspect `pyproject.toml` and existing agent modules.
2. If `google-adk` is installed or `LlmAgent` / `Runner` is present, follow the **Google ADK + SQLSpec** pattern in [adk-and-serving.md](references/adk-and-serving.md).
3. If `google-genai` is used directly with `msgspec.Struct` events, `SpecTree`, or `DynamicWorkflow`, follow the **Native `google-genai` Runtime** pattern in [custom-agents-and-tools.md](references/custom-agents-and-tools.md).
4. If the task is non-conversational classification, extraction, or embedding, implement a **Structured-Output Domain Service** with `response_mime_type="application/json"` and `tenacity` backoff on HTTP 429.

### 2. Design Agent Hierarchies & Prompt Isolation

1. **Coordinator + Specialist Tree**:
   - In Google ADK, compose `LlmAgent(name="coordinator", sub_agents=[...], static_instruction=..., instruction=_dynamic_instruction)`.
   - In the native runtime, build a `SpecTree(root=coordinator, specialists={...}, declarations={...})` which automatically injects an enum-constrained `transfer_to_agent` tool into every agent in the tree.
2. **Static vs Dynamic Instructions**:
   - Keep `static_instruction` strictly immutable across turns and tenants so Vertex AI / Gemini context caching (`ContextCacheConfig` or `CacheRegistry`) produces stable SHA-256 digests.
   - Inject per-request context (tenant metadata, active engine/environment summary) via `temp:dynamic_instruction` in turn state and read it through a callable `instruction` / `dynamic_instruction` hook.
3. **Prompt-Injection Fencing**:
   - Wrap dynamic state, skill indices, and preloaded memory in explicit `<<<BEGIN_SYSTEM_INSTRUCTION>>> ... <<<END_SYSTEM_INSTRUCTION>>>` fences with a directive to treat the enclosed block as read-only reference data.

### 3. Engineer Tools & Request-Scoped DI Binding

1. **Bind Request-Scoped Services Safely**:
   - Register tools once at application startup (`Scope.APP`), but resolve request-scoped domain services (`Scope.REQUEST`) per turn through a `RunContextRegistry`.
   - At turn start, call `token = run_contexts.bind(tool_context)` and pass `temp:run_context_token: token` in the turn's `state_delta`; always call `run_contexts.release(token)` inside a `finally:` block when the stream closes.
2. **Normalize Outputs & Contain Recoverable Errors**:
   - Convert all tool return values into JSON-safe builtins (`msgspec.to_builtins` or a recursive `json_safe` helper) before persisting to `JSONB` event columns.
   - Catch expected domain errors inside tool wrappers and return `{"error": {"code": "...", "message": "..."}}` so the model can self-correct or narrow its query instead of crashing the turn.

### 4. Wire Persistence, Context Caching & Compaction

1. **Persistence**:
   - For Google ADK, wire `SQLSpecSessionService`, `SQLSpecMemoryService`, and optionally `SQLSpecArtifactService` from `sqlspec.extensions.adk`.
   - For the native runtime, wire `SessionStore` (with `version = version + 1 WHERE id = :id AND version = :expected` optimistic locking), `EventStore` (monotonic `seq` assignment under `SELECT last_seq ... FOR UPDATE`), and `MemoryStore` (parallel `app` + `user` hybrid FTS/vector search).
2. **Context Caching & Compaction**:
   - Enable `ContextCacheConfig` / `EventsCompactionConfig` in ADK `App(...)`, or wire `CacheRegistry` + `CompactionPolicy` + `Summarizer` in the native runtime.
   - Offload post-turn conversation compaction and vector embedding backfills to `litestar-queues` or `litestar-saq` background tasks so HTTP SSE streams never block on summarization.

### 5. Expose Terminal-Aware Streaming & Session Endpoints

1. Adapt internal runtime events through a `StreamService` that yields an initial `session` event, deduplicated `tool_call` / `tool_end` events, thought-filtered `delta` chunks, idle `ping` frames, and exactly one terminal `complete` or `error` event.
2. Wrap the SSE generator in `try ... finally: await close_async_iterator(events)` so client disconnects deterministically release `RunContextRegistry` tokens and background producer tasks.

</workflow>

<guardrails>

- **Never hold database connections across LLM awaits** — model generation takes seconds; holding a pooled connection across `generate_content` or `runner.run_async` exhausts the connection pool under concurrency.
- **Never instantiate `google.genai.Client` or `Runner` per request** — construct `ModelClient`, `RunContextRegistry`, `CacheRegistry`, and bounded `ApplicationFactory` caches at `Scope.APP`.
- **Never interpolate per-tenant or per-turn strings into `static_instruction`** — dynamic strings bust the static-prefix context cache on every turn; pass dynamic context via `temp:` state instead.
- **Never leak raw model `thought` parts or `thought_signature` bytes into user-visible `delta` frames** — filter out `part.thought is True` when extracting assistant text deltas while preserving `thought_signature` on persisted history turns for Gemini 2.5/3 thinking continuity.
- **Never inject unsanitized memory hits into prompts** — strip control characters, HTML-escape text, sanitize author labels, and cap preloaded memory size before inserting `<APPLICATION_MEMORY>` or `<PAST_CONVERSATIONS>` blocks.
- **Never split a `FunctionCall` from its matching `FunctionResponse` during compaction** — always cut history at a turn boundary where all open function call IDs have been answered (`find_safe_cut`).
- **Never allow unbounded tool or model loops** — enforce `max_turns_per_session`, `max_message_chars`, `max_tool_calls_per_turn`, and `max_model_calls_per_turn` via ADK `BasePlugin` callbacks or native `GuardHooks`.

</guardrails>

<validation>

- [ ] `RunContextRegistry.release(token)` runs in a `finally:` block on both normal completion and `asyncio.CancelledError` client disconnect.
- [ ] `static_instruction` contains zero per-request variables; dynamic context is read from `temp:` state.
- [ ] Tool outputs pass through `msgspec.to_builtins` / `json_safe` and return structured `{"error": ...}` payloads on recoverable failures.
- [ ] Stream adapter emits `session` first, filters out `part.thought` chunks, emits `ping` on idle intervals, and guarantees a single terminal `complete` or `error` event.
- [ ] Session updates enforce ownership (`workspace_id` + `principal_id`) and optimistic concurrency (`expected_version`) or scoped ADK lookup.
- [ ] `make check` (`lint`, `typecheck`, `test`, `validate-skills`) passes with zero warnings.

</validation>

<example>

```python
import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID, uuid4

import msgspec
from google.adk.agents import LlmAgent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext as AdkToolContext
from google.genai import types
from litestar import Controller, Litestar, post
from litestar.di import Provide
from litestar.exceptions import ServiceUnavailableException
from litestar.params import Dependency
from litestar.response import ServerSentEvent
from litestar.response.sse import ServerSentEventMessage
from litestar.status_codes import HTTP_200_OK
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgPoolConfig
from sqlspec.adapters.asyncpg.adk import AsyncpgADKMemoryStore, AsyncpgADKStore
from sqlspec.extensions.adk import SQLSpecMemoryService, SQLSpecSessionService
from sqlspec.extensions.litestar import SQLSpecPlugin

RUN_CONTEXT_KEY = "temp:run_context_token"
DYNAMIC_INSTRUCTION_KEY = "temp:dynamic_instruction"


class ChatPromptRequest(msgspec.Struct, kw_only=True):
    """Incoming request payload for an agent conversation turn."""

    message: str
    session_id: str | None = None
    stream: bool = True


class ChatResponse(msgspec.Struct, kw_only=True):
    """Non-streaming response payload for an agent conversation turn."""

    session_id: str
    message: str
    finish_reason: str
    usage: dict[str, int]


class StreamEvent(msgspec.Struct, kw_only=True):
    """Normalized outward event emitted over SSE."""

    event_type: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DomainToolContext:
    """Request-scoped context bound for the duration of a single agent turn."""

    workspace_id: UUID
    user_id: str


class RunContextRegistry:
    """Store request-scoped tool contexts behind opaque single-turn tokens."""

    def __init__(self) -> None:
        self._contexts: dict[str, DomainToolContext] = {}

    def bind(self, context: DomainToolContext) -> str:
        """Register a tool context and return an opaque token for temp state."""
        token = uuid4().hex
        self._contexts[token] = context
        return token

    def resolve(self, token: str) -> DomainToolContext:
        """Resolve an active tool context from its opaque token."""
        context = self._contexts.get(token)
        if context is None:
            msg = "Agent tool context is missing or expired"
            raise RuntimeError(msg)
        return context

    def release(self, token: str) -> None:
        """Remove a token when the turn completes or disconnects."""
        self._contexts.pop(token, None)


def _dynamic_instruction(ctx: ReadonlyContext) -> str:
    """Read invocation-scoped context from temporary session state."""
    return str(ctx.state.get(DYNAMIC_INSTRUCTION_KEY, ""))


def build_bound_tools(registry: RunContextRegistry) -> list[FunctionTool]:
    """Create ADK FunctionTools that resolve request-scoped state via RunContextRegistry."""

    async def get_workspace_summary(
        environment: str,
        tool_context: AdkToolContext | None = None,
    ) -> dict[str, Any]:
        """Fetch workload summary metrics for the active workspace environment."""
        if tool_context is None:
            return {"error": {"code": "missing_context", "message": "Tool context unavailable."}}
        token = str(tool_context.state.get(RUN_CONTEXT_KEY, ""))
        domain_ctx = registry.resolve(token)
        return {
            "workspace_id": str(domain_ctx.workspace_id),
            "environment": environment,
            "status": "healthy",
        }

    return [FunctionTool(get_workspace_summary)]


class AgentRuntimeService:
    """Manage the singleton ADK Runner and stream turn execution."""

    def __init__(
        self,
        runner: Runner,
        session_service: SQLSpecSessionService,
        run_contexts: RunContextRegistry,
        app_name: str = "litestar_assistant",
    ) -> None:
        self._runner = runner
        self._session_service = session_service
        self._run_contexts = run_contexts
        self._app_name = app_name

    async def stream_turn(
        self,
        *,
        workspace_id: UUID,
        user_id: str,
        message: str,
        session_id: str | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute one conversation turn and yield normalized StreamEvents."""
        resolved_id = session_id or uuid4().hex
        existing = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=user_id,
            session_id=resolved_id,
        )
        if existing is None:
            await self._session_service.create_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=resolved_id,
                state={"workspace_id": str(workspace_id)},
            )

        token = self._run_contexts.bind(DomainToolContext(workspace_id=workspace_id, user_id=user_id))
        state_delta: dict[str, object] = {
            RUN_CONTEXT_KEY: token,
            DYNAMIC_INSTRUCTION_KEY: f"Active workspace: {workspace_id}",
        }
        content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
        usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}

        try:
            yield StreamEvent(event_type="session", data={"session_id": resolved_id})
            async for event in self._runner.run_async(
                user_id=user_id,
                session_id=resolved_id,
                new_message=content,
                state_delta=state_delta,
            ):
                if event.usage_metadata is not None:
                    usage["prompt_tokens"] += int(event.usage_metadata.prompt_token_count or 0)
                    usage["output_tokens"] += int(event.usage_metadata.candidates_token_count or 0)
                    usage["total_tokens"] += int(event.usage_metadata.total_token_count or 0)
                    usage["cached_tokens"] += int(event.usage_metadata.cached_content_token_count or 0)
                if event.content and event.content.parts and event.author != "user":
                    text = "".join(
                        p.text or "" for p in event.content.parts if p.text and not getattr(p, "thought", False)
                    )
                    if text:
                        yield StreamEvent(event_type="delta", data={"text": text})
            yield StreamEvent(event_type="complete", data={**usage, "finish_reason": "STOP"})
        finally:
            self._run_contexts.release(token)
            latest = await self._session_service.get_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=resolved_id,
            )
            if latest is not None:
                await self._session_service.append_event(
                    session=latest,
                    event=Event(
                        author=self._app_name,
                        actions=EventActions(state_delta={"usage.last_turn": usage}),
                    ),
                )


class AgentChatController(Controller):
    """HTTP and SSE endpoints for multi-turn agent conversations."""

    path = "/api/v1/workspaces/{workspace_id:uuid}/agent"
    tags = ["Agent"]

    @post(path="/chat", status_code=HTTP_200_OK)
    async def chat(
        self,
        workspace_id: UUID,
        data: ChatPromptRequest,
        runtime_service: Annotated[AgentRuntimeService, Dependency(skip_validation=True)],
    ) -> ServerSentEvent | ChatResponse:
        """Stream an SSE conversation turn or return a consolidated JSON response."""
        if not data.message.strip():
            raise ServiceUnavailableException(detail="Prompt message cannot be empty.")

        user_id = f"{workspace_id}:default-user"
        if data.stream:

            async def sse_stream() -> AsyncIterator[ServerSentEventMessage]:
                events = runtime_service.stream_turn(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    message=data.message,
                    session_id=data.session_id,
                )
                try:
                    async for item in events:
                        payload = msgspec.json.encode(item.data).decode("utf-8")
                        yield ServerSentEventMessage(event=item.event_type, data=payload)
                except asyncio.CancelledError:
                    raise
                finally:
                    await events.aclose()

            return ServerSentEvent(sse_stream(), headers={"Content-Type": "text/event-stream; charset=utf-8"})

        chunks: list[str] = []
        resolved_session = data.session_id or ""
        usage_totals: dict[str, int] = {}
        events = runtime_service.stream_turn(
            workspace_id=workspace_id,
            user_id=user_id,
            message=data.message,
            session_id=data.session_id,
        )
        try:
            async for item in events:
                if item.event_type == "session":
                    resolved_session = str(item.data.get("session_id", resolved_session))
                elif item.event_type == "delta":
                    chunks.append(str(item.data.get("text", "")))
                elif item.event_type == "complete":
                    usage_totals = {k: int(v) for k, v in item.data.items() if isinstance(v, int)}
        finally:
            await events.aclose()

        return ChatResponse(
            session_id=resolved_session,
            message="".join(chunks),
            finish_reason="STOP",
            usage=usage_totals,
        )


sql_runtime = SQLSpec()
db_config = AsyncpgConfig(
    connection_config=AsyncpgPoolConfig(dsn="postgresql://app:app@localhost:5432/app"),
    extension_config={"adk": {"session_table": "adk_sessions", "events_table": "adk_events"}},
)
sql_runtime.add_config(db_config)

run_context_registry = RunContextRegistry()
session_store = SQLSpecSessionService(AsyncpgADKStore(db_config))
memory_store = SQLSpecMemoryService(AsyncpgADKMemoryStore(db_config))

specialist_agent = LlmAgent(
    name="metrics_specialist",
    model="gemini-2.5-flash",
    description="Analyzes workload health and capacity metrics.",
    static_instruction="You are the metrics specialist. Answer using workspace telemetry tools.",
    instruction=_dynamic_instruction,
    tools=build_bound_tools(run_context_registry),
)

coordinator_agent = LlmAgent(
    name="workspace_coordinator",
    model="gemini-2.5-flash",
    description="Coordinates workspace analysis and delegates to specialists.",
    static_instruction="You coordinate workspace diagnostics and delegate metrics questions.",
    instruction=_dynamic_instruction,
    sub_agents=[specialist_agent],
)

adk_app = App(
    name="litestar_assistant",
    root_agent=coordinator_agent,
    context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
    events_compaction_config=EventsCompactionConfig(compaction_interval=10, overlap_size=2),
)

adk_runner = Runner(
    app=adk_app,
    session_service=session_store,
    memory_service=memory_store,
)


async def provide_runtime_service() -> AgentRuntimeService:
    """Provide the singleton AgentRuntimeService."""
    return AgentRuntimeService(
        runner=adk_runner,
        session_service=session_store,
        run_contexts=run_context_registry,
    )


app = Litestar(
    route_handlers=[AgentChatController],
    plugins=[SQLSpecPlugin(sql_runtime)],
    dependencies={"runtime_service": Provide(provide_runtime_service)},
)
```

</example>

## References Index

- **[adk-and-serving.md](references/adk-and-serving.md)** — Google ADK `LlmAgent` + `App` + `Runner` architecture, bounded LRU `AgentApplicationFactory`, `SQLSpecSessionService` / `SQLSpecMemoryService` / `SQLSpecArtifactService` store wiring, `RunContextRegistry` + `JSONSafeTool`, sanitized `PreloadMemoryTool`, `BasePlugin` guardrails, Dishka & native DI wiring, and `prune_sessions` / `prune_memory` retention pruning.
- **[custom-agents-and-tools.md](references/custom-agents-and-tools.md)** — Native `google-genai` + `msgspec` agent runtime (`AgentRuntime`, `AgentSpec`, `SpecTree` with `transfer_to_agent`), `GeminiModelClient` turn normalization, `declare()` + `msgspec.json.schema` to Gemini schema translation, `execute_parallel` tool runner, multi-step `DynamicWorkflow` / `WorkflowEngine` / `BaseSpecialistNode`, and standalone structured-output LLM classifiers.
- **[streaming-and-queues.md](references/streaming-and-queues.md)** — Terminal-aware SSE `StreamService.adapt()`, `TranscriptReconstructor` session history endpoints, static-prefix `CacheRegistry`, rolling `CompactionPolicy` + `Summarizer` with `find_safe_cut`, `litestar-queues` background compaction and embedding jobs, and OpenTelemetry tracing spans.

## Official References

- [Google Agent Development Kit (ADK) Documentation](https://google.github.io/adk-docs/)
- [Google Gen AI Python SDK (`google-genai`)](https://googleapis.github.io/python-genai/)
- [SQLSpec ADK Extension Documentation](https://litestar-org.github.io/sqlspec/usage/extensions/adk/)
- [Litestar Server-Sent Events (SSE)](https://docs.litestar.dev/2/usage/responses.html#server-sent-events-responses)
- [Google Developer Knowledge MCP](../litestar-styleguide/references/google-developer-knowledge-mcp.md)

## Shared Styleguide Baseline

Follow [litestar-styleguide](../litestar-styleguide/SKILL.md) for PEP 604 type annotations, async-first concurrency, `msgspec.Struct` schemas, and testing conventions.
