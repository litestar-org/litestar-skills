# Async Testing with pytest (anyio)

Litestar supports AnyIO for async tests. Prefer `@pytest.mark.anyio` in Litestar projects so tests can run under the same async abstraction used by the framework.

## Setup

```bash
uv add --dev anyio pytest
```

```python
# conftest.py
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

Or via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
anyio_backend = "asyncio"
```

## Basic Async Test

```python
import pytest


@pytest.mark.anyio
async def test_async_operation():
    result = await some_async_function()
    assert result == expected_value
```

## Async Fixture Patterns

### Simple Async Fixture

```python
from collections.abc import AsyncGenerator
import pytest
from litestar import Litestar
from litestar.testing import AsyncTestClient


@pytest.fixture
async def async_client(app: Litestar) -> AsyncGenerator[AsyncTestClient[Litestar], None]:
    async with AsyncTestClient(app=app) as client:
        yield client
```

### Async Generator Fixtures

```python
from collections.abc import AsyncGenerator
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
    await engine.dispose()
```

### Session-Scoped Async Fixtures

```python
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()
```

## Testing Async Context Managers

```python
@pytest.mark.anyio
async def test_async_context_manager():
    async with MyAsyncResource() as resource:
        assert resource.is_connected
        result = await resource.fetch("key")
        assert result is not None
    assert resource.is_closed


@pytest.mark.anyio
async def test_context_manager_cleanup_on_error():
    resource = MyAsyncResource()
    with pytest.raises(ValueError):
        async with resource:
            raise ValueError("intentional")
    assert resource.is_closed
```

### Mocking Async Context Managers

```python
from unittest.mock import AsyncMock, MagicMock


def make_async_cm(return_value):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.anyio
async def test_with_mocked_cm():
    mock_conn = MagicMock()
    mock_pool = make_async_cm(mock_conn)
    async with mock_pool as conn:
        assert conn is mock_conn
```

## Common Pitfalls

### Event Loop Conflicts

`RuntimeError: This event loop is already running` from mixing sync and async.

```python
# Bad
@pytest.mark.anyio
async def test_bad():
    import asyncio

    result = asyncio.run(some_coro())  # RuntimeError


# Good
@pytest.mark.anyio
async def test_good():
    result = await some_coro()
```

### Unawaited Coroutines

```python
# Bad - coroutine is truthy
@pytest.mark.anyio
async def test_sneaky_pass():
    result = some_async_function()  # missing await
    assert result  # passes incorrectly


# Good
@pytest.mark.anyio
async def test_correct():
    result = await some_async_function()
    assert result
```

Catch these in CI:

```toml
[tool.pytest.ini_options]
filterwarnings = ["error::RuntimeWarning"]
```

### Mixing pytest-asyncio and AnyIO

Do not enable both plugins in automatic mode. If your project already uses `pytest-asyncio`, keep modes explicit and do not mix `@pytest.mark.asyncio` and `@pytest.mark.anyio` in the same test module. New Litestar tests should use `@pytest.mark.anyio`.

### Fixture Scope

Session-scoped async fixtures need the `anyio_backend` fixture also at session scope:

```python
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
```

### Mixing Sync and Async Fixtures

Async fixtures may depend on sync fixtures, not the reverse. A sync test cannot directly consume an async fixture; use module/session-scope to pre-compute and access the resolved value.

## Litestar-specific

### `AsyncTestClient` and `TestClient` Lifespan

`AsyncTestClient(app)` and `TestClient(app)` require entering their context managers (`async with` / `with`) so `LifeSpanHandler` runs `on_startup` / `on_shutdown` hooks and `lifespan` context managers. Implicit lifespan startup without a context manager emits a `DeprecationWarning` and is removed in Litestar 3.0.

```python
async with AsyncTestClient(app=app) as client:
    ...
```

Without this, plugin lifespans (Vite, SAQ, SQLAlchemy session pool, Channels) never start or shut down cleanly.

### `create_test_client` / `create_async_test_client`

For one-off sync tests with a tiny ad-hoc app, use `create_test_client`:

```python
from litestar import get
from litestar.testing import create_test_client


@get("/")
async def handler() -> dict[str, bool]:
    return {"ok": True}


def test_inline_app() -> None:
    with create_test_client([handler]) as client:
        resp = client.get("/")
        assert resp.status_code == 200
```

For async client tests, use `create_async_test_client`:

```python
import pytest
from litestar.testing import create_async_test_client


@pytest.mark.anyio
async def test_inline_async_app() -> None:
    async with create_async_test_client([handler]) as client:
        resp = await client.get("/")
        assert resp.status_code == 200
```

