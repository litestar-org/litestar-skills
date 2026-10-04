# Domain-Clustered Layout and End-to-End Vertical Slice

Cluster code by business domain — each domain owns its schemas, services, controllers, guards, and jobs in a single folder. Shared infrastructure lives in `lib/`.

## Canonical Layout

```text
src/app/
├── domain/
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── controllers.py     # AccountController, UserController
│   │   ├── services.py        # AccountService, UserService
│   │   ├── schemas.py         # camelized msgspec DTOs
│   │   ├── guards.py          # requires_active_user, requires_superuser
│   │   ├── deps.py            # Provide() / Dishka providers
│   │   └── jobs.py            # SAQ tasks for this domain
│   ├── teams/
│   │   ├── controllers.py     # TeamController, MembershipController
│   │   └── ...
│   └── tasks/
│       └── ...
├── db/
│   ├── models/                # SQLAlchemy / advanced-alchemy models
│   └── migrations/            # Alembic
├── lib/                       # cross-cutting shared infrastructure
│   ├── exceptions.py          # ApplicationError hierarchy
│   ├── schema.py              # CamelizedBaseStruct base
│   ├── settings.py            # @dataclass settings
│   ├── deps.py                # shared filter dependencies
│   └── serialization.py
└── server/
    ├── app.py                 # Litestar() instance
    ├── plugins.py             # GranianPlugin, SAQPlugin, etc.
    └── routers.py             # Router composition
```

