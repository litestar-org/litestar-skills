# Commit Modes

This reference describes `commit_mode` for the FastAPI, Flask, Starlette, and
Sanic extensions. Litestar uses `before_send_handler` instead; see
[Litestar Transaction Configuration](#litestar-transaction-configuration).

## What `commit_mode` Controls

The non-Litestar framework config classes declare:

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

## Litestar Transaction Configuration

Litestar's `SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` do not define
`commit_mode`. Configure their `before_send_handler`:

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://app:app@localhost/orders",
    before_send_handler="autocommit",
)
```

Accepted string shortcuts are `"autocommit"` and
`"autocommit_include_redirects"` (plural). Leave the field unset for the
default close-only handler, which neither commits nor rolls back.

For custom status rules, pass
`async_autocommit_handler_maker(extra_commit_statuses={...},
extra_rollback_statuses={...})` or the sync equivalent. Overlapping status
sets raise `ValueError`.

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

The non-Litestar `commit_mode` middleware uses fixed 2xx/3xx ranges. Use
`commit_mode="manual"` and commit explicitly for other status rules. Litestar
does expose `extra_commit_statuses` and `extra_rollback_statuses` through its
handler makers.

## Common Pitfalls

- **`autocommit` rolls back on 4xx.** A handler that returns `400` after writing a row will see the row disappear at request teardown. If the write must persist, switch to `manual` and commit before returning the 4xx.
- **`autocommit` rolls back on 5xx.** Handlers that catch an exception, log it, and return `500` will still see a rollback because the status code drives the decision. Use `manual` if you need to commit partial work before reporting failure.
- **Redirects do not commit by default.** If your handler returns `303 See Other` after `INSERT`, plain `autocommit` will roll back. Use `autocommit_include_redirect`.
- **Do not pass request sessions to background tasks.** Request cleanup closes
  the session before deferred work runs. Pass identifiers or payloads and open
  a worker-owned session.
- **Transaction behavior is per config, not per route.** Use manual commits for
  exceptional routes; do not create a fake database bind solely to change
  transaction semantics.

## Canonical Reference

- [Advanced Alchemy v1.11.0 source](https://github.com/litestar-org/advanced-alchemy/tree/v1.11.0/advanced_alchemy/extensions)
