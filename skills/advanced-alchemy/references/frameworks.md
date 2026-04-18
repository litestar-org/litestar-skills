# Framework Integrations (Beyond Litestar)

## Overview

Advanced Alchemy supports multiple Python web frameworks through dedicated extension modules. Each integration provides a plugin that manages engine creation, session lifecycle, and dependency injection according to the framework's conventions.

```text
advanced_alchemy.extensions.litestar   → Litestar (see litestar_plugin.md)
advanced_alchemy.extensions.fastapi    → FastAPI / Starlette
advanced_alchemy.extensions.flask      → Flask
advanced_alchemy.extensions.sanic      → Sanic
advanced_alchemy.extensions.starlette  → Starlette (standalone)
```

---

## FastAPI Integration

### Plugin Setup

```python
from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)

app = FastAPI()
alchemy = AdvancedAlchemy(config=db_config, app=app)
```

`AdvancedAlchemy` is the public extension class for FastAPI. Pass the FastAPI instance via `app=` (or call `alchemy.init_app(app)` later) and it wires up engine startup/shutdown plus per-request session management. `commit_mode="autocommit"` commits on success and rolls back on exception; use `"manual"` (the default) to manage transactions yourself.

### Lifespan Handler

`AdvancedAlchemy` exposes a context manager for use with FastAPI's lifespan pattern:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)
alchemy = AdvancedAlchemy(config=db_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with alchemy.lifespan(app):
        yield


app = FastAPI(lifespan=lifespan)
alchemy.init_app(app)
```

### Dependency Injection with Depends()

`provide_session` is a method on the `AdvancedAlchemy` instance — call it to obtain a per-config FastAPI dependency:

```python
from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def provide_user_service(
    session: AsyncSession = Depends(alchemy.provide_session()),
) -> UserService:
    return UserService(session=session)


@router.get("/users")
async def list_users(
    service: UserService = Depends(provide_user_service),
) -> list[dict]:
    results = await service.list()
    return [{"id": str(r.id), "email": r.email} for r in results]


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    service: UserService = Depends(provide_user_service),
) -> dict:
    user = await service.get(user_id)
    return {"id": str(user.id), "email": user.email}


@router.post("/users")
async def create_user(
    data: dict,
    service: UserService = Depends(provide_user_service),
) -> dict:
    user = await service.create(data)
    return {"id": str(user.id), "email": user.email}
```

### FastAPI with Sync Sessions

```python
from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    SQLAlchemySyncConfig,
)

sync_config = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)

alchemy = AdvancedAlchemy(config=sync_config, app=app)
```

---

## Flask Integration

### Plugin Setup

```python
from flask import Flask
from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    SQLAlchemySyncConfig,
)


db_config = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)

app = Flask(__name__)
alchemy = AdvancedAlchemy(config=db_config, app=app)
```

### App Context Session Management

Flask manages sessions via the application context. `AdvancedAlchemy` hooks into Flask's `teardown_appcontext` to handle session cleanup, and exposes `get_session()` (or `get_sync_session()`) on the extension instance.

```python
from flask import Flask
from sqlalchemy.orm import Session


@app.route("/users")
def list_users():
    session: Session = alchemy.get_sync_session()
    service = UserService(session=session)
    results = service.list()  # Sync operations in Flask
    return [{"id": str(r.id), "email": r.email} for r in results]
```

### Async Flask (Flask 2.0+)

```python
from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)

async_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)

alchemy = AdvancedAlchemy(config=async_config, app=app)
```

---

## Starlette Integration

### Direct ASGI Integration

For Starlette applications without FastAPI:

```python
from starlette.applications import Starlette
from starlette.routing import Route
from advanced_alchemy.extensions.starlette import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)


async def list_users(request):
    from starlette.responses import JSONResponse
    session = request.state.session
    service = UserService(session=session)
    results = await service.list()
    return JSONResponse([{"id": str(r.id)} for r in results])


app = Starlette(routes=[Route("/users", list_users)])
alchemy = AdvancedAlchemy(config=db_config, app=app)
```

### Middleware-Based Session

The Starlette plugin injects the session into `request.state`, making it available to all route handlers without explicit dependency injection.

---

## Sanic Integration

### Plugin Setup

```python
from sanic import Sanic
from advanced_alchemy.extensions.sanic import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,
)


