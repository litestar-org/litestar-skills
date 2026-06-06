# Commit Modes

This reference describes SQLSpec's commit-mode middleware semantics — how the per-request connection's transaction is committed, rolled back, or left untouched based on a configuration string and the response's HTTP status code. Configuration here is framework-neutral; per-framework wiring (where the connection ends up on the request, how handlers receive it) lives in the integration guides.

## What `commit_mode` Selects

SQLSpec attaches its commit policy through `extension_config["<framework>"]["commit_mode"]` on each adapter config. The framework extension reads that value and registers either `SQLSpecAutocommitMiddleware` or `SQLSpecManualMiddleware` against the application. The default — applied when the key is absent — is `"manual"`:

```python
DEFAULT_COMMIT_MODE = "manual"
```

The three accepted values map to middleware as follows:

| `commit_mode` value | Middleware registered | Notes |
| --- | --- | --- |
| `"manual"` | `SQLSpecManualMiddleware` | Acquires + releases the connection; never commits or rolls back automatically. |
| `"autocommit"` | `SQLSpecAutocommitMiddleware(include_redirect=False)` | Commits on 2xx, rolls back on everything else. |
| `"autocommit_include_redirect"` | `SQLSpecAutocommitMiddleware(include_redirect=True)` | Commits on 2xx + 3xx, rolls back on everything else. |

The dispatch is hard-coded in the extension's `_add_middleware` step:

```python
if config_state.commit_mode == "manual":
    app.add_middleware(SQLSpecManualMiddleware, config_state=...)
elif config_state.commit_mode == "autocommit":
    app.add_middleware(SQLSpecAutocommitMiddleware, ..., include_redirect=False)
elif config_state.commit_mode == "autocommit_include_redirect":
    app.add_middleware(SQLSpecAutocommitMiddleware, ..., include_redirect=True)
```

## What Each Mode Does

### `"manual"`

`SQLSpecManualMiddleware` acquires a connection from the pool (or creates one if the adapter does not pool), stores it on `request.state` under the configured `connection_key`, runs the handler, and releases the connection on the way out. It never calls `commit()` or `rollback()` — your handler is responsible for transaction boundaries. Use `manual` when:

- You want explicit control over commits (multiple atomic units inside one handler).
- The adapter is already auto-committing each statement (e.g. a connection opened with `autocommit=True` at the driver level).
- Tests want to assert on transaction boundaries without middleware interference.

### `"autocommit"`

`SQLSpecAutocommitMiddleware` runs the handler, then calls `connection.commit()` if `_should_commit(response.status_code)` returns `True`, otherwise `connection.rollback()`. Exceptions raised by the handler always roll back and re-raise. The decision predicate from upstream:

```python
def _should_commit(self, status_code: int) -> bool:
    extra_commit = self.config_state.extra_commit_statuses or set()
    extra_rollback = self.config_state.extra_rollback_statuses or set()

    if status_code in extra_commit:
        return True
    if status_code in extra_rollback:
        return False
    if HTTP_200_OK <= status_code < HTTP_300_MULTIPLE_CHOICES:
        return True
    return bool(
        self.include_redirect
        and HTTP_300_MULTIPLE_CHOICES <= status_code < HTTP_400_BAD_REQUEST
    )
```

Use `autocommit` for standard CRUD endpoints where "2xx response means the work succeeded; anything else means undo it".

### `"autocommit_include_redirect"`

Same as `autocommit`, plus 3xx (`300`-`399`) responses commit. The `include_redirect` flag flips the second branch in `_should_commit`. Use this when handlers respond with a redirect after performing a successful state mutation (POST-then-redirect-to-GET, OAuth callback flows, server-rendered apps that prefer `303 See Other` over JSON envelopes).

## Status-Code Customization: `extra_commit_statuses` / `extra_rollback_statuses`

