# End-to-End Example — Task Feature (vertical slice)

A complete feature using every canonical pattern: Advanced Alchemy model + Repository Service, camelized msgspec DTOs, Guards, custom exceptions, `OffsetPagination`, Channels broadcast from a SAQ worker.

## Layer 1 — Model (`app/db/models/task.py`)

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class Task(UUIDAuditBase):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
```

## Layer 2 — Schemas (`app/domain/tasks/schemas.py`)

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

## Layer 3 — Service (`app/domain/tasks/services.py`)

```python
from __future__ import annotations

from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

from app.db.models import Task


class TaskRepository(SQLAlchemyAsyncRepository[Task]):
    model_type = Task


class TaskService(SQLAlchemyAsyncRepositoryService[Task]):
    repository_type = TaskRepository
```

## Layer 4 — Controller (`app/domain/tasks/controllers.py`)

```python
from __future__ import annotations

from uuid import UUID

from litestar import Controller, Request, get, post, patch, delete
from litestar.di import NamedDependency
from litestar.params import FromPath, SkipValidation  # Litestar >= 2.23
from msgspec import to_builtins
from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination

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
            *filters, owner_id=request.user.id,
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
        # Broadcast to the user's WS channel (from request context)
        await channels.wait_published(
            {"type": "task.created", "taskId": str(db_task.id)},
            f"user:{request.user.id}",
        )
        return tasks_service.to_schema(db_task, schema_type=Task)

    @patch("/{task_id:uuid}")
    async def update_task(
        self, task_id: FromPath[UUID], data: TaskUpdate,
        tasks_service: NamedDependency[TaskService], request: Request,
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

## Layer 5 — SAQ worker publishing back to WS clients

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

## Layer 6 — App wiring (`app/server/app.py`)

```python
from __future__ import annotations

from litestar import Litestar
from litestar.di import Provide
from litestar_granian import GranianPlugin
from litestar_saq import SAQPlugin, SAQConfig, QueueConfig
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig
from redis.asyncio import Redis

from app.domain.tasks.controllers import TaskController
from app.domain.tasks.services import TaskService
from app.domain.tasks.jobs import notify_task_due_job
from app.lib.exceptions import ApplicationError, application_exception_handler
from app.lib.settings import get_settings


settings = get_settings()

channels = ChannelsPlugin(
    backend=RedisChannelsPubSubBackend(redis=Redis.from_url(settings.redis.url)),
    channels=["user:*"],
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
    ws_handler_base_path="/ws",
)

app = Litestar(
    route_handlers=[TaskController],
    dependencies={
        "tasks_service": Provide(lambda db_session: TaskService(session=db_session)),
    },
    exception_handlers={ApplicationError: application_exception_handler},
    plugins=[
        GranianPlugin(),
        SQLAlchemyPlugin(config=SQLAlchemyAsyncConfig(connection_string=settings.database.url)),
        SAQPlugin(config=SAQConfig(
            use_server_lifespan=True,
            queue_configs=[QueueConfig(
                name="default",
                dsn=settings.redis.url,
                jobs=[notify_task_due_job],
            )],
        )),
        channels,
    ],
)
```

## What This Exercises

Canonical layering (model → service → schema → controller → jobs → app), `SQLAlchemyAsyncRepositoryService` for data access, `OffsetPagination` + filter deps, camelized DTOs, custom `NotFoundError`, Guards at Controller level, cross-process Channel broadcast from both request handler and SAQ worker. Every guardrail from the parent `SKILL.md` `<guardrails>` section is in play.

## Cross-references

- Repository service patterns: [services.md](../../litestar-data-services/references/services.md)
- Filter dependency catalog: [pagination.md](../../litestar-data-services/references/pagination.md)
- Channel pub/sub from SAQ workers: [websockets.md](../../litestar-realtime/references/websockets.md)
- App wiring with plugins: [plugins.md](../../litestar-plugins/references/plugins.md), [litestar-app.md](../../litestar-deployment/references/litestar-app.md)
- Exception hierarchy: [exceptions.md](../../litestar-exceptions/references/exceptions.md)
