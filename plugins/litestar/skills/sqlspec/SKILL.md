---
name: sqlspec
description: "Auto-activate for sqlspec, SQLSpec, SQLFileLoader, drivers, query builders, named SQL, filters, pagination, Arrow, framework extensions, ADK stores, or observers. Not for ORM repositories — use advanced-alchemy."
---

# SQLSpec Skill

SQLSpec is a **type-safe SQL query mapper for Python** -- NOT an ORM. It provides flexible connectivity with consistent interfaces across 20 database adapter packages. Write raw SQL, use the builder API, or load SQL from files. Statements pass through a sqlglot-powered AST pipeline for validation, parameter handling, and dialect conversion.

## Match-Your-Framework — read first

sqlspec ships first-party extensions for five web frameworks. If your project uses one of these, **jump directly to the matching integration guide and skip the others**:

- **Litestar** — register configs on `SQLSpec`, then pass that registry to `SQLSpecPlugin`. The plugin adds DI, the `litestar db` CLI, and request observability. See [`references/extensions.md`](references/extensions.md).
- **FastAPI** → [`references/fastapi-integration.md`](references/fastapi-integration.md) — `Depends(plugin.provide_session())` DI, `Annotated[...]` handlers, filter providers.
- **Flask** → [`references/flask-integration.md`](references/flask-integration.md) — `plugin.init_app(app)`, pull-based `plugin.get_session()`, async-via-portal.
- **Starlette** → [`references/starlette-integration.md`](references/starlette-integration.md) — `request.state`-based session access, lifespan wrapping, middleware variants.
- **Sanic** — first-party ASGI-style extension for Sanic applications; match Sanic's app/request lifecycle instead of copying Litestar DI examples.

Shared topics that apply to every framework live in [`references/commit-modes.md`](references/commit-modes.md) (autocommit / manual middleware) and [`references/multi-database.md`](references/multi-database.md) (multi-config registry). Read the framework guide first, then those for depth.

The rest of this SKILL.md covers framework-agnostic topics: adapter setup, query builder, driver methods, filters, observability, migrations, the ADK extension, and data-dictionary introspection.

## Code Style Rules

- **`from __future__ import annotations` rule** — SQLSpec adapter config modules and driver definitions avoid `from __future__ import annotations` because configs are introspected at runtime. Consumer application modules (handlers, services, tests that *use* a configured driver) MAY and typically SHOULD use it — canonical Litestar apps use it in 100+ files.

## Quick Reference

### Adapter Pattern

```python
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig

config = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://user:pass@localhost:5432/mydb",
        "min_size": 2,
        "max_size": 10,
    },
)
db_manager = SQLSpec()
db_manager.add_config(config)

async with db_manager.provide_session(config) as db:
    users = await db.select(
        "SELECT * FROM users WHERE active = $1",
        True,
        schema_type=User,
    )
```

### Query Builder Essentials

```python
from sqlspec import sql

stmt = (
    sql.select("id", "name", "email")
    .from_("users")
    .where_eq("status", "active")
    .where("created_at > :since", since=cutoff_date)
    .order_by("created_at", desc=True)
    .limit(50)
    .to_statement()
)

insert_stmt = (
    sql.insert("users").columns("name", "email").values(name="Alice", email="alice@example.com").to_statement()
)

merge_stmt = (
    sql.merge("inventory", dialect="postgres")
    .using("updates")
    .on("inventory.product_id = updates.product_id")
    .when_matched_then_update(qty="updates.qty")
    .when_not_matched_then_insert(product_id="updates.product_id", qty="updates.qty")
    .to_statement()
)
```

### Driver Method Summary

