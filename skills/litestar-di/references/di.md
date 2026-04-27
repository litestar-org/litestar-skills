# Dependency Injection — `Provide()` and Dishka

Two paths: built-in `Provide()` for small/mid apps, Dishka for enterprise scope management. Don't default to Dishka — it's a scaling choice, not a style choice.

## Litestar Built-in DI (`Provide()`)

```python
from __future__ import annotations

from litestar import Litestar, Request
from litestar.di import Provide
from litestar.datastructures import State
from sqlalchemy.ext.asyncio import AsyncSession


async def provide_session(state: State) -> AsyncSession:
    return state.db_session


async def provide_current_user(request: Request, session: AsyncSession) -> User:
    token = request.headers.get("Authorization")
    return await authenticate(session, token)


async def provide_user_service(db_session: AsyncSession) -> UserService:
    return UserService(session=db_session)


app = Litestar(
    route_handlers=[...],
    dependencies={
        "db_session": Provide(provide_session),
        "current_user": Provide(provide_current_user),
        "users_service": Provide(provide_user_service),
    },
)
```

Resolution scopes:

- **app** (default for `Litestar(dependencies=...)`)
- **router** / **controller** (declared at that level)
- **route handler** (declared on the decorator)

Same-name lookups walk inward — handler-level overrides controller, controller overrides app.

## Dishka (`FromDishka as Inject[T]`)

Use Dishka when the app needs explicit request / session / app scope management — typically when you have transient resources that must close at request end and don't want to wire them all through `Provide()` callables.

```python
from __future__ import annotations

from dishka import Provider, Scope, provide, make_async_container
from dishka.integrations.litestar import FromDishka as Inject, setup_dishka

from app.domain.accounts.services import UserService


class AppProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def users_service(self, db_session: AsyncSession) -> UserService:
        return UserService(session=db_session)


container = make_async_container(AppProvider())
app = Litestar(route_handlers=[UserController])
setup_dishka(container=container, app=app)


class UserController(Controller):
    path = "/api/users"

    @get("/{user_id:uuid}")
    async def get_user(self, user_id: UUID, users_service: Inject[UserService]) -> User:
        return await users_service.get(user_id)
```

## When to Scale Up

| Symptom | Stay on `Provide()` | Move to Dishka |
| --- | --- | --- |
| <10 dependencies | ✓ | — |
| Flat dependency graph | ✓ | — |
| Resource lifetimes match request | ✓ | — |
| Need cross-scope (app singleton + request transient) | — | ✓ |
| Hand-wiring `Provide` callables feels repetitive | — | ✓ |
| Plugin authors who want strict typing of injected deps | — | ✓ |
| Mixing CLI + HTTP entry points sharing services | — | ✓ |

Most consumer apps live happily on `Provide()`. Promote to Dishka when the wiring genuinely costs more than it pays back.

## Dishka Footnote

Dishka is not a standalone skill in this repo — Litestar is its primary surface here, so this reference is the integration source of truth. Key Dishka concepts worth knowing:

- **`Provider`**: a class declaring how to build types in a given `Scope`
- **`Scope`**: `APP`, `SESSION`, `REQUEST`, `ACTION`, `STEP` — Litestar uses `APP` and `REQUEST` mostly
- **`@provide`**: marks an async/sync method that builds an instance of its return type
- **`make_async_container(*providers)`**: constructs the container at app boot
- **`setup_dishka(container, app)`**: wires the container into Litestar so `Inject[T]` resolves on request
- **`Inject[T]`** (= `FromDishka`): the parameter annotation that triggers DI resolution

## Cross-references

- Repository service deps live alongside DB sessions: [services.md](../../litestar-data-services/references/services.md)
- Plugin-supplied deps (e.g. `TaskQueues` from `litestar-saq`): [plugins.md](../../litestar-plugins/references/plugins.md), `../../litestar-saq/SKILL.md`
