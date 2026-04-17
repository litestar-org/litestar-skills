# AI serving — Litestar + Google ADK

This reference covers HTTP-facing AI endpoints built with Google Agent Development Kit (ADK) `LlmAgent` + `Runner`, backed by `SQLSpecSessionService` for multi-turn memory, and wired through Dishka for dependency injection. It documents the request/response (non-streaming) handler pattern found in `oracledb-vertexai-demo`. For vector search and embedding internals, see [`../../sqlspec/references/vector-search.md`](../../sqlspec/references/vector-search.md).

## ADK at a glance

- **`LlmAgent`** — the reasoning loop: holds system instructions, a model slug, and the list of callable tools.
- **`Runner`** — the event pump: takes an agent, an `app_name`, and a session service; drives the turn-by-turn `run_async` iteration.
- **`SQLSpecSessionService`** — multi-turn memory: persists conversation history via an ADK store so the agent recalls prior turns across HTTP requests.
- **`tools`** — async functions the agent can invoke during a turn (search, lookup, classify). Each tool is a plain `async def` registered on the agent.

See the [Google ADK documentation](https://google.github.io/adk-docs/) for the full API surface.

## Provider wiring (Dishka)

All three ADK objects are expensive to construct (model initialisation, client creation) and are thread-safe, so they live at `Scope.APP`. The `QueryContext` needed per request lives at `Scope.REQUEST`. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/chat/services/__init__.py`.

```python
from dishka import Provider, Scope, provide
from litestar_adk import OracleAsyncADKStore
from google.adk.sessions import SQLSpecSessionService
from sqlspec.adapters.oracledb import OracleAsyncConfig

from app.domains.chat.services.runner import AIRunner


class AgentServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_adk_store(self, config: OracleAsyncConfig) -> OracleAsyncADKStore:
        return OracleAsyncADKStore(config=config)

    @provide(scope=Scope.APP)
    def get_session_service(
        self, store: OracleAsyncADKStore
    ) -> SQLSpecSessionService:
        return SQLSpecSessionService(store)

    @provide(scope=Scope.APP)
    def get_adk_runner(
        self, session_service: SQLSpecSessionService
    ) -> AIRunner:
        return AIRunner(session_service=session_service)
```

Note: no `from __future__ import annotations` — Dishka inspects `@provide` signatures at runtime. The future-annotations import defers evaluation and breaks DI introspection.

## Runner construction

`AIRunner` wraps `LlmAgent` + `Runner` and exposes a single `process_request` coroutine. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/chat/services/adk.py:L135–143`.

```python
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import SQLSpecSessionService

from app.domains.chat.tools import search_records_by_vector, get_record_details, classify_intent
from app.lib.settings import get_settings

settings = get_settings()

ALL_TOOLS = [search_records_by_vector, get_record_details, classify_intent]


class AIRunner:
    def __init__(self, session_service: SQLSpecSessionService) -> None:
        self.session_service = session_service
        agent = LlmAgent(
            name="SupportAssistant",
            instruction=BASE_SYSTEM_INSTRUCTION,
            model=settings.vertex_ai.CHAT_MODEL,
            tools=ALL_TOOLS,
        )
        self._runner = Runner(
            agent=agent,
            app_name="support-assistant",
            session_service=session_service,
        )
```

Tools are plain `async def` functions in the same module — the ADK runtime discovers their signatures and docstrings to build its tool catalog.

## Multi-turn session memory

`SQLSpecSessionService` wraps an `OracleAsyncADKStore` (or any ADK-compatible store). Before each turn the runner calls `get_session(app_name, user_id, session_id)` to load prior history; if no session exists it calls `create_session(...)` with an empty state. The Runner persists each turn's events back to the store automatically. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/chat/services/adk.py:L144–147`.

This is what enables users to reference "my last question" across HTTP requests without the handler maintaining any state.

## Handler pattern (synchronous request/response)

The canonical demo uses a straight `await runner.process_request(...)` → return-JSON pattern — no streaming, no SSE, no async generator. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/chat/controllers.py:L56–98`.

```python
import uuid
from litestar import post, Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_503_SERVICE_UNAVAILABLE
from dishka.integrations.litestar import FromDishka as Inject

from app.domains.chat.schemas import ChatMessage, ChatReply
from app.domains.chat.services.runner import AIRunner


class ChatController:
    @post("/api/chat", name="chat.api.send")
    async def send_chat_message(
        self,
        data: ChatMessage,
        adk_runner: Inject[AIRunner],
        request: Request,
    ) -> ChatReply:
        session_id = request.headers.get("x-session-id", str(uuid.uuid4()))
        result = await adk_runner.process_request(
            query=data.message,
            user_id="web_user",
            session_id=session_id,
            persona=data.persona,
        )
        return ChatReply(message=result["text"])
```

The handler returns a msgspec `ChatReply` struct; Litestar serialises it to JSON. The `x-session-id` header binds turns into a conversation thread — clients that omit it get a fresh session each call.

**Streaming note:** this handler does NOT stream. See [Streaming — not yet canonical](#streaming--not-yet-canonical) below.

## Persona-augmented prompts

The `PersonaManager` pattern concatenates a shared base instruction with a persona-specific addon at request time. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/system/services/services.py:L127–129`.

```python
@classmethod
def get_system_prompt(cls, persona_key: str, base_prompt: str) -> str:
    persona = cls.PERSONAS.get(persona_key, cls.PERSONAS["user"])
    return f"{base_prompt}\n\n## Persona Context: {persona.name}\n{persona.system_prompt_addon}"
```

Example persona set (neutral-domain variant; the demo uses 4 personas named `novice`, `enthusiast`, `expert`, and a domain-specific role):

| Key | Description |
|---|---|
| `novice` | Plain language, step-by-step guidance |
| `user` | Default; balanced tone and depth |
| `expert` | Terse, technical; assume deep knowledge |
| `admin` | Full internal context; no simplification |

Each persona is a `msgspec.Struct` with a `system_prompt_addon: str` field appended to `BASE_SYSTEM_INSTRUCTION`.

## Tool-use-first prompt pattern

The reference demo uses a structured instruction that forces the agent to call `classify_intent` before doing anything else. This prevents hallucinated responses to out-of-scope queries. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/system/services/services.py:L35–64`.

```python
BASE_SYSTEM_INSTRUCTION = """
You are a helpful support assistant. Follow these steps for EVERY user message:

## STEP 1 — Classify intent
ALWAYS call the `classify_intent` tool first.
Do not answer until you have the intent label.

## STEP 2 — Branch on intent
- SEARCH   → call `search_records_by_vector`, then summarise the results
- HELP      → answer from your knowledge; do not call search
- PURCHASE  → confirm the request, then call the purchase tool
- SUPPORT   → escalate; do not attempt to resolve autonomously
- CONVERSATION → respond naturally; skip all other tools

## CRITICAL REQUIREMENTS
- Never skip STEP 1, even for trivial inputs.
- Never fabricate record IDs or facts not returned by a tool.
- If a tool returns an empty result, say so honestly.
"""
```

The workflow scaffold (STEP 1 / STEP 2 / CRITICAL REQUIREMENTS) is the durable pattern — the intent labels and tool names change per application.

## Missing-credentials handling

Vertex AI clients raise `ValueError` when credentials or API keys are absent. Convert these to HTTP 503 so the client knows the service is temporarily unavailable rather than receiving a 500 with a stack trace. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/chat/controllers.py:L69–78`.

```python
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_503_SERVICE_UNAVAILABLE


async def call_with_credential_guard(coro):
    try:
        return await coro
    except ValueError as exc:
        msg = str(exc).lower()
        if "api key" in msg or "credentials" in msg:
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI backend not configured — check VERTEX_AI_* environment variables.",
            ) from exc
        raise
```

Apply this guard in the handler or in `AIRunner.process_request` before the call to `self._runner.run_async(...)`.

## Streaming — not yet canonical

The reference app (`oracledb-vertexai-demo`) does not stream responses. It awaits the full ADK event iteration inside `process_request` and returns a plain JSON dict. The `STREAM_BUFFER_SIZE` / `STREAM_TIMEOUT_SECONDS` settings exist in `VertexAISettings` but are unused by the current handler.

When a canonical streaming example lands, this section will be expanded to cover `litestar.response.Stream` / SSE patterns and the ADK async-generator event protocol. Until then, ship the synchronous pattern above.

## SAQ batch inference — not yet canonical

The reference app does not use SAQ for async inference batches. Everything runs inline within the HTTP request lifecycle. Projects that need batch inference (e.g., nightly embedding regeneration, bulk classification) should adapt the canonical SAQ patterns from [`../../litestar-saq/SKILL.md`](../../litestar-saq/SKILL.md) with an inference task, but no first-party reference exists yet for this combination.

## Vertex AI settings

`VertexAISettings` is a plain `@dataclass` loaded from environment variables. Canonical source: `oracledb-vertexai-demo/src/py/app/lib/settings.py:L283–318`. Use a stable model slug (not preview) for production; check [Google Vertex AI model cards](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models) for current names.

```python
import os
from dataclasses import dataclass, field


@dataclass
class VertexAISettings:
    PROJECT_ID: str = field(
        default_factory=lambda: os.getenv("VERTEX_AI_PROJECT_ID", "")
    )
    LOCATION: str = field(
        default_factory=lambda: os.getenv("VERTEX_AI_LOCATION") or "us-central1"
    )
    API_KEY: str | None = field(
        default_factory=lambda: (
            os.getenv("VERTEX_AI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
    )
    EMBEDDING_MODEL: str = field(
        default_factory=lambda: os.getenv(
            "VERTEX_AI_EMBEDDING_MODEL", "gemini-embedding-001"
        )
    )
    EMBEDDING_DIMENSIONS: int = 768
    CHAT_MODEL: str = field(
        default_factory=lambda: os.getenv(
            "VERTEX_AI_CHAT_MODEL", "gemini-1.5-flash-001"
        )
    )
    CACHE_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("VERTEX_AI_CACHE_TTL_SECONDS", "3600"))
    )
```

**Match-Your-Stack:** if the project is already on `pydantic_settings`, use `BaseSettings` with `env_prefix="VERTEX_AI_"` instead of the bare `@dataclass`. Both approaches read the same environment variables.

## Cross-references

- [`../../sqlspec/references/vector-search.md`](../../sqlspec/references/vector-search.md) — Oracle `VECTOR_DISTANCE` similarity search, Vertex AI embedding generation, embedding cache, intent exemplar table
- [`../../sqlspec/references/dishka-integration.md`](../../sqlspec/references/dishka-integration.md) — Full multi-provider Dishka setup (persistence + domain services + app singletons)
- [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) — `SQLSpecAsyncService` base, named SQL templates, driver API
- [`../../msgspec/references/litestar-patterns.md`](../../msgspec/references/litestar-patterns.md) — msgspec Struct DTOs, camelCase rename, MsgspecDTO

## Shared Styleguide Baseline

- [`../litestar-styleguide/references/general.md`](../litestar-styleguide/references/general.md) — Cross-language baseline
- [`../litestar-styleguide/references/python.md`](../litestar-styleguide/references/python.md) — Python conventions
- [`../litestar-styleguide/references/litestar.md`](../litestar-styleguide/references/litestar.md) — Litestar-specific baseline
