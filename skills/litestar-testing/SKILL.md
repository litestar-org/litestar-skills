---
name: litestar-testing
description: "Use when working with test_*.py, conftest.py, litestar.testing, TestClient, AsyncTestClient, create_test_client, create_async_test_client, anyio, Guard mocks, or DI overrides. Not for generic pytest."
---

# litestar-testing

Litestar-specific testing patterns built on pytest + anyio. Covers:

- `TestClient` vs `AsyncTestClient` — constructor options, lifespan, and when to use each
- `create_test_client` and `create_async_test_client` — inline app factories for isolated handler/controller tests
- `@pytest.mark.anyio` setup and `pytest-asyncio` coexistence rules
- App + lifespan fixtures (`on_startup` / `on_shutdown` / `lifespan`)
- Mocking Guards and overriding DI dependencies (native `Provide` and Dishka `Provider`)
- Session testing with `set_session_data` and `get_session_data`
- WebSocket testing with `websocket_connect` and `WebSocketTestSession`
- Unit-testing Guards and dependencies with `RequestFactory`
- Live server subprocess testing with `subprocess_async_client` and `subprocess_sync_client`
- Integration with `pytest-databases` (see `../pytest-databases/SKILL.md`) and `polyfactory` (see `../polyfactory/SKILL.md`)
- Autowire discovery and cache isolation (see `../litestar-autowire/references/testing.md`)

For JS-side testing (Vitest, Testing Library, Playwright), use the upstream Vitest docs and Litestar's own JS examples. Out of scope here.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Test modules MAY use `from __future__ import annotations` — they are pure consumer code.
- Function-based tests (not class-based)
- One assertion concern per test
- Async Litestar tests use `@pytest.mark.anyio` by default; do not mix AnyIO and `pytest-asyncio` auto modes.
- Prefer `AsyncTestClient` for new code; `TestClient` only for legacy / sync-only flows.
- Always enter test clients as context managers (`async with AsyncTestClient(...)` / `with TestClient(...)`) — `LifeSpanHandler` only runs inside `__aenter__` / `__enter__`, so without a context manager `on_startup`, `on_shutdown`, and `lifespan` hooks never execute.

## Quick Reference

### TestClient vs AsyncTestClient

| Client | Base Class | Context Manager | Session Helpers | WebSocket Connect |
| --- | --- | --- | --- | --- |
| `AsyncTestClient` | `httpx.AsyncClient`, `BaseTestClient` | `async with AsyncTestClient(app=app) as client:` | `await client.set_session_data(...)` / `await client.get_session_data()` | `with await client.websocket_connect("/ws") as ws:` |
| `TestClient` | `httpx.Client`, `BaseTestClient` | `with TestClient(app=app) as client:` | `client.set_session_data(...)` / `client.get_session_data()` | `with client.websocket_connect("/ws") as ws:` |

Both clients accept the same constructor parameters:

```python
from litestar.testing import AsyncTestClient, TestClient

AsyncTestClient(
    app=app,
    base_url="http://testserver.local",  # Must contain a dot ('.') or UserWarning is emitted
    raise_server_exceptions=True,  # False wraps unhandled server exceptions as HTTP 500 responses
    root_path="",
    backend="asyncio",  # "asyncio" | "trio"
    backend_options=None,
    session_config=None,  # Required for get_session_data() / set_session_data()
    timeout=None,
    cookies=None,
)
```

Both set `follow_redirects=True` and `headers={"user-agent": "testclient"}` by default. When testing template responses, `TestClientTransport` populates `response.template` and `response.context` on the returned `httpx.Response`.

```python
from litestar.testing import AsyncTestClient


async def test_index(async_client: AsyncTestClient) -> None:
    resp = await async_client.get("/")
    assert resp.status_code == 200
```

```python
from litestar.testing import TestClient


def test_index(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
```

### `create_test_client` and `create_async_test_client`

For isolated route handler, controller, or router tests without bootstrapping the full application factory, use `create_async_test_client(route_handlers=..., **litestar_and_client_kwargs)` (or `create_test_client` for sync tests). Both build a `Litestar` instance and return a configured test client.

```python
import pytest
from litestar import get
from litestar.testing import create_async_test_client


@get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@pytest.mark.anyio
async def test_health_check() -> None:
    async with create_async_test_client(route_handlers=health_check) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
```

### anyio vs pytest-asyncio Setup