Both helpers accept a single handler, `Controller` subclass, `Router`, or sequence of them as `route_handlers` (default `None`), plus keyword-only arguments matching `Litestar(...)` (`dependencies`, `guards`, `middleware`, `plugins`, `stores`, `state`, `on_startup`, `on_shutdown`, `lifespan`, `exception_handlers`, `dto`, `return_dto`, `template_config`, `static_files_config`, `cors_config`, `csrf_config`, `compression_config`, `allowed_hosts`, `response_cache_config`, `logging_config`, `openapi_config`, `opt`, `parameters`, `path`, `security`, `tags`, `signature_namespace`, `signature_types`, `type_encoders`, `request_class`, `response_class`, `websocket_class`, `response_cookies`, `response_headers`, `before_request`, `after_request`, `after_response`, `before_send`, `after_exception`, `on_app_init`, `listeners`, `cache_control`, `etag`, `include_in_schema`, `multipart_form_part_limit=1000`, `pdb_on_exception`, `experimental_features`, `debug=True`) and test-client options (`backend="asyncio"`, `backend_options=None`, `base_url="http://testserver.local"`, `raise_server_exceptions=True`, `root_path=""`, `session_config=None`, `timeout=None`).

### Dependency Replacements (Native `Provide` and Dishka)

Litestar does not expose a mutable dependency-override registry. Pass replacement providers while constructing a fresh test app:

```python
import pytest
from litestar import get
from litestar.di import NamedDependency, Provide
from litestar.testing import create_async_test_client


@get("/")
async def get_data(service: NamedDependency[Service]) -> dict[str, str]:
    return await service.fetch()


async def provide_fake_service() -> Service:
    return FakeService()


@pytest.mark.anyio
async def test_with_fake_service() -> None:
    async with create_async_test_client(
        [get_data],
        dependencies={
            "service": Provide(provide_fake_service),
        },
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
```

When using Dishka, pass a test `Provider` subclass after the production providers in `make_async_container(AppProvider(), TestProvider())` before calling `setup_dishka(container=container, app=app)`. For full-application tests, make the application factory accept a dependency map or extra Dishka providers and return a new `Litestar` instance. Never mutate a shared app between tests.

### Session Helpers (`set_session_data` / `get_session_data`)

Pass `session_config` (`ServerSideSessionConfig` or `CookieBackendConfig`) to both `middleware=[session_config.middleware]` and the test client's `session_config=session_config` parameter:

```python
import pytest
from litestar import Request, get
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.testing import create_async_test_client

session_config = ServerSideSessionConfig()


@get("/profile")
async def get_profile(request: Request) -> dict[str, str]:
    return {"user": request.session.get("user", "anonymous")}


@pytest.mark.anyio
async def test_session_helpers() -> None:
    async with create_async_test_client(
        route_handlers=[get_profile],
        middleware=[session_config.middleware],
        session_config=session_config,
    ) as client:
        await client.set_session_data({"user": "alice"})
        resp = await client.get("/profile")
        assert resp.json() == {"user": "alice"}
        assert await client.get_session_data() == {"user": "alice"}
```

### WebSocket Sessions (`websocket_connect` / `WebSocketTestSession`)

On `AsyncTestClient`, `websocket_connect` is `async def`, returning a `WebSocketTestSession` that is a **synchronous** context manager (`with await client.websocket_connect(...) as ws:`). On `TestClient`, `websocket_connect` is synchronous (`with client.websocket_connect(...) as ws:`).

```python
import pytest
from litestar import websocket_listener
from litestar.exceptions import WebSocketDisconnect
from litestar.testing import create_async_test_client


@websocket_listener("/ws")
async def chat_handler(data: str) -> str:
    return f"ack:{data}"


@pytest.mark.anyio
async def test_websocket_session() -> None:
    async with create_async_test_client(route_handlers=[chat_handler]) as client:
        with await client.websocket_connect("/ws") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "ack:ping"
```

Available `WebSocketTestSession` methods:

- `send(data, mode="text", encoding="utf-8")`, `send_text(data)`, `send_bytes(data)`, `send_json(data, mode="text")`, `send_msgpack(data)`
- `receive(block=True, timeout=None)`, `receive_text(block=True, timeout=None)`, `receive_bytes(block=True, timeout=None)`, `receive_json(mode="text", block=True, timeout=None)`, `receive_msgpack(block=True, timeout=None)`
- `close(code=WS_1000_NORMAL_CLOSURE)` — if the server closes the connection, `receive*()` raises `WebSocketDisconnect`.

### `RequestFactory` and Subprocess Clients

- Use `RequestFactory` (`from litestar.testing import RequestFactory`) to build `Request` objects (`.get()`, `.post()`, `.put()`, `.patch()`, `.delete()`) with `user`, `auth`, `session`, `state`, `headers`, `cookies`, `query_params`, `path_params`, and `data` for unit-testing Guards or dependencies directly without ASGI transport overhead.
- Use `subprocess_async_client(workdir, app, capture_output=True)` or `subprocess_sync_client(workdir, app, capture_output=True)` (`from litestar.testing import subprocess_async_client, subprocess_sync_client`) to boot `litestar --app <app> run` in a background subprocess and yield a live `httpx.AsyncClient` / `httpx.Client`.

## Tagged source

- [2.24 test-client helpers](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/testing/helpers.py)
- [2.24 RequestFactory](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/testing/request_factory.py)
- [2.24 WebSocketTestSession](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/testing/websocket_test_session.py)
- [2.24 dependency replacement guidance](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/onboarding/fastapi.rst)
