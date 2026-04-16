---
name: litestar
description: "Auto-activate for litestar, litestar_granian, litestar_saq, litestar_vite, litestar_mcp, litestar_email, litestar_asyncpg, litestar_oracledb, sqlspec, advanced_alchemy, msgspec, dishka imports; litestar.toml; pyproject.toml with a litestar dep; `from litestar import` in any .py file. Litestar ASGI framework and first-party ecosystem — Controllers, Guards, middleware, msgspec DTOs, OpenAPI, DI (Provide / Dishka), and plugins for Granian, SAQ, Vite, MCP, Email, AsyncPG, OracleDB. Produces opinionated Litestar routes, DTOs, Guards, Controllers, plugin configs, auth flows, CRUD endpoints. Use when: exposing a SQLAlchemy model as a Controller or MCP tool, integrating a Vite frontend (React / Vue / Svelte / HTMX / Inertia), serving AI models with streaming and SAQ workers, implementing JWT refresh-token auth, scaffolding a Litestar app, or adding Guards / middleware / DI. Not for FastAPI, Django, Flask, Starlette, aiohttp, or Sanic — Litestar has its own runtime-introspection and DI model."
---

# Litestar Framework

Litestar is a high-performance Python ASGI web framework with built-in OpenAPI generation, first-class msgspec integration, dependency injection, and a curated plugin ecosystem (Granian, SAQ, Vite, MCP, Email, AsyncPG, OracleDB). This skill produces idiomatic Litestar consumer-app code — msgspec-first DTOs, Guards for auth, `Provide()` or Dishka for DI, Granian for serving, advanced-alchemy / sqlspec for data access.

## Code Style Rules

- **PEP 604 unions only**: `T | None`, not `Optional[T]`
- **`from __future__ import annotations`** at the top of every application module (handlers, DTOs, services, tests). Exception: libraries in the Litestar ecosystem (this repo, advanced-alchemy, sqlspec, msgspec, dishka, etc.) avoid it in modules that define runtime-introspected types.
- **Google-style docstrings** when useful; skip over writing bad ones
- **Async all I/O** — `async def` handlers with awaited DB / HTTP calls. Sync blocks the event loop and breaks Granian's worker model.
- **msgspec DTOs with camelCase rename** — `Meta(rename="camel")` on request/response Structs so the Python side stays snake_case while the API ships camelCase
- **Cluster Controllers by domain** (`/api/accounts`, `/api/teams`, `/api/admin`), not by HTTP method
- **Guards at Controller class level** primarily; route-level guards only for exceptions to the controller's default policy
- **DI**: `Provide()` for small-to-mid apps; **Dishka `FromDishka as Inject[T]`** for enterprise scope management (request / session / app scopes)
- **Data access — pick the path matching your project's stack.** If the project uses `advanced-alchemy`, use `SQLAlchemyAsyncRepositoryService` (auto-conversion, filters, pagination built in — the opinionated default). If the project uses `sqlspec`, use `SQLSpecAsyncService` + driver methods for direct SQL control and multi-adapter support. If the project uses raw SQLAlchemy only, use manual `async_sessionmaker` sessions. See `skills/advanced-alchemy` and `skills/sqlspec` for canonical patterns per stack. Hand-written queries inside a repository-service stack are an escape hatch; hand-written queries are the primary surface in a sqlspec stack — context decides.

## Quick Reference

### Controller (domain-clustered, Guards at class level)

```python
# advanced-alchemy stack — create_filter_dependencies + OffsetPagination + to_schema
# Using sqlspec instead? See skills/sqlspec/references/service-patterns.md for the
# LimitOffsetFilter + SQLSpecAsyncService equivalent.
class UserController(Controller):
    path = "/api/users"
    guards = [requires_active_user]
    dependencies = create_filter_dependencies({"id_filter": "UUID", "pagination_type": "limit_offset"})

    @get("/")
    async def list_users(self, users_service: UserService, filters: list) -> OffsetPagination[User]:
        results, total = await users_service.list_and_count(*filters)
        return users_service.to_schema(results, total, filters=filters, schema_type=User)
```

