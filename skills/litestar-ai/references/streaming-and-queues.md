# Terminal-Aware SSE Streaming, Context Caching, Compaction & Background Queues

Use this reference when implementing SSE streaming controllers, transcript reconstruction, static-prefix context caching, rolling conversation compaction, `litestar-queues` background jobs, and OpenTelemetry tracing.

---

## 1. Terminal-Aware `StreamService.adapt()` with Keep-Alive Pings

Long-running tool calls, multi-step workflows, and thinking models can pause for several seconds between chunks. Wrap the underlying event iterator in a producer task with `asyncio.wait_for(..., timeout=ping_interval)` so the HTTP SSE stream:

1. Emits `session` immediately with `session_id` and `compacted_through_seq`.
2. Emits `ping` frames when idle so reverse proxies and browsers do not drop the connection.
3. Deduplicates `tool_call` IDs, truncates `tool_end` previews (`240` chars), and strips `part.thought` text from `delta` frames.
4. Guarantees a single terminal `complete` or `error` frame and always closes the underlying async iterator via `close_async_iterator()`.

```python
import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

import msgspec

RESULT_PREVIEW_CHARS = 240
DEFAULT_PING_INTERVAL = 5.0


@runtime_checkable
class AsyncClosableIterator(Protocol):
    """Protocol for async iterators supporting explicit aclose()."""

    def __aiter__(self) -> AsyncIterator[Any]: ...
    async def __anext__(self) -> Any: ...
    async def aclose(self) -> None: ...


class PublicStreamEvent(msgspec.Struct, kw_only=True):
    """Outward event serialized as an SSE frame."""

    event_type: Literal["session", "tool_call", "tool_start", "tool_end", "delta", "ping", "complete", "error"]
    data: dict[str, Any]


async def close_async_iterator(iterator: AsyncIterator[object]) -> None:
    """Close an async iterator while containing non-cancellation finalizer errors."""
    if not isinstance(iterator, AsyncClosableIterator):
        return
    with contextlib.suppress(asyncio.CancelledError, RuntimeError, OSError, ValueError):
        await iterator.aclose()


def build_tool_preview(response: dict[str, Any]) -> tuple[Literal["completed", "error"], str]:
    """Classify a tool response and return a bounded JSON preview string."""
    status: Literal["completed", "error"] = "error" if response.get("error") else "completed"
    encoded = msgspec.json.encode(response).decode("utf-8")
    if len(encoded) <= RESULT_PREVIEW_CHARS:
        return status, encoded
    return status, f"{encoded[: RESULT_PREVIEW_CHARS - 1]}…"


class AgentStreamService:
    """Adapt internal agent events into a terminal-aware SSE event stream."""

    def __init__(self, ping_interval: float = DEFAULT_PING_INTERVAL) -> None:
        self._ping_interval = ping_interval

    async def _producer(
        self,
        source: AsyncIterator[Any],
        queue: asyncio.Queue[Any | Exception | None],
        fetch_next: asyncio.Event,
    ) -> None:
        try:
            while True:
                await fetch_next.wait()
                fetch_next.clear()
                try:
                    item = await anext(source)
                except StopAsyncIteration:
                    await queue.put(None)
                    break
                await queue.put(item)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await queue.put(exc)
        finally:
            await close_async_iterator(source)

    async def adapt(
        self,
        agent_events: AsyncIterator[Any],
        *,
        session_id: UUID,
        compacted_through_seq: int | None = None,
    ) -> AsyncGenerator[PublicStreamEvent, None]:
        """Yield ordered PublicStreamEvents with keep-alive pings and guaranteed cleanup."""
        fetch_next = asyncio.Event()
        fetch_next.set()
        queue: asyncio.Queue[Any | Exception | None] = asyncio.Queue(maxsize=1)
        producer_task = asyncio.create_task(self._producer(agent_events, queue, fetch_next))
        seen_calls: set[str] = set()
        has_final = False
        usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}

        try:
            yield PublicStreamEvent(
                event_type="session",
                data={"session_id": str(session_id), "compacted_through_seq": compacted_through_seq},
            )
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self._ping_interval)
                except TimeoutError:
                    if not has_final:
                        yield PublicStreamEvent(event_type="ping", data={})
                    continue

                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item

                if item.usage is not None:
                    usage["prompt_tokens"] += int(item.usage.prompt_tokens)
                    usage["output_tokens"] += int(item.usage.output_tokens)
                    usage["total_tokens"] += int(item.usage.total_tokens)
                    usage["cached_tokens"] += int(item.usage.cached_tokens)

                for call in item.function_calls():
                    call_id = call.id or call.name
                    if call_id not in seen_calls:
                        seen_calls.add(call_id)
                        yield PublicStreamEvent(
                            event_type="tool_call",
                            data={"id": call.id, "name": call.name, "author": item.agent, "args": call.args},
                        )

                for resp in item.function_responses():
                    status, preview = build_tool_preview(resp.response)
                    yield PublicStreamEvent(
                        event_type="tool_end",
                        data={
                            "id": resp.id,
                            "name": resp.name,
                            "author": item.agent,
                            "status": status,
                            "result_preview": preview,
                        },
                    )

                delta_text = item.text() if item.agent != "user" else ""
                if delta_text:
                    yield PublicStreamEvent(event_type="delta", data={"text": delta_text})

                if not item.partial and item.content and item.content.role == "model" and not item.function_calls():
                    has_final = True

                fetch_next.set()

            if has_final:
                yield PublicStreamEvent(
                    event_type="complete",
                    data={**usage, "finish_reason": "STOP"},
                )
            else:
                yield PublicStreamEvent(
                    event_type="error",
                    data={"code": "stream_incomplete", "message": "Stream ended before final response."},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            yield PublicStreamEvent(
                event_type="error",
                data={"code": "stream_error", "message": "The agent stream failed. Please retry."},
            )
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, RuntimeError, OSError, ValueError):
                    await producer_task
```