Refs: [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/app/`), [litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia) (`src/app/`).

## Why Domain Clustering

- **Locality of change.** Adding a field to `User` touches `domain/accounts/{schemas,services,controllers}.py` — three files in one folder, not three folders.
- **Bounded contexts.** Each domain folder is a candidate for extraction into a separate service later if needed.
- **Test colocation.** `tests/domain/accounts/test_users.py` mirrors source layout exactly.
- **Plugin auto-discovery.** Litestar Autowire walks configured domain packages to register controllers and listeners automatically.

## Shared `lib/`

`lib/` is for code that doesn't belong to any single domain:

- **`lib/exceptions.py`** — `ApplicationError` hierarchy (see [exceptions.md](exceptions.md))
- **`lib/schema.py`** — `CamelizedBaseStruct` and shared msgspec primitives (see [dtos.md](dtos.md))
- **`lib/settings.py`** — `@dataclass` config (see [settings.md](settings.md))
- **`lib/deps.py`** — common filter / pagination dependencies reused across Controllers

When something in `lib/` becomes domain-specific, move it to that domain's folder.

## Multi-tenant Workspaces

For workspace-scoped apps, the workspace dimension lives in guards and channel names — not in folder layout:

```python
# domain/workspaces/guards.py
async def requires_workspace_membership(connection, _) -> None: ...


# domain/workspaces/controllers.py
class WorkspaceController(Controller):
    path = "/api/workspaces/{workspace_id:uuid}"
    guards = [requires_active_user, requires_workspace_membership]
```

Channels follow the same scoping (`workspace:{id}:events`). See [websockets.md](websockets.md) and [channels-and-sse.md](channels-and-sse.md).

---

## End-to-End Example — Task Feature (Vertical Slice)

A complete feature using every canonical pattern: Advanced Alchemy model + Repository Service, camelized msgspec DTOs, Guards, custom exceptions, `OffsetPagination`, and Channels broadcast from a SAQ worker.

### Layer 1 — Model (`app/db/models/task.py`)

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class Task(UUIDAuditBase):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
```

### Layer 2 — Schemas (`app/domain/tasks/schemas.py`)

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.lib.schema import CamelizedBaseStruct


class Task(CamelizedBaseStruct):
    id: UUID
    title: str
    done: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(CamelizedBaseStruct):
    title: str


class TaskUpdate(CamelizedBaseStruct):
    title: str | None = None
    done: bool | None = None
```

### Layer 3 — Service (`app/domain/tasks/services.py`)

```python
from __future__ import annotations

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

from app.db.models import Task


class TaskRepository(SQLAlchemyAsyncRepository[Task]):
    model_type = Task


class TaskService(SQLAlchemyAsyncRepositoryService[Task]):
    repository_type = TaskRepository
```

### Layer 4 — Controller (`app/domain/tasks/controllers.py`)

```python
from __future__ import annotations

from uuid import UUID

from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination
from litestar import Controller, Request, delete, get, patch, post
from litestar.di import NamedDependency
from litestar.params import FromPath, SkipValidation
from msgspec import to_builtins

from app.domain.accounts.guards import requires_active_user
from app.domain.tasks.schemas import Task, TaskCreate, TaskUpdate
from app.domain.tasks.services import TaskService
from app.lib.exceptions import NotFoundError
from app.server.plugins import channels


class TaskController(Controller):
    path = "/api/tasks"
    guards = [requires_active_user]
    tags = ["Tasks"]
    dependencies = create_service_dependencies(
        TaskService,
        key="tasks_service",
        filters={
            "id_filter": UUID,
            "pagination_type": "limit_offset",
            "pagination_size": 20,
            "search": "title",
            "created_at": True,
        },
    )

    @get("/")
    async def list_tasks(
        self,
        tasks_service: NamedDependency[TaskService],
        request: Request,
        filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> OffsetPagination[Task]:
        results, total = await tasks_service.get_many_and_count(
            *filters,
            owner_id=request.user.id,
        )
        return tasks_service.to_schema(results, total, filters=filters, schema_type=Task)

    @get("/{task_id:uuid}")
    async def get_task(
        self,
        task_id: FromPath[UUID],
        tasks_service: NamedDependency[TaskService],
        request: Request,
    ) -> Task:
        db_task = await tasks_service.get_one_or_none(id=task_id, owner_id=request.user.id)
        if db_task is None:
            raise NotFoundError(detail="Task not found")
        return tasks_service.to_schema(db_task, schema_type=Task)

    @post("/")
    async def create_task(
        self,
        data: TaskCreate,
        tasks_service: NamedDependency[TaskService],
        request: Request,
    ) -> Task:
        db_task = await tasks_service.create({**to_builtins(data), "owner_id": request.user.id})
        await channels.wait_published(
            {"type": "task.created", "taskId": str(db_task.id)},
            f"user:{request.user.id}",
        )
        return tasks_service.to_schema(db_task, schema_type=Task)

    @patch("/{task_id:uuid}")
    async def update_task(
        self,
        task_id: FromPath[UUID],
        data: TaskUpdate,
        tasks_service: NamedDependency[TaskService],
        request: Request,
    ) -> Task:
        db_task = await tasks_service.update(
            {**to_builtins(data), "id": task_id},
            owner_id=request.user.id,
        )
        return tasks_service.to_schema(db_task, schema_type=Task)

    @delete("/{task_id:uuid}")
    async def delete_task(
        self,
        task_id: FromPath[UUID],
        tasks_service: NamedDependency[TaskService],
        request: Request,
    ) -> None:
        await tasks_service.delete(task_id, owner_id=request.user.id)
```

### Layer 5 — SAQ Worker Publishing Back to WS Clients

```python
# app/domain/tasks/jobs.py
from __future__ import annotations

from saq import Context

from app.server.plugins import channels


async def notify_task_due_job(ctx: Context, *, task_id: str, owner_id: str) -> None:
    await channels.wait_published(
        {"type": "task.due", "taskId": task_id},
        f"user:{owner_id}",
    )
```

### Layer 6 — App Wiring (`app/server/app.py`)

```python
from __future__ import annotations

from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from litestar import Litestar
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from litestar_granian import GranianPlugin
from litestar_saq import QueueConfig, SAQConfig, SAQPlugin
from redis.asyncio import Redis

from app.domain.tasks.controllers import TaskController
from app.domain.tasks.jobs import notify_task_due_job
from app.lib.exceptions import ApplicationError, application_exception_handler
from app.lib.settings import get_settings

settings = get_settings()

channels = ChannelsPlugin(
    backend=RedisChannelsPubSubBackend(redis=Redis.from_url(settings.redis.url)),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
    ws_handler_base_path="/ws",
)

app = Litestar(
    route_handlers=[TaskController],
    exception_handlers={ApplicationError: application_exception_handler},
    plugins=[
        GranianPlugin(),
        SQLAlchemyPlugin(config=SQLAlchemyAsyncConfig(connection_string=settings.database.url)),
        SAQPlugin(
            config=SAQConfig(
                use_server_lifespan=True,
                queue_configs=[
                    QueueConfig(
                        name="default",
                        dsn=settings.redis.url,
                        tasks=[notify_task_due_job],
                    )
                ],
            )
        ),
        channels,
    ],
)
```

## Cross-References

- Package discovery via Litestar Autowire: [litestar-autowire](../../litestar-autowire/SKILL.md)
- Guard composition for tenant isolation: [auth-and-guards.md](auth-and-guards.md)
- Repository service patterns: [services-and-repos.md](services-and-repos.md)
- Filter dependency catalog: [filters-and-pagination.md](filters-and-pagination.md)
- Channel pub/sub and WebSockets: [channels-and-sse.md](channels-and-sse.md), [websockets.md](websockets.md)
- App wiring with plugins: [plugins.md](plugins.md), [litestar-app.md](../../litestar-deployment/references/litestar-app.md)
- Exception hierarchy: [exceptions.md](exceptions.md)