```python
# conftest.py
import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
```

Prefer `@pytest.mark.anyio` because Litestar's internal concurrency model is built on AnyIO. Do not mix `@pytest.mark.anyio` and `@pytest.mark.asyncio` in the same test module.

### App + Lifespan Fixture

```python
# conftest.py
from collections.abc import AsyncGenerator
import pytest
from litestar import Litestar
from litestar.testing import AsyncTestClient

from app import create_app


@pytest.fixture
async def app() -> Litestar:
    return create_app()


@pytest.fixture
async def async_client(app: Litestar) -> AsyncGenerator[AsyncTestClient[Litestar], None]:
    async with AsyncTestClient(app=app) as client:
        yield client
```

`async with AsyncTestClient(...)` enters `LifeSpanHandler`, firing `on_startup` / `on_shutdown` hooks and plugin `lifespan` context managers (Vite, SAQ, SQLAlchemy, Channels, etc.). Without the context manager, `LifeSpanHandler` is never entered and startup/shutdown hooks never run.

### Mocking Guards & Overriding DI Dependencies (Match Your Stack)

Guards are functions of `(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None | Awaitable[None]`. Test the real guard with fake identity or authorization providers, or unit-test the guard directly with `RequestFactory`. Build a fresh app with replacement providers; Litestar has no mutable `app.dependency_overrides` registry.

- **Option A — Litestar Built-in DI (`Provide` + `NamedDependency`)**: Pass replacement `Provide` entries to `create_app(dependencies=...)` or `create_async_test_client(..., dependencies=...)`. Handler parameters resolved by name must use `NamedDependency[T]`. For synchronous test providers, always specify `sync_to_thread=False` (or `True`) to avoid `LitestarWarning`.
- **Option B — Dishka DI (`Provider` + `make_async_container`)**: Subclass `Provider` in tests and pass the test provider *after* `LitestarProvider()` and production providers in `make_async_container(LitestarProvider(), AppProvider(), FakeEmailProvider(mock_email))` — later providers override earlier ones for matching return types. Route handlers using `FromDishka[T]` must be decorated with `@inject` (or `@inject_websocket`, or registered on a `DishkaRouter`) before calling `setup_dishka(container=container, app=app)`. See [Async Testing](references/async_testing.md) for full `FakeEmailProvider` and `dishka_client` fixture patterns.

```python
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from litestar import post
from litestar.di import NamedDependency, Provide
from litestar.testing import AsyncTestClient, create_async_test_client


@post("/notify")
async def notify_handler(email_service: NamedDependency[AsyncMock]) -> dict[str, bool]:
    await email_service.send("user@example.com")
    return {"sent": True}


@pytest.fixture
async def client_with_email() -> AsyncGenerator[tuple[AsyncTestClient, AsyncMock], None]:
    fake_email = AsyncMock()
    async with create_async_test_client(
        route_handlers=[notify_handler],
        dependencies={
            "email_service": Provide(lambda: fake_email, sync_to_thread=False),
        },
    ) as client:
        yield client, fake_email
```

### Session Testing (`set_session_data` and `get_session_data`)

Pass the same `session_config` (`ServerSideSessionConfig` or `CookieBackendConfig`) to both `middleware=[session_config.middleware]` and `session_config=session_config` on the test client (omitting `session_config` on the client raises `ImproperlyConfiguredException`). On `AsyncTestClient`, `await client.set_session_data(data)` and `await client.get_session_data()` are **async**; on `TestClient`, they are **sync**.

```python
import pytest
from litestar import Request, get, post
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.testing import create_async_test_client

session_config = ServerSideSessionConfig()


@get("/me")
async def read_session(request: Request) -> dict[str, str]:
    return dict(request.session)


@post("/login")
async def write_session(request: Request, data: dict[str, str]) -> None:
    request.session["user_id"] = data["user_id"]


@pytest.mark.anyio
async def test_session_roundtrip() -> None:
    async with create_async_test_client(
        route_handlers=[read_session, write_session],
        middleware=[session_config.middleware],
        session_config=session_config,
    ) as client:
        await client.set_session_data({"user_id": "u-123"})
        assert (await client.get("/me")).json() == {"user_id": "u-123"}
        await client.post("/login", json={"user_id": "u-456"})
        assert await client.get_session_data() == {"user_id": "u-456"}
```

### WebSocket, SSE (`ServerSentEvent`), and `ChannelsPlugin` Testing