| Method | Returns | Use Case |
| --- | --- | --- |
| `select()` / `fetch()` | List of rows | Filtered queries, listing |
| `select_value()` | Single scalar | `COUNT(*)`, `MAX()`, existence checks |
| `select_value_or_none()` | Scalar or `None` | Optional scalar lookup |
| `select_one()` | One row (strict) | Get-by-ID, raises `NotFoundError` |
| `select_one_or_none()` | One row or `None` | Optional lookup |
| `select_with_total()` | Rows plus total | Pagination |
| `select_stream()` / `fetch_stream()` | Context-managed row stream | Bounded row iteration where adapter supports native streaming |
| `select_to_arrow()` / `fetch_to_arrow()` | `ArrowResult` | Bulk data export, analytics |
| `select_to_storage()` | `StorageBridgeJob` | Export query results to local or cloud storage |
| `execute()` | `SQLResult` | INSERT/UPDATE/DELETE metadata |
| `execute_many()` | `SQLResult` | Batch operation metadata |
| `execute_script()` | `SQLResult` | Multi-statement SQL script execution |
| `execute_stack()` | `tuple[StackResult, ...]` | Ordered statement-stack execution |
| `load_from_arrow()` | `StorageBridgeJob` | Adapter-supported Arrow ingest |
| `load_from_storage()` | `StorageBridgeJob` | Adapter-supported staged-file ingest |
| `load_from_records()` | `StorageBridgeJob` | Records normalized through the Arrow ingest path |
| `transaction()` | Context manager | Atomic transaction or savepoint scope on a driver |

### Arrow Integration Basics

```python
arrow_result = await db.select_to_arrow(
    "SELECT * FROM large_dataset WHERE region = $1",
    region,
    return_format="reader",
    batch_size=10_000,
)

await db.load_from_arrow("users", arrow_result)
await db.load_from_records("users", [{"id": 1, "name": "Ada"}])
```

<workflow>

## Workflow

### Step 1: Choose Adapter and Pattern

| Need | Adapter | Key Feature |
| --- | --- | --- |
| PostgreSQL async | `asyncpg`, `psycopg` | Async, NUMERIC/PYFORMAT params, auto-probed `pgvector` / `pg_textsearch` / `paradedb` |
| PostgreSQL sync | `psycopg` | Sync+async, PYFORMAT params |
| SQLite | `sqlite`, `aiosqlite` | QMARK params, local dev |
| DuckDB analytics | `duckdb` | Arrow-native OLAP, extension load/install lifecycle, direct object-store transfer |
| Arrow / multi-engine ETL | `adbc` | Arrow-native ingest/export across DuckDB, PostgreSQL, BigQuery, Flight SQL |
| MySQL async | `asyncmy` | PYFORMAT params |
| Oracle | `oracledb` | NAMED_COLON params, sync+async |
| IBM Db2 | `db2` | QMARK params, sync+async via `ibm_db`, `SYSCAT` catalog reflection |
| BigQuery / Spanner | `bigquery`, `spanner` | NAMED_AT params, cloud job/session controls |
| Raw SQL strings | Driver methods | `select()`, `execute()` |
| Dynamic queries | Query builder | `sql.select()...to_statement()`, `sql.update()...from_()`, `sql.upsert()` |
| SQL from files | `SQLFileLoader` | Metadata directives, `-- param:`, `-- fragment:`, `/* include: */`, `/* slot: */`, caching |
| High-volume ingest/export | Storage bridge | Check the adapter matrix before selecting `load_from_arrow()`, `load_from_storage()`, `load_from_records()`, or `select_to_storage()` |

### Step 2: Implement

1. Configure the adapter with connection details (standardized aliases like `dsn`/`url`/`conninfo`, `database`/`dbname`, `user`/`username` normalize automatically) and pool settings
2. Register the config with `SQLSpec.add_config()` and use `SQLSpec.provide_session(config)` or config-backed `SQLSpecAsyncService(config=..., loader=...)` for connection lifecycle
3. Choose the appropriate driver method for your query shape
4. Use `schema_type` parameter for typed results (msgspec Structs, dataclasses, or Pydantic models)
5. Apply filters with `LimitOffsetFilter`, `CursorFilter`, `OrderByFilter`, `SearchFilter`, `BeforeAfterFilter`, or `InCollectionFilter`
6. Use `select_stream(..., native_only=True)` when bounded-memory streaming is mandatory
7. Check adapter ingest capabilities, then use `load_from_records()`, `load_from_arrow()`, `load_from_storage()`, or `select_to_storage()` for high-volume data movement

### Step 3: Validate

Run through the validation checkpoint below before considering the work complete.

</workflow>

<guardrails>

## Guardrails