→ See [references/routing.md](references/routing.md), [references/domains.md](references/domains.md)

### Repository Service — advanced-alchemy

```python
class UserRepository(SQLAlchemyAsyncRepository[User]):
    model_type = User

class UserService(SQLAlchemyAsyncRepositoryService[User]):
    repository_type = UserRepository
```

Get `get`, `get_one_or_none`, `list_and_count`, `create`, `update`, `delete`, `upsert`, `exists`, `count`, `to_schema` for free. → See [references/services.md](references/services.md)

### Service — sqlspec

```python
# sqlspec stack — thin async service over driver methods + explicit SQL
class UserService(SQLSpecAsyncService):
    async def list_and_count(self, *filters) -> tuple[list[User], int]:
        return await self.driver.select_and_count(
            "SELECT * FROM users WHERE tenant_id = :tid",
            filters=filters,
            schema_type=User,
        )
```

Pick `sqlspec` when you want direct SQL, multi-adapter support (15+ drivers), or Arrow integration for analytics. → See [`../sqlspec/references/service-patterns.md`](../sqlspec/references/service-patterns.md) *(landing in Ch5 — stub link TODO(Ch5))*.

### msgspec DTO with camelCase

```python
class User(CamelizedBaseStruct):  # base sets rename="camel"
    id: UUID
    name: str
    is_active: bool = True   # → "isActive" on the wire
```

→ See [references/dto.md](references/dto.md)

### Guard (auth at Controller class level)

```python
async def requires_active_user(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    if not connection.user or not connection.user.is_active:
        raise PermissionDeniedException("Authentication required")
```

→ See [references/guards.md](references/guards.md)

### Dependency Injection — two paths

```python
# Provide() — small/mid apps
app = Litestar(dependencies={"users_service": Provide(provide_user_service)})

# Dishka — enterprise scope management
async def get_user(users_service: Inject[UserService]) -> User: ...
```

→ See [references/di.md](references/di.md)

### Custom Exceptions

```python
class ApplicationError(HTTPException): ...
class NotFoundError(ApplicationError): status_code = 404
class ConflictError(ApplicationError): status_code = 409

app = Litestar(exception_handlers={ApplicationError: application_exception_handler})
```

Handlers never catch — exceptions bubble to app-level handler. → See [references/exceptions.md](references/exceptions.md)

### Settings — two supported paths

```python
# Path A — @dataclass + get_env() + @lru_cache (no extra deps; canonical default)
@dataclass(frozen=True)
class AppSettings:
    name: str = field(default_factory=lambda: get_env("APP_NAME", "My App"))
    database: DatabaseSettings = field(default_factory=DatabaseSettings)

@lru_cache(maxsize=1)
def get_settings() -> AppSettings: return AppSettings()
```

Using Pydantic already in-stack? Use `pydantic_settings.BaseSettings` with the same env-loading pattern — it's fully supported and reads the same env vars. Pick `@dataclass` for a leaner dep graph on fresh projects; pick `BaseSettings` when Pydantic is already a transitive dep (e.g., shared DTOs with non-Litestar microservices). → See [references/settings.md](references/settings.md) for both options side-by-side.

### Pagination — pick the branch for your stack

```python
# advanced-alchemy — OffsetPagination + create_filter_dependencies
dependencies = create_filter_dependencies({
    "id_filter": "UUID", "pagination_type": "limit_offset",
    "search": "title,author", "created_at": True,
})

async def list_posts(self, posts_service, filters: list) -> OffsetPagination[Post]:
    results, total = await posts_service.list_and_count(*filters)
    return posts_service.to_schema(results, total, filters=filters, schema_type=Post)
```

Using `sqlspec`? Use `LimitOffsetFilter` + `OrderByFilter` in the driver call. Using raw SQLAlchemy Core? Apply `.limit()` / `.offset()` manually on the statement. See [references/pagination.md](references/pagination.md) for all three branches side-by-side.