- **WebSockets (`websocket_connect`)**: On `AsyncTestClient`, `websocket_connect` is `async def` (must be awaited), while the returned `WebSocketTestSession` is always a **synchronous** context manager (`with await client.websocket_connect(...) as ws:`) with synchronous methods (`ws.send_json(...)`, `ws.receive_json(...)`, `ws.close(...)`). Server-initiated close causes `ws.receive*()` to raise `litestar.exceptions.WebSocketDisconnect`.
- **SSE (`ServerSentEvent`)**: Stream events with `async with client.stream("GET", "/sse") as resp:` and iterate `resp.aiter_lines()`.
- **`ChannelsPlugin`**: Configure `ChannelsPlugin(backend=MemoryChannelsBackend(), channels=["alerts"], create_ws_route_handlers=True)` and enter `async with create_async_test_client(plugins=[channels_plugin]) as client:`. Publish via `channels_plugin.publish(data, channels=["alerts"])` and consume via `websocket_connect`.

```python
from collections.abc import AsyncGenerator
import pytest
from litestar import get, websocket_listener
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend
from litestar.response.sse import ServerSentEvent, ServerSentEventMessage
from litestar.testing import create_async_test_client


@websocket_listener("/ws")
async def echo_ws(data: dict[str, str]) -> dict[str, str]:
    return {"echo": data["msg"]}


@get("/events")
async def stream_events() -> ServerSentEvent:
    async def generator() -> AsyncGenerator[ServerSentEventMessage, None]:
        yield ServerSentEventMessage(data="ready", event="status")

    return ServerSentEvent(generator())


@pytest.mark.anyio
async def test_ws_sse_and_channels() -> None:
    channels = ChannelsPlugin(backend=MemoryChannelsBackend(), channels=["alerts"], create_ws_route_handlers=True)
    async with create_async_test_client(route_handlers=[echo_ws, stream_events], plugins=[channels]) as client:
        with await client.websocket_connect("/ws") as ws:
            ws.send_json({"msg": "hello"})
            assert ws.receive_json() == {"echo": "hello"}

        async with client.stream("GET", "/events") as resp:
            lines = [line async for line in resp.aiter_lines() if line]
            assert lines == ["event: status", "data: ready"]

        with await client.websocket_connect("/alerts") as ws:
            channels.publish({"msg": "fired"}, channels=["alerts"])
            assert ws.receive_json() == {"msg": "fired"}
```

### Unit Testing with `RequestFactory` & Live Subprocess Clients

- **`RequestFactory`**: Construct real `litestar.connection.Request` instances for unit-testing Guards or dependencies without an ASGI transport (`factory = RequestFactory(); req = factory.get("/admin", user={"role": "viewer"})`). In Litestar, `connection.app` reads `request.scope["litestar_app"]` (not `request.scope["app"]`); `RequestFactory` populates `scope["litestar_app"]` automatically.
- **`subprocess_async_client` / `subprocess_sync_client`**: Verify `litestar --app <app> run` CLI startup and real socket binding via `async with subprocess_async_client(workdir=tmp_path, app="main:app") as client:`. See [Async Testing](references/async_testing.md) for complete examples.

### Integration with pytest-databases

Combine `pytest-databases` fixtures with the app fixture. See `../pytest-databases/SKILL.md`.

```python
# conftest.py
pytest_plugins = ["pytest_databases.docker.postgres"]


@pytest.fixture
async def app(postgres_service) -> Litestar:
    from app import create_app
    from app.config import Settings

    settings = Settings(
        database_url=f"postgresql+asyncpg://{postgres_service.user}:{postgres_service.password}@{postgres_service.host}:{postgres_service.port}/{postgres_service.database}"
    )
    return create_app(settings=settings)
```

The `postgres_service` fixture starts a Postgres container. Inject its connection details into the app config.

### Request Bodies

| Body Type | Pass via |
| --- | --- |
| JSON | `client.post("/", json={...})` |
| Form | `client.post("/", data={...})` |
| Multipart (file upload) | `client.post("/", files={"file": ("name.txt", b"content", "text/plain")})` |
| Raw bytes | `client.post("/", content=b"...")` |
| Custom content-type | `client.post("/", content=b"...", headers={"Content-Type": "..."})` |

```python
async def test_create_user(async_client: AsyncTestClient) -> None:
    resp = await async_client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Alice"
```