- **Always use typed adapters**: import the specific adapter config, not generic base classes
- **Always use `schema_type`** for query results -- get typed objects, not raw dicts
- **Always use context managers** for driver lifecycle -- `async with db_manager.provide_session(config) as db:` or `async with service.provide_session() as db:`
- **Prefer the query builder** for complex dynamic queries -- avoids string concatenation, handles dialect conversion
- **Prefer `SQLFileLoader`** for static queries -- keeps SQL out of Python, supports reusable `-- fragment:` / `/* include: */` blocks and validated `/* slot: */` splicing, and reuses the global file-cache namespace
- **Use `-- param:` declarations for named SQL files that cross service boundaries** -- load-time and execute-time validation catches name drift and required parameter omissions
- **Use `native_only=True` for streaming or Arrow paths only when fallback is unacceptable** -- unsupported adapters otherwise use eager row conversion
- **Pass regular query bind values as positional arguments** -- `await db.select("... WHERE id = $1", user_id, schema_type=User)`, not `await db.select(..., [user_id], ...)`
- **Never concatenate SQL strings** -- use parameterized queries, query builder expressions, or declared `/* slot: <name> */` fragments
- **Never hold connections outside context managers** -- connection leaks exhaust the pool; prefer config-backed services (`SQLSpecAsyncService(config=...)`) when operations should hold a connection only for the duration of a single query or `begin_transaction()` block
- **Match parameter style to adapter**: `$1` for asyncpg, `%s` for psycopg, `?` for sqlite/duckdb/db2, `:name` for oracledb
- **Cloud adapter controls** -- BigQuery job controls live in `driver_features`; Spanner request controls live in `driver_features` or `provide_session()` kwargs
- **Adapter config / driver modules avoid `from __future__ import annotations`**. Consumer app modules MAY use it.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering SQLSpec code, verify:

- [ ] Adapter config uses the correct import path (`sqlspec.adapters.<name>`)
- [ ] Connection lifecycle uses `SQLSpec.provide_session(config)` or `service.provide_session()` context manager
- [ ] Parameter style matches the adapter (see adapter registry table)
- [ ] Query results use `schema_type` for type-safe mapping
- [ ] Complex dynamic queries use the builder API or declared SQL slots, not string concatenation
- [ ] Filters use SQLSpec filter objects (`LimitOffsetFilter`, `CursorFilter`, `OrderByFilter`, etc.) not manual LIMIT/OFFSET
- [ ] Dishka-first Litestar apps that disable SQLSpec DI set `extension_config={"litestar": {"disable_di": True, "manage_lifespan": True}}` when `SQLSpecPlugin` should still manage pool lifespan
- [ ] Streaming code uses context managers and sets `native_only=True` when eager fallback would be a bug
- [ ] Bulk ingest/export code checks the adapter matrix before using `load_from_arrow()`, `load_from_storage()`, `load_from_records()`, or `select_to_storage()`
- [ ] ADK stores are selected from supported adapter `adk` packages; BigQuery is not an OLTP live-agent ADK backend

</validation>

<example>

## Example

**Task:** "Set up an asyncpg adapter, define a typed model, and execute a parameterized query with pagination."

```python
from dataclasses import dataclass
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.core.filters import LimitOffsetFilter, OrderByFilter


@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool


config = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://user:pass@localhost:5432/mydb",
        "min_size": 2,
        "max_size": 10,
    },
)
db_manager = SQLSpec()
db_manager.add_config(config)


async def list_active_users(page: int = 1, page_size: int = 25) -> list[User]:
    filters = [
        OrderByFilter(field_name="name", sort_order="asc"),
        LimitOffsetFilter(limit=page_size, offset=(page - 1) * page_size),
    ]

    async with db_manager.provide_session(config) as db:
        users = await db.select(
            "SELECT id, name, email, active FROM users WHERE active = $1",
            True,
            *filters,
            schema_type=User,
        )
        return users


async def get_user_count() -> int:
    async with db_manager.provide_session(config) as db:
        count = await db.select_value("SELECT COUNT(*) FROM users WHERE active = $1", True)
        return count
```

</example>

## References Index

> **Choosing between `sqlspec` and `advanced-alchemy`:** `advanced-alchemy` gives you an opinionated ORM service layer with `UUIDAuditBase`, lifecycle hooks, repository / service / Alembic integration, and `OffsetPagination[T]` out of the box — pick it when you want a complete CRUD surface with attribute-style row access and you're happy inside the SQLAlchemy ecosystem. `sqlspec` gives you direct SQL control, 20 adapter packages (asyncpg, oracledb, Db2, DuckDB, BigQuery, SQLite, and more), Arrow result paths for analytics, and a builder API when you need it — pick it when you want explicit SQL, heterogeneous database backends, or Arrow integration. Both skills integrate with Litestar via first-party plugins; see [`../advanced-alchemy/SKILL.md`](../advanced-alchemy/SKILL.md) for the ORM path.