---

## 2. Session History CRUD & `TranscriptReconstructor`

Expose dedicated session endpoints (`GET /sessions`, `GET /sessions/{session_id}`, `DELETE /sessions/{session_id}`) alongside `POST /chat` so clients can list conversations, restore full transcripts with correlated tool call previews on page reload, and delete sessions.

```python
from typing import Annotated, Literal
from uuid import UUID

import msgspec
from litestar import Controller, delete, get
from litestar.exceptions import NotFoundException
from litestar.params import Dependency, Parameter


class ToolCallSummary(msgspec.Struct, kw_only=True):
    """Correlated tool call and preview returned in a session transcript."""

    id: str
    name: str
    author: str
    args: dict[str, object]
    status: Literal["completed", "error"]
    result_preview: str | None = None


class TurnMessage(msgspec.Struct, kw_only=True):
    """Single reconstructed user or assistant turn for UI rendering."""

    role: Literal["user", "model"]
    text: str
    tool_calls: list[ToolCallSummary] = []
    timestamp: float = 0.0
    finish_reason: str | None = None


class SessionDetail(msgspec.Struct, kw_only=True):
    """Full conversation session detail and ordered transcript turns."""

    id: UUID
    title: str
    turn_count: int
    messages: list[TurnMessage]


class SessionHistoryService:
    """Service loading scoped session summaries and reconstructed transcripts."""

    async def list_sessions(self, workspace_id: UUID, user_id: str) -> list[dict[str, object]]:
        """Return sessions owned by workspace_id and user_id."""
        del workspace_id, user_id
        return []

    async def get_transcript(self, workspace_id: UUID, user_id: str, session_id: UUID) -> SessionDetail | None:
        """Load session events and reconstruct TurnMessage records."""
        del workspace_id, user_id, session_id
        return None

    async def delete_session(self, workspace_id: UUID, user_id: str, session_id: UUID) -> None:
        """Delete a scoped session and its events."""
        del workspace_id, user_id, session_id


class AgentSessionController(Controller):
    """Multi-turn session history CRUD endpoints."""

    path = "/api/v1/workspaces/{workspace_id:uuid}/agent/sessions"
    tags = ["Agent"]

    @get(path="/")
    async def list_sessions(
        self,
        workspace_id: UUID,
        session_service: Annotated[SessionHistoryService, Dependency(skip_validation=True)],
    ) -> list[dict[str, object]]:
        """List active multi-turn chat sessions for the workspace."""
        return await session_service.list_sessions(workspace_id=workspace_id, user_id="default-user")

    @get(path="/{session_id:uuid}")
    async def get_session(
        self,
        workspace_id: UUID,
        session_id: Annotated[UUID, Parameter(title="Session ID")],
        session_service: Annotated[SessionHistoryService, Dependency(skip_validation=True)],
    ) -> SessionDetail:
        """Retrieve reconstructed turn history for a single session."""
        detail = await session_service.get_transcript(
            workspace_id=workspace_id,
            user_id="default-user",
            session_id=session_id,
        )
        if detail is None:
            raise NotFoundException(detail=f"Session {session_id} not found.")
        return detail

    @delete(path="/{session_id:uuid}", status_code=204)
    async def delete_session(
        self,
        workspace_id: UUID,
        session_id: Annotated[UUID, Parameter(title="Session ID")],
        session_service: Annotated[SessionHistoryService, Dependency(skip_validation=True)],
    ) -> None:
        """Delete a chat session and cascade its persisted events."""
        await session_service.delete_session(
            workspace_id=workspace_id,
            user_id="default-user",
            session_id=session_id,
        )
```