db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost:5432/mydb",
    commit_mode="autocommit",
)

app = Sanic("MyApp")
alchemy = AdvancedAlchemy(config=db_config, app=app)
```

### Route Handlers

```python
from sanic import json
from sanic.request import Request


@app.get("/users")
async def list_users(request: Request):
    session = request.ctx.session
    service = UserService(session=session)
    results = await service.list()
    return json([{"id": str(r.id), "email": r.email} for r in results])
```

- Sanic uses `request.ctx` for request-scoped state
- The plugin manages session creation and teardown per request

---

## Common Patterns Across All Frameworks

### Plugin Configuration

All framework integrations follow the same configuration pattern. The non-Litestar integrations expose a single class — `AdvancedAlchemy` — that wires engines, sessions, and lifecycle hooks into the host framework:

```python
from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    SQLAlchemyAsyncConfig,   # or SQLAlchemySyncConfig
    EngineConfig,
)

config = SQLAlchemyAsyncConfig(
    connection_string="...",
    engine_config=EngineConfig(
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=300,
        echo=False,
    ),
    commit_mode="autocommit",
)

alchemy = AdvancedAlchemy(config=config, app=app)
```

For Litestar, use `SQLAlchemyPlugin(config=...)` — see `litestar_plugin.md`.

### Session Injection

Every integration ensures one session per request with automatic cleanup:

| Framework | Session Location | Cleanup Mechanism |
| --- | --- | --- |
| Litestar | DI (`db_session` parameter) | `commit_mode` middleware |
| FastAPI | `Depends(alchemy.provide_session())` | ASGI middleware |
| Flask | `alchemy.get_sync_session()` / app context | `teardown_appcontext` |
| Starlette | `request.state.session` | ASGI middleware |
| Sanic | `request.ctx.session` | Request middleware |

### Transaction Management

All integrations support the same `commit_mode` settings on the config class:

- `commit_mode="autocommit"`: auto-commits if no exception, rolls back on error
- `commit_mode="autocommit_include_redirect"`: same behavior, also commits on 3xx redirect responses
- `commit_mode="manual"` (default): omit autocommit and manage `session.commit()` / `session.rollback()` yourself

### Multiple Database Support

All integrations accept a list of configs for multi-database setups:

```python
primary = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/primary",
    commit_mode="autocommit",
)

analytics = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://localhost/analytics",
    commit_mode="autocommit",
    bind_key="analytics",
)

alchemy = AdvancedAlchemy(config=[primary, analytics], app=app)
```

---

## Feature Comparison

| Feature | Litestar | FastAPI | Flask | Starlette | Sanic |
| --- | --- | --- | --- | --- | --- |
| Async sessions | Yes | Yes | Yes (Flask 2.0+) | Yes | Yes |
| Sync sessions | Yes | Yes | Yes | Yes | No |
| Auto-commit handler | Yes | Yes | Yes | Yes | Yes |
| DTOs (SQLAlchemyDTO) | Yes | No | No | No | No |
| Filter dependencies | Yes | Manual | Manual | Manual | Manual |
| CLI migrations | Yes (`litestar db`) | `alchemy` CLI | `alchemy` CLI | `alchemy` CLI | `alchemy` CLI |
| Lifespan integration | Built-in | `plugin.lifespan()` | `init_app()` | `init_app()` | `init_app()` |
| Multiple databases | Yes | Yes | Yes | Yes | Yes |
| Engine config | Yes | Yes | Yes | Yes | Yes |
| Service layer | Yes | Yes | Yes | Yes | Yes |
| Repository pattern | Yes | Yes | Yes | Yes | Yes |

### Key Differences

- **Litestar** has the deepest integration: native DTOs, `create_filter_dependencies()`, and built-in CLI migration commands
- **FastAPI** uses standard `Depends()` for DI and requires explicit `provide_session` dependency
- **Flask** is typically sync-first; async support requires Flask 2.0+ with an async-capable server
- **Starlette** provides the most minimal integration — session on `request.state`, no DI framework
- **Sanic** uses `request.ctx` for request-scoped state, fully async

### Migration Note

The service and repository layers (`SQLAlchemyAsyncRepositoryService`, `SQLAlchemyAsyncRepository`, etc.) are framework-agnostic. Only the session injection and plugin setup differ between frameworks. Switching frameworks requires changing only the plugin and dependency wiring, not the business logic.