Unlike advanced-alchemy, SQLSpec lets you override individual status codes in either direction. Both knobs live alongside `commit_mode` on the adapter's `extension_config`:

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
    extension_config={
        "starlette": {
            "commit_mode": "autocommit",
            "extra_commit_statuses": {422},   # commit even on 422
            "extra_rollback_statuses": {201}, # roll back even on 201
        },
    },
)
```

Both fields accept any `Iterable[int]` (a `set` is idiomatic). The predicate checks `extra_commit_statuses` *first*, then `extra_rollback_statuses`, then the default range — so adding a status to `extra_commit_statuses` overrides the default rollback for 4xx, and adding a 2xx status to `extra_rollback_statuses` overrides the default commit. They are mutually exclusive: do not put the same code in both.

## Decision Matrix

| Situation | Mode |
| --- | --- |
| Most REST endpoints; "2xx means it worked" | `autocommit` |
| Server-rendered endpoints that POST and redirect | `autocommit_include_redirect` |
| Validation API that returns `422` after a successful audit-log write | `autocommit` + `extra_commit_statuses={422}` |
| Webhook receiver that returns `201` but should never persist (debug mode) | `autocommit` + `extra_rollback_statuses={201}` |
| Long handler with multiple commit points; or driver-level autocommit | `manual` |
| Adapter that does not support transactions at all (e.g. some analytics drivers) | `manual` |

## Configuring It

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig

config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost:5432/orders"},
    extension_config={
        "starlette": {
            "commit_mode": "autocommit",
            "connection_key": "db_connection",
            "session_key": "db_session",
            "pool_key": "db_pool",
        },
    },
)

sqlspec = SQLSpec()
sqlspec.add_config(config)
```

The `extension_config` mapping is keyed by extension name (`"starlette"`, `"litestar"`, `"fastapi"`, etc.). The same adapter config can declare settings for multiple extensions in the same dict — they are read by whichever extension is loaded.

## Sync Bridge

SQLSpec exposes sync adapters (e.g. `PsycopgSyncConfig`, `DuckDBConfig`, `SqliteConfig`). The middleware uses the same status-code predicate and the same `commit_mode` strings; the difference is the underlying driver call (`connection.commit()` blocks rather than awaits). For ASGI hosts, sync adapters typically run inside a threadpool — the middleware handles that transparently.

```python
from sqlspec import SQLSpec
from sqlspec.adapters.psycopg import PsycopgSyncConfig

config = PsycopgSyncConfig(
    connection_config={"conninfo": "postgresql://app:app@localhost:5432/orders"},
    extension_config={
        "starlette": {"commit_mode": "autocommit"},
    },
)
sqlspec = SQLSpec()
sqlspec.add_config(config)
```

## Common Pitfalls

- **`autocommit` rolls back on 4xx.** A handler that returns `422` after a *successful* state mutation will lose the write. Set `extra_commit_statuses={422}` to keep it.
- **`autocommit` rolls back on 5xx.** Handlers that catch an exception, log it, and return `500` will see a rollback because the status code drives the decision. Use `manual` if you need to commit partial work before reporting failure.
- **Redirects do not commit by default.** If the handler returns `303 See Other` after a write, plain `autocommit` rolls back. Use `autocommit_include_redirect`.
- **`manual` does not mean "no transaction".** The connection is still acquired and held open for the request. If your handler issues `INSERT`s and returns without calling `commit()`, the changes are discarded when the connection is released.
- **Adapters without pooling still get the middleware.** `SQLSpecAutocommitMiddleware` checks `config.supports_connection_pooling` and falls through to `config.create_connection()` + `connection.close()` for non-pooled adapters. Behavior is identical from the handler's point of view.
- **Background tasks scheduled inside a handler share the request connection.** If the handler returns `202 Accepted`, autocommit will commit and the connection goes back to the pool before the task runs. Pass payload data to the task and let the worker open its own connection.
- **`extra_commit_statuses` / `extra_rollback_statuses` are sets, not lists.** Pass `{422}` not `[422]` — the upstream `or set()` fallback works either way at runtime, but the type hint is `set[int] | None`.
- **`commit_mode` is per-config, not per-route.** Multiple routes that share the same adapter config get the same mode. Register a second config (with its own `connection_key`) if different routes need different commit semantics — see [multi-database.md](./multi-database.md).

## Canonical References

- [litestar-sqlstack](https://github.com/cofin/litestar-sqlstack) — uses `commit_mode="autocommit"` on its primary AsyncpgConfig via the Litestar extension; demonstrates `extension_config` shape.
- [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo) — single-bind OracleAsyncConfig with autocommit semantics for chat-session writes.