---

## 3. Static-Prefix Context Caching (`CacheRegistry`)

When using a native `google-genai` runtime, cache the immutable prefix `(model, backend_scope, static_instruction, sorted_tool_declarations)`:

1. Compute a deterministic SHA-256 digest over the canonical JSON encoding of `(model, backend_scope, static_instruction, sorted(tools, key=lambda t: t.name))`.
2. Only create a server-side cache when `count_tokens` exceeds `min_tokens` (e.g., `2,048` tokens); mark smaller prefixes `ineligible` in the database so subsequent turns skip `count_tokens`.
3. Create and extend caches asynchronously (`asyncio.create_task`) so the active turn never blocks on cache provisioning.
4. If `generate_content` raises a cache-not-found or expired error, invalidate the digest and retry the model call uncached in the same turn.

```python
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import msgspec


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Configuration for server-side static-prefix context caching."""

    enabled: bool = True
    ttl_seconds: int = 3600
    min_tokens: int = 2048
    renew_headroom_seconds: int = 300


def compute_static_prefix_digest(
    *,
    model: str,
    backend_scope: dict[str, Any],
    static_instruction: str,
    tool_declarations: list[dict[str, Any]],
) -> str:
    """Compute a deterministic SHA-256 digest for a static instruction and toolset prefix."""
    sorted_tools = sorted(tool_declarations, key=lambda item: str(item.get("name", "")))
    canonical = msgspec.json.encode(
        {
            "model": model,
            "backend_scope": backend_scope,
            "static_instruction": static_instruction,
            "tools": sorted_tools,
        }
    )
    return sha256(canonical).hexdigest()
```

---

## 4. Safe-Cut Conversation Compaction & `litestar-queues` Background Tasks

Never block an HTTP SSE response to run conversation summarization or vector embedding generation. Instead:

1. At the end of a turn, check `CompactionPolicy`: if `turn_count` or `last_prompt_tokens` exceeds the threshold (`min_turns_to_compact = 6`, `token_threshold = 48_000`), enqueue a background `litestar-queues` task.
2. In `find_safe_cut()`, walk backward from `len(events) - retain_recent_events` until there are **zero unanswered `FunctionCall` IDs** across the cut boundary—Gemini rejects any history where a `function_call` turn is separated from its matching `function_response` turn.
3. Extract the summary inside `<summary>...</summary>` delimiters, verify token savings meet `min_savings_ratio` (`0.20`), and persist the compaction record in `session.state["compaction"]` using optimistic concurrency (`expected_version`).