### WebSockets & Channels

```python
@websocket("/ws/workspace/{workspace_id:uuid}")
async def workspace_stream(socket, workspace_id, channels: ChannelsPlugin) -> None:
    await socket.accept()
    async with channels.start_subscription([f"workspace:{workspace_id}"]) as sub:
        async for event in sub.iter_events():
            await socket.send_json(event)
```

WS auth via query-param JWT (browsers can't set WS headers). Cross-process pub/sub from SAQ workers and CLI uses the same Channels backend. → See [references/websockets.md](references/websockets.md)

### App with First-Party Plugins

```python
app = Litestar(
    plugins=[
        GranianPlugin(),
        SQLAlchemyPlugin(config=SQLAlchemyAsyncConfig(connection_string=settings.database.url)),
        SAQPlugin(config=SAQConfig(use_server_lifespan=True, queue_configs=[...])),
        VitePlugin(config=ViteConfig(dev_mode=settings.debug)),
        LitestarMCP(MCPConfig(name=settings.name)),
    ],
)
# Run: litestar run    Workers: litestar workers run
```

→ See [references/plugins.md](references/plugins.md), [references/deployment.md](references/deployment.md)

## End-to-End Example

Full 6-layer vertical slice (Model → Schemas → Service → Controller → Jobs → App wiring) demonstrating every canonical pattern in [references/example.md](references/example.md).

<workflow>

## Workflow

### Step 1 — Model the domain

Define `msgspec.Struct` (or SQLAlchemy / Advanced Alchemy models) for the data shapes. Keep API DTOs separate from persistence models via `DTOConfig(exclude={...})`.

### Step 2 — Write route handlers

Use `@get` / `@post` / `@put` / `@delete` decorators for single routes, or group related endpoints into a `Controller` class with shared `path`, `dependencies`, and `guards`.

### Step 3 — Add Guards and middleware

Apply `guards=[...]` at the route, controller, or app level for auth / authz. Use `AbstractMiddleware` for cross-cutting concerns (logging, timing, CORS, request IDs).

### Step 4 — Wire dependencies + plugins

Register DI providers via `Provide()` (built-in) or a Dishka `make_async_container()` for richer scope management. Register ecosystem plugins (`GranianPlugin`, `SAQPlugin`, `VitePlugin`, `LitestarMCP`, etc.) on the `Litestar(plugins=[...])` call.

### Step 5 — Validate

Confirm `/schema/openapi.json` or the Swagger UI at `/schema` reflects the correct DTOs. Run `litestar run --reload` (Granian-backed) and smoke-test endpoints. For MCP-exposed routes, confirm `POST /mcp/` (JSON-RPC 2.0) lists expected tools.

</workflow>

<guardrails>

## Guardrails

- **msgspec DTOs with `Meta(rename="camel")`** — Python side snake_case, API ships camelCase. Pydantic DTOs only when the project explicitly requires it.
- **Guards at Controller class level primarily** (`guards = [requires_auth]` on the Controller), route-level only for exceptions to the class default. Never inline `if not connection.user: ...` in handler bodies.
- **DI sizing**: `Provide()` for small/mid apps; **Dishka `FromDishka as Inject[T]`** for apps that need request / session / app scope management. Don't default to Dishka — it's a scaling choice, not a style choice.
- **Data access — match your stack:** if on `advanced-alchemy`, subclass `SQLAlchemyAsyncRepositoryService` (auto DTO conversion, filtering, pagination); if on `sqlspec`, use `SQLSpecAsyncService` + driver methods; if on raw SQLAlchemy, use `async_sessionmaker` sessions. The anti-pattern is mixing: don't paste an `advanced-alchemy` repository into a `sqlspec` project (drags in ORM deps you rejected) or vice-versa.
- **Pagination — match your stack:** `advanced-alchemy`'s `create_filter_dependencies` + `OffsetPagination[T]`; `sqlspec`'s `LimitOffsetFilter` + `OrderByFilter`; or raw `.limit()` / `.offset()` in plain-SA Core. Never hand-roll `limit` / `offset` *query params* in a handler — the filter dep / filter-object pattern owns that.
- **Custom exception hierarchy**: extend `ApplicationError` in `lib/exceptions.py`, register handlers on the app via `app_config.exception_handlers = {ExceptionType: handler_func}`. Never inline `try` / `except` in handlers — let exceptions bubble to the app-level handler.
- **Settings — match your stack:** `@dataclass(frozen=True)` + `get_env()` + `@lru_cache` for fresh projects (canonical default; no extra deps), OR `pydantic_settings.BaseSettings` when Pydantic is already a dep of the project. Don't use `msgspec.Struct` for config — it lacks env-loading affordances. Whichever path, the settings object is cached once per process.
- **`from __future__ import annotations` is a LIBRARY-AUTHOR guardrail, not a consumer rule.** Litestar libraries (this repo, advanced-alchemy, sqlspec, msgspec, dishka, etc.) avoid it in modules that define runtime-introspected types. **Application code MAY use `from __future__ import annotations`** — canonical Litestar apps use it in 100+ files per repo.
- **Async all I/O** — `async def` handlers with awaited DB / HTTP calls. Sync blocks the event loop.
- **Cluster Controllers by domain** — `/api/accounts`, `/api/teams`, `/api/admin` — not by HTTP method. Each domain gets its own Controller class (or several) sharing a path prefix.
- **Granian over uvicorn** — `litestar-granian` is the default ASGI server. Use uvicorn only when Granian's HTTP/2 behavior is incompatible with your deploy target.
- **SAQ for background work**, never `asyncio.create_task()` in handlers. Fire-and-forget leaks request-scoped resources; SAQ gives durability, scheduling, and observability.
- **WebSockets — choose the Channels backend per stack:** Memory backend for dev / single-process; Redis backend when Redis is already in the stack (cache, SAQ broker); `sqlspec` PG-LISTEN extension when the project is sqlspec + PostgreSQL; `advanced-alchemy` session-aware backend when the project is advanced-alchemy + PostgreSQL. Anti-pattern: forcing Redis into a PG-only project just for Channels, or forcing a PG-LISTEN backend when Redis is already present. WS auth always happens via query-param JWT (browsers can't set WS headers). Plain `WebSocket` + direct pub/sub is still fine for one-off streams; Channels plugin adds dynamic channel names, backlog / history, and cross-process publishing from SAQ workers or CLI.
- **First-party plugins over hand-rolled glue** — `litestar-saq` before Celery, `litestar-vite` before hand-rolled static, `litestar-mcp` before raw JSON-RPC, `litestar-email` before raw SMTP, `litestar-asyncpg` / `litestar-oracledb` before raw driver lifespans.

</guardrails>

<validation>

## Validation Checkpoint

Before delivering Litestar code, verify:

- [ ] DTOs use `msgspec.Struct` + `MsgspecDTO` with `Meta(rename="camel")` unless the project explicitly uses Pydantic
- [ ] Auth is enforced via Guards at Controller class level; no inline auth checks
- [ ] Data-access services match the project's stack: `SQLAlchemyAsyncRepositoryService` for advanced-alchemy, `SQLSpecAsyncService` for sqlspec, or `async_sessionmaker` sessions for raw SQLAlchemy — never mixed within one project
- [ ] Pagination matches the project's stack: `OffsetPagination[T]` + `create_filter_dependencies` for advanced-alchemy, `LimitOffsetFilter` + `OrderByFilter` for sqlspec, or `.limit()` / `.offset()` for raw SA
- [ ] Exceptions extend the project's `ApplicationError` base; handlers registered on the app, not inline
- [ ] Settings match the project's stack: `@dataclass` + `get_env()` + `@lru_cache` (fresh projects) OR `pydantic_settings.BaseSettings` (projects already on Pydantic)
- [ ] All I/O handlers are `async def`; no `asyncio.create_task()` for background work — SAQ instead
- [ ] Controllers cluster by domain (not HTTP method); shared `path` + `dependencies` + `guards`
- [ ] OpenAPI schema at `/schema/openapi.json` reflects the intended request / response types
- [ ] First-party plugins used where available (Granian / SAQ / Vite / MCP / Email / AsyncPG / OracleDB)
- [ ] For library-author changes: no `from __future__ import annotations` in modules that define Litestar handlers, DTOs, DI providers, or any runtime-introspected types

</validation>

## References Index

Deep-dive references under `references/`:

### Core Patterns

- [routing.md](references/routing.md) — Route decorators, Controller patterns, Router composition, domain clustering
- [di.md](references/di.md) — `Provide()` and Dishka integration, scope sizing guidance
- [dto.md](references/dto.md) — msgspec Struct → MsgspecDTO → DTOConfig, exclude / rename / partial, `CamelizedBaseStruct`
- [guards.md](references/guards.md) — Auth/authz at route/controller/app level, JWT, multi-tenant, WebSocket auth
- [middleware.md](references/middleware.md) — `AbstractMiddleware`, scope filtering, exclude patterns

### Data & Business Logic

- [services.md](references/services.md) — `SQLAlchemyAsyncRepositoryService` deep dive, filters, `to_schema`, escape hatches
- [pagination.md](references/pagination.md) — `OffsetPagination[T]` + `create_filter_dependencies`, filter catalog
- [exceptions.md](references/exceptions.md) — `ApplicationError` hierarchy, handler registration
- [settings.md](references/settings.md) — `@dataclass` + `get_env()` + `@lru_cache` pattern

### Infrastructure

- [domains.md](references/domains.md) — Domain-clustered folder structure, shared `lib/`, multi-tenant workspaces
- [plugins.md](references/plugins.md) — `InitPluginProtocol`, plugin lifecycle, ecosystem plugin index

### Real-time

- [websockets.md](references/websockets.md) — WebSocket handlers, Channels plugin, cross-process publishing, WS-vs-Channels matrix

### Deployment

- [deployment.md](references/deployment.md) — Granian config, IAP auth, static asset serving, Docker patterns

### Full Vertical Slice

- [example.md](references/example.md) — Full 6-layer Task feature vertical slice

### Sibling Skills

- `../litestar-granian/SKILL.md` — Granian server tuning
- `../litestar-saq/SKILL.md` — SAQ task queues, cron, workers
- `../litestar-vite/SKILL.md` — Vite frontend integration, TypeGen, Inertia
- `../litestar-mcp/SKILL.md` — MCP tools/resources over JSON-RPC 2.0
- `../litestar-email/SKILL.md` — Email backends, templates
- `../advanced-alchemy/SKILL.md` — Repository/Service patterns, audit base, Alembic
- `../dishka/SKILL.md` — DI scopes (note: see [references/di.md](references/di.md) for Litestar-specific Dishka usage)

## Official References

- <https://docs.litestar.dev/latest/> — Framework docs
- <https://docs.litestar.dev/latest/release-notes/changelog.html> — Changelog
- <https://github.com/litestar-org/litestar> — Core repo
- <https://github.com/litestar-org> — First-party ecosystem org (all `litestar-*` packages)
- <https://pypi.org/project/litestar/> — Releases

## Shared Styleguide Baseline

Generic language / framework rules live in the repo's shared styleguides:

- [`general.md`](../litestar-styleguide/references/general.md) — Cross-language baseline
- [`python.md`](../litestar-styleguide/references/python.md) — Python conventions
- [`litestar.md`](../litestar-styleguide/references/litestar.md) — Litestar-specific baseline

This skill extends those — it does not duplicate them. When a convention is generic (type hints, naming, imports), it belongs in the shared styleguide.
