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
import pytest
from litestar.testing import AsyncTestClient

@pytest.fixture
async def async_client(app) -> AsyncTestClient:
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

### `AsyncTestClient` lifespan

`AsyncTestClient(app)` does NOT fire lifespan unless used as `async with`. Always:

```python
async with AsyncTestClient(app=app) as client:
    ...
```

Without this, plugin lifespans (Vite, SAQ, SQLAlchemy session pool) never start.

### `create_test_client` / `create_async_test_client`

For one-off sync tests with a tiny ad-hoc app, use `create_test_client`:

```python
from litestar.testing import create_test_client
from litestar import get

@get("/")
async def handler() -> dict:
    return {"ok": True}

def test_inline_app():
    with create_test_client([handler]) as client:
        resp = client.get("/")
        assert resp.status_code == 200
```

For async client tests, use `create_async_test_client`:

```python
from litestar.testing import create_async_test_client


@pytest.mark.anyio
async def test_inline_async_app():
    async with create_async_test_client([handler]) as client:
        resp = await client.get("/")
        assert resp.status_code == 200
```