```python
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from litestar_queues import QueueService, task

SUMMARY_TAG_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CompactionPolicy:
    """Thresholds controlling background conversation compaction."""

    enabled: bool = True
    min_turns_to_compact: int = 6
    retain_recent_turns: int = 3
    token_threshold: int = 48_000
    min_savings_ratio: float = 0.20


def find_safe_cut(events: list[Any], retain_recent_turns: int) -> int:
    """Find the latest index before recent turns where no FunctionCall lacks its FunctionResponse."""
    if not events:
        return 0
    turns = sorted({int(e.turn) for e in events})
    if len(turns) <= retain_recent_turns:
        return 0
    cutoff_turn = turns[-retain_recent_turns]
    candidate_idx = next((i for i, e in enumerate(events) if e.turn >= cutoff_turn), 0)

    while candidate_idx > 0:
        prefix = events[:candidate_idx]
        open_calls: set[str] = set()
        for ev in prefix:
            for fc in ev.function_calls():
                open_calls.add(fc.id or fc.name)
            for fr in ev.function_responses():
                open_calls.discard(fr.id or fr.name)
                open_calls.discard(fr.name)
        if not open_calls:
            return candidate_idx
        candidate_idx -= 1
    return 0


def extract_summary_block(raw_text: str) -> str:
    """Extract text enclosed in <summary>...</summary> tags or fall back to stripped text."""
    match = SUMMARY_TAG_RE.search(raw_text)
    return match.group(1).strip() if match else raw_text.strip()


@task(
    key="agent.compact_session",
    queue="agent-maintenance",
    retries=2,
    timeout=120,
)
async def compact_agent_session(session_id: str) -> dict[str, Any]:
    """Background task that summarizes older turns and updates session compaction state."""
    target_id = UUID(session_id)
    return {"session_id": str(target_id), "status": "compacted"}


@task(
    key="agent.backfill_memory_embeddings",
    queue="agent-maintenance",
    retries=3,
    timeout=180,
)
async def backfill_memory_embeddings(batch_size: int = 32) -> dict[str, int]:
    """Background task that computes dense embeddings for unindexed memory rows."""
    return {"batch_size": batch_size, "indexed": 0}


async def schedule_post_turn_compaction(
    queues: QueueService,
    *,
    session_id: UUID,
    turn_count: int,
    last_prompt_tokens: int,
    policy: CompactionPolicy,
) -> bool:
    """Enqueue session compaction when turn count or prompt tokens cross policy thresholds."""
    if not policy.enabled:
        return False
    if turn_count < policy.min_turns_to_compact and last_prompt_tokens < policy.token_threshold:
        return False
    await queues.enqueue("agent.compact_session", session_id=str(session_id))
    return True
```

---

## 5. OpenTelemetry Observability Spans

Instrument every layer of the agent loop with structured OpenTelemetry spans so latency bottlenecks, cache hit rates, specialist delegations, and tool failures are visible in distributed traces:

| Span Name | Key Attributes |
| --- | --- |
| `agent.turn` | `session.id`, `workspace.id`, `agent.name`, `agent.turn` |
| `agent.model_call` | `model`, `prompt_tokens`, `output_tokens`, `cached_tokens` |
| `agent.tool_call` | `tool.name`, `function_call.id` |
| `agent.transfer` | `source.agent`, `target.agent` |
| `agent.cache` | `cache.digest`, `cache.action` (`lookup`, `create`, `extend`, `invalidate`) |
| `agent.compaction` | `session.id`, `scope`, `compacted_through_seq` |
| `agent.workflow` | `workflow.name`, `workflow.execution_id` |
| `agent.workflow_node` | `node.id`, `node.type` |