### Headers, Cookies, Auth, HTMX, and Response Assertions

```python
resp = await async_client.get(
    "/items/list",
    headers={"Authorization": "Bearer token", "HX-Request": "true", "HX-Target": "#item-list"},
    cookies={"session": "abc123"},
)
assert resp.status_code == 200
assert "HX-Trigger" in resp.headers
assert "<ul" in resp.text
```

### Parametrize

```python
import pytest


@pytest.mark.parametrize(
    "payload, expected_status",
    [
        ({"name": "valid", "email": "a@b.co"}, 201),
        ({"name": "", "email": "a@b.co"}, 400),
        ({"name": "valid", "email": "not-email"}, 400),
    ],
)
@pytest.mark.anyio
async def test_create_user_validation(async_client, payload, expected_status):
    resp = await async_client.post("/api/users", json=payload)
    assert resp.status_code == expected_status
```

### Coverage

```bash
pytest --cov=src --cov-report=html
pytest --cov=src --cov-fail-under=90
```

<workflow>

## Workflow

### Step 1: Set Up anyio Backend

Add `anyio_backend` fixture to `conftest.py` returning `"asyncio"`. Mark async tests with `@pytest.mark.anyio`.

### Step 2: App + Client Fixtures

Build an `app` fixture that returns a fresh `Litestar` instance per test (or per session if no shared state). Build an `async_client` fixture that wraps the app in `AsyncTestClient` via `async with` (or use `create_async_test_client` for isolated handler/controller tests).

### Step 3: Add Database Fixtures

If the app talks to a DB, layer in `pytest-databases` (`postgres_service`, `mysql_service`, etc.) and pass connection details into the app config. See `../pytest-databases/SKILL.md`.

### Step 4: Override DI for Externals

Mock `EmailService`, HTTP clients, and other side-effect-laden dependencies by constructing a fresh app or test client with replacement `Provide` instances (or a Dishka override `Provider` passed to `make_async_container`). Avoid real network calls in tests.

### Step 5: Test Guards and Sessions

Build a fresh app with fake identity providers, use `RequestFactory` to unit-test Guards directly, and pass `session_config` to the test client when seeding or asserting session state via `set_session_data` / `get_session_data`.

### Step 6: Write Tests

- One assertion concern per test.
- Use `@pytest.mark.parametrize` for input variations.
- Use `AsyncTestClient` for new code (`with await client.websocket_connect(...) as ws:` for WebSockets).
- Include HTMX / Inertia headers when testing those paths.

### Step 7: Verify Coverage

`pytest --cov=src --cov-fail-under=90`. Cover handlers, services, Guards, and at least one happy-path + one error-path per route.

</workflow>

<guardrails>

## Guardrails

- **Use `@pytest.mark.anyio` for new Litestar async tests** — keep `pytest-asyncio` only when a project already uses it explicitly, and never mix auto modes.
- **Always enter `AsyncTestClient` / `TestClient` as a context manager** — without `async with` / `with`, `LifeSpanHandler` never enters and plugin lifespans (Vite, SAQ, SQLAlchemy) do not run.
- **Prefer `AsyncTestClient` over `TestClient`** for new tests — the async client matches Litestar's runtime model.
- **Pass `session_config` to the client when using `get_session_data` / `set_session_data`** — omitting `session_config` raises `ImproperlyConfiguredException`.
- **Await `websocket_connect` on `AsyncTestClient`, then enter `WebSocketTestSession` with sync `with`** — `with await async_client.websocket_connect("/ws") as ws:`; `WebSocketTestSession` methods (`send_json`, `receive_json`, etc.) are synchronous.
- **Mock side effects via DI override**, not patching — keeps tests isolated from import order and global state.
- **Build a fresh app for dependency replacements** — Litestar has no mutable dependency-override registry, and shared app mutation races under parallel tests.
- **Use `pytest-databases` for real DB testing** — never mock SQLAlchemy / sqlspec internals; assertions on mocked queries don't catch real bugs.
- **Function-based tests** — no class-based test containers unless absolutely needed for shared setup.
- **One assertion concern per test** — failures should pinpoint a single behavior.
- **Don't share state between tests** — fresh app + fresh DB per test (or per module with explicit cleanup).
- **Test the HTMX path with `HX-Request: true`** — handlers that branch on `request.htmx` need both branches covered.
- **Mock email via `backend="memory"` / `InMemoryBackend`** — see `../litestar-email/SKILL.md`.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering Litestar tests, verify:

- [ ] `anyio_backend` fixture returns `"asyncio"`
- [ ] Async tests use `@pytest.mark.anyio` (no mixed AnyIO / `pytest-asyncio` auto modes)
- [ ] `AsyncTestClient` / `create_async_test_client` is wrapped in `async with` (lifespan fires)
- [ ] `session_config` is passed to the test client whenever `get_session_data` / `set_session_data` is called
- [ ] WebSocket tests on `AsyncTestClient` use `with await client.websocket_connect(...) as ws:`
- [ ] DI dependencies (email, HTTP clients) are overridden via `Provide` or Dishka `Provider`, not patched
- [ ] DB-dependent tests use `pytest-databases` fixtures
- [ ] Guards either pass real auth, use a fresh app with fake identity providers, or are unit-tested with `RequestFactory`
- [ ] One assertion concern per test; parametrize for input variations
- [ ] HTMX-targeted handlers have tests with `HX-Request: true`
- [ ] Coverage gate (`--cov-fail-under`) is set in CI

</validation>

<example>

## Example

**Task:** Test an account creation endpoint that hits Postgres, sends a welcome email via SAQ, and is guarded by an auth check.

```python
# conftest.py
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from litestar import Litestar
from litestar.di import Provide
from litestar.testing import AsyncTestClient

pytest_plugins = ["pytest_databases.docker.postgres"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app(postgres_service) -> tuple[Litestar, AsyncMock]:
    from app import create_app
    from app.config import Settings

    fake_queue = AsyncMock()
    fake_task_queues = Mock()
    fake_task_queues.get.return_value = fake_queue

    async def provide_fake_task_queues() -> Mock:
        return fake_task_queues

    settings = Settings(
        database_url=(
            f"postgresql+asyncpg://{postgres_service.user}:{postgres_service.password}"
            f"@{postgres_service.host}:{postgres_service.port}/{postgres_service.database}"
        ),
    )
    return (
        create_app(
            settings=settings,
            dependencies={
                "task_queues": Provide(provide_fake_task_queues),
            },
        ),
        fake_queue,
    )


@pytest.fixture
async def async_client(
    app: tuple[Litestar, AsyncMock],
) -> AsyncGenerator[tuple[AsyncTestClient, AsyncMock], None]:
    test_app, fake_queue = app
    async with AsyncTestClient(app=test_app) as client:
        yield client, fake_queue
```

```python
# tests/test_accounts.py
import pytest


@pytest.mark.anyio
async def test_create_account_persists_and_queues_email(async_client):
    client, fake_queue = async_client

    resp = await client.post(
        "/api/accounts",
        json={"email": "alice@example.com", "name": "Alice"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    fake_queue.enqueue.assert_awaited_once()
    args, kwargs = fake_queue.enqueue.await_args
    assert args[0] == "send_welcome_email"
    assert kwargs["email"] == "alice@example.com"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload, expected_status",
    [
        ({"email": "valid@example.com", "name": "Valid"}, 201),
        ({"email": "", "name": "Valid"}, 400),
        ({"email": "valid@example.com", "name": ""}, 400),
    ],
)
async def test_create_account_validation(async_client, payload, expected_status):
    client, _ = async_client
    resp = await client.post("/api/accounts", json=payload)
    assert resp.status_code == expected_status
```

</example>

---

## References Index

- **[Async Testing](references/async_testing.md)** — anyio setup, async fixtures, `create_async_test_client`, session/WebSocket/`RequestFactory`/subprocess helpers, and common pitfalls.
- **[litestar](../litestar/SKILL.md)** — Litestar fundamentals.
- **[pytest-databases](../pytest-databases/SKILL.md)** — Container-based DB fixtures.
- **[polyfactory](../polyfactory/SKILL.md)** — Model, dataclass, and msgspec test data factories.
- **[litestar-email](../litestar-email/SKILL.md)** — `backend="memory"` and `InMemoryBackend` for email tests.
- **[litestar-saq](../litestar-saq/SKILL.md)** — Mocking task queues.

## Official References

- <https://docs.litestar.dev/2/usage/testing.html>
- <https://github.com/litestar-org/litestar>
- <https://docs.pytest.org/en/stable/>
- <https://anyio.readthedocs.io/en/stable/testing.html>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Testing](../litestar-styleguide/references/testing.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
