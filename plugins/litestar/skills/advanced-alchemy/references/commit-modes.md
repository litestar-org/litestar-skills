# Commit Modes

This reference describes Advanced Alchemy's `commit_mode` configuration option — the library-level switch that decides when a request-scoped SQLAlchemy session commits, when it rolls back, and which HTTP status codes it treats as "successful". Configuration here is framework-neutral; per-framework wiring (where the session ends up on the request, how handlers receive it) lives in the integration guides.

## What `commit_mode` Controls

The `commit_mode` field is declared on the per-framework config classes (`SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` in `advanced_alchemy.extensions.starlette`, `advanced_alchemy.extensions.fastapi`, `advanced_alchemy.extensions.sanic`, etc.) as:

```python
commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
```

The middleware that ships with each extension reads this field at request teardown and decides whether to call `session.commit()` or `session.rollback()` based on the response's HTTP status code.

## The Three Modes

### `"manual"` (default)

The middleware does not commit or roll back. Your handler — or a service layer it delegates to — is responsible for calling `session.commit()` and `session.rollback()` directly. The middleware still owns session lifetime: it constructs the session at request start and closes it at request end.

Use `manual` when:

- A single endpoint spans multiple atomic units of work that must commit independently.
- You commit early to release locks, then continue work after the commit point.
- Tests want full control over transaction boundaries.

### `"autocommit"`

The middleware commits if the response status code is in the `200`-`299` range; otherwise it rolls back. Exceptions raised by the handler always roll back. The exact predicate from the upstream source is:

```python
if (commit_mode == "autocommit" and 200 <= status_code < 300):
    await session.commit()
else:
    await session.rollback()
```

Use `autocommit` for standard CRUD endpoints where "2xx response means the work succeeded; anything else means undo it".

### `"autocommit_include_redirect"`

Same as `autocommit`, plus 3xx responses (`300`-`399`) also commit. The upstream predicate:

```python
if (commit_mode == "autocommit" and 200 <= status_code < 300) or (
    commit_mode == "autocommit_include_redirect" and 200 <= status_code < 400
):
    await session.commit()
else:
    await session.rollback()
```

Use this when handlers respond with a 3xx redirect after performing a successful state mutation (the POST-then-redirect-to-GET pattern common in server-rendered apps and OAuth callbacks).

## Decision Matrix

| Situation | Mode |
| --- | --- |
| Most REST endpoints; "2xx means it worked" | `autocommit` |
| Server-rendered endpoints that POST and redirect | `autocommit_include_redirect` |
| Long handler with multiple commit points; or tests asserting exact transaction boundaries | `manual` |
| Webhook receivers that always 200 even on partial failure | `manual` |
| Multi-tenant background-job dispatch where the transaction wraps the dispatch only | `manual` |

## Configuring It

```python
from advanced_alchemy.extensions.starlette import (
    SQLAlchemyAsyncConfig,
    EngineConfig,
)

db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost:5432/orders",
    commit_mode="autocommit",
    engine_config=EngineConfig(
        pool_size=20,
        max_overflow=10,
        pool_recycle=300,
    ),
)
```

The same field exists on `SQLAlchemySyncConfig` and accepts the same three string literals. The `extensions.fastapi` module re-exports the Starlette config classes, so the API is identical there.

## Sync Bridge

The sync flavor uses `run_in_threadpool()` under the hood to call `session.commit()` / `session.rollback()` from the ASGI event loop. The status-code predicate is identical:

```python
from advanced_alchemy.extensions.starlette import SQLAlchemySyncConfig

db_config = SQLAlchemySyncConfig(
    connection_string="postgresql+psycopg://app:app@localhost:5432/orders",
    commit_mode="autocommit",
)
```

Pick the sync config when your application server can dedicate threads (e.g. a sync WSGI worker, or an ASGI app that runs sync repositories in a threadpool).

## Status-Code Customization

Advanced Alchemy's middleware does **not** expose `extra_commit_statuses` or `extra_rollback_statuses` knobs at the time of writing — the 2xx (and optional 3xx) ranges are hard-coded into the predicate above. If you need to commit on a non-standard status code (for example, a handler that returns `422` after a *successful* state mutation that produced a validation warning), use `commit_mode="manual"` and call `session.commit()` explicitly inside the handler before returning.

This is the one significant API gap relative to sqlspec, which does expose those knobs. Track upstream issues on the [advanced-alchemy repository](https://github.com/litestar-org/advanced-alchemy) if this matters for your application.

## Common Pitfalls

- **`autocommit` rolls back on 4xx.** A handler that returns `400` after writing a row will see the row disappear at request teardown. If the write must persist, switch to `manual` and commit before returning the 4xx.
- **`autocommit` rolls back on 5xx.** Handlers that catch an exception, log it, and return `500` will still see a rollback because the status code drives the decision. Use `manual` if you need to commit partial work before reporting failure.
- **Redirects do not commit by default.** If your handler returns `303 See Other` after `INSERT`, plain `autocommit` will roll back. Use `autocommit_include_redirect`.
- **Background tasks scheduled inside a handler share the request session.** If the handler returns `202 Accepted`, autocommit will commit and the session is closed before the task runs. Pass payload data (not session-bound ORM instances) to the task and let the worker open its own session.
- **`commit_mode` is per-config, not per-route.** Multiple routes that share the same `SQLAlchemyAsyncConfig` get the same mode. Split into multiple configs (each with its own `bind_key`) if different routes need different commit semantics — see [multi-database.md](./multi-database.md).

## Canonical References

- [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) — uses `commit_mode="autocommit"` on its primary write database via the Litestar plugin.
- [litestar-fullstack-inertia](https://github.com/litestar-org/litestar-fullstack-inertia) — server-rendered POST-redirect-GET endpoints; demonstrates where `autocommit_include_redirect` would apply.