For detailed instructions, patterns, and API guides, refer to the following documents:

### Standards & Style

- **[Code Quality & Mypyc](references/standards.md)** -- Type annotation rules, import standards, test structure.

### Core Utilities

- **[SQLglot Best Practices](references/sqlglot.md)** -- v30+ guardrails, AST manipulation, `copy=False` pattern.

### Architecture & Performance

- **[Architecture & Caching](references/architecture.md)** -- Core data flow, global cache configuration, namespaces, and driver-local statement caches.
- **[Performance & Cloud Controls](references/performance.md)** -- Bounded async bridge, cache/fetch tuning, BigQuery job controls, Spanner session controls.
- **[Data Dictionary](references/data-dictionary.md)** -- Dialect feature flags, runtime introspection (`get_tables`, `get_columns`, `get_indexes`), ADBC native metadata/statistics.

### Query Building & Execution

- **[Query Builder API](references/query_builder.md)** -- `sql` factory: select, insert, update, delete, merge.
- **[Driver Method Reference](references/driver_api.md)** -- `select()`, `select_one()`, `select_stream()`, `select_to_arrow()`, load methods.
- **[Filter & Pagination System](references/filters.md)** -- `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`.

### Data Integration

- **[Arrow & ADBC Integration](references/arrow.md)** -- `select_to_arrow()` formats, Arrow-native paths, conversion fallbacks.
- **[Native Bulk Ingest](references/bulk-ingest.md)** -- `load_from_arrow()`, `load_from_storage()`, `load_from_records()`, adapter gates.
- **[SQL File Loading](references/loader.md)** -- `SQLFileLoader` with search paths, metadata directives.

### Adapters & Drivers

- **[Adapter & Driver Registry](references/adapters.md)** -- Full 20-adapter registry with dialects and parameter styles.

### Framework & Storage Integrations

- **[Framework Extensions](references/extensions.md)** -- Litestar plugin, FastAPI/Starlette integration.
- **[Storage Integration](references/storage.md)** -- ADK store, Litestar session stores, event channel backends.
- **[Event Channels (Pub/Sub)](references/events.md)** -- `AsyncEventChannel`, subscribe/publish patterns.
- **[ADK Extension](references/adk.md)** -- ADK 2 session/memory stores, scoped state, artifact service contracts.

### Migrations & Schema

- **[Native Migration Runner](references/migrations.md)** -- standalone `sqlspec` CLI, timestamp versioning, `ddl_migrations` tracker, extension migrations, and Litestar `litestar db` integration.

### Observability

- **[Observability & Tracing](references/observability.md)** -- Telemetry semantics, correlation extraction.

### Advanced Patterns

- **[Design Patterns](references/patterns.md)** -- Service layer, batch operations, upsert, AST tenant filters.
- **[Service Patterns](references/service-patterns.md)** -- SQLSpecAsyncService base, named SQL templates via db_manager.get_sql, direct driver API (select_value / select_one / execute), variadic filter composition, create_filter_dependencies() wiring.
- **[Dishka Integration](references/dishka-integration.md)** -- FromDishka as Inject alias, multi-provider pattern (REQUEST-scoped domain services, REQUEST-scoped driver, APP-scoped singletons), handler injection.
- **[Vector Search](references/vector-search.md)** — Oracle VECTOR_DISTANCE cosine similarity, Vertex AI embedding generation, SHA256-keyed embedding cache, intent classification via exemplar similarity, pgvector cross-reference.

## Key Resources

- **SQLglot Docs**: <https://sqlglot.com/sqlglot.html>
- **SQLglot GitHub**: <https://github.com/tobymao/sqlglot>
- **Mypyc Docs**: <https://mypyc.readthedocs.io/>
- **PyArrow Docs**: <https://arrow.apache.org/docs/python/>

## Official References

- <https://sqlspec.dev/>
- <https://sqlspec.dev/changelog.html>
- <https://github.com/litestar-org/sqlspec>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
