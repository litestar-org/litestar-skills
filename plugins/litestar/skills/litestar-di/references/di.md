# Dependency Injection — `Provide()` and Dishka

Two paths: built-in `Provide()` for small/mid apps, Dishka for enterprise scope management. Don't default to Dishka — it's a scaling choice, not a style choice.

## Litestar Built-in DI (`Provide()`)

```python
from __future__ import annotations

from litestar import Litestar, Request
from litestar.di import NamedDependency, Provide
from litestar.datastructures import State
from sqlalchemy.ext.asyncio import AsyncSession


async def provide_session(state: State) -> AsyncSession:
    return state.db_session


async def provide_current_user(
    request: Request,
    db_session: NamedDependency[AsyncSession],
) -> User:
    token = request.headers.get("Authorization")
    return await authenticate(db_session, token)


async def provide_user_service(db_session: NamedDependency[AsyncSession]) -> UserService:
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

Wrap every provider in `Provide`. Litestar uses the wrapper to inspect the
provider, control caching, and decide whether synchronous work runs inline or
in a worker thread.

- Use an async provider for async I/O.
- Use `Provide(sync_provider, sync_to_thread=True)` when the provider performs
  blocking I/O.
- Use `Provide(sync_provider, sync_to_thread=False)` only for trivial
  non-blocking work. Omitting `sync_to_thread` on a synchronous provider emits
  `LitestarWarning`.
- Use generator providers for request cleanup. Do not combine a generator
  provider with `use_cache=True`.

Dependency declaration layers:

- **app** (default for `Litestar(dependencies=...)`)
- **router** / **controller** (declared at that level)
- **route handler** (declared on the decorator)

Same-name lookups walk inward — handler-level overrides controller, controller overrides app.

## Typed Dependency Parameters

Name handler and provider parameters after dependency keys. Use `NamedDependency[T]` for every value resolved from a Litestar dependency map; Litestar 2.24 deprecates implicit dependency injection by matching parameter names alone. Use `NamedDependency[SkipValidation[T]]` when the dependency value is trusted and should bypass validation, such as a generated filter aggregate.

```python
from litestar.di import NamedDependency
from litestar.params import SkipValidation


async def list_users(
    users_service: NamedDependency[UserService],
    filters: NamedDependency[SkipValidation[list[FilterTypes]]],
) -> OffsetPagination[User]:
    rows, total = await users_service.get_many_and_count(*filters)
    return users_service.to_schema(rows, total, filters=filters, schema_type=User)
```

The dependency key and parameter name must match. `NamedDependency[T]` (from `litestar.di`) marks the parameter as a dependency value and replaces `Annotated[T, Dependency()]`:

```python
from litestar.di import NamedDependency


async def list_users(db: NamedDependency[AsyncSession]) -> list[User]:  # injects the "db" provider
    ...
```

`params.Dependency` / `DependencyKwarg` are deprecated since 2.23. Litestar
2.24 also deprecates implicit injection based only on a matching parameter
name. Both forms are removed in Litestar 3.0.

## Dependency replacement in tests

Litestar has no mutable `app.dependency_overrides` registry. Create a fresh app
or client with the replacement providers:

```python
import pytest
from litestar import get
from litestar.di import NamedDependency, Provide
from litestar.testing import create_async_test_client


@get("/")
async def get_user(users_service: NamedDependency[UserService]) -> User:
    return await users_service.get_current()


async def provide_fake_users_service() -> UserService:
    return FakeUserService()


@pytest.mark.anyio
async def test_get_user() -> None:
    async with create_async_test_client(
        get_user,
        dependencies={
            "users_service": Provide(provide_fake_users_service),
        },
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
```

For full-application tests, make `create_app()` accept the provider map and
construct a new `Litestar` instance per test. Do not mutate shared app state;
parallel tests otherwise race on dependency configuration.

## Dishka (`FromDishka as Inject[T]`)

Use Dishka when the app needs explicit request / session / app scope management — typically when you have transient resources that must close at request end and don't want to wire them all through `Provide()` callables.

```python
from __future__ import annotations

from dishka import Provider, Scope, provide, make_async_container
from dishka.integrations.litestar import FromDishka as Inject, setup_dishka
from litestar.params import FromPath

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
    async def get_user(
        self,
        user_id: FromPath[UUID],
        users_service: Inject[UserService],
    ) -> User:
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

## Tagged source

- [2.24 dependency injection guide](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/usage/dependency-injection.rst)
- [2.24 `Provide` and `NamedDependency`](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/di.py)
- [2.24 test override guidance](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/onboarding/fastapi.rst)
