---
name: sqlspec
description: "Auto-activate for sqlspec, SQLSpec, SQLFileLoader, drivers, query builders, named SQL, filters, pagination, Arrow, framework extensions, ADK stores, data dictionary, or observers. Not for ORM repositories -- use advanced-alchemy."
---

# SQLSpec Skill

SQLSpec is a **type-safe SQL query mapper for Python** -- NOT an ORM. It provides flexible connectivity with consistent interfaces across 18+ database adapters. Write raw SQL, use the builder API, or load SQL from files. Statements pass through a sqlglot-powered AST pipeline for validation, parameter handling, and dialect conversion.

## Match-Your-Framework — read first

sqlspec ships first-party extensions for five web frameworks. If your project uses one of these, **jump directly to the matching integration guide and skip the others**:

- **Litestar** — `SQLSpecPlugin` with full DI, CLI, observability. The rest of this SKILL.md covers Litestar by default; also see [`references/extensions.md`](references/extensions.md).
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

# Configure the adapter with connection details
config = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://user:pass@localhost:5432/mydb",
        "min_size": 2,
        "max_size": 10,
    },
)
db_manager = SQLSpec()
db_manager.add_config(config)

# Use SQLSpec's session provider for connection lifecycle
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

# SELECT with filters
stmt = (
    sql.select("id", "name", "email")
    .from_("users")
    .where_eq("status", "active")
    .where("created_at > :since", since=cutoff_date)
    .order_by("created_at", desc=True)
    .limit(50)
    .to_statement()
)

# INSERT
stmt = (
    sql.insert("users")
    .columns("name", "email")
    .values(name="Alice", email="alice@example.com")
    .to_statement()
)

# MERGE / upsert
stmt = (
    sql.merge_("inventory")
    .using("updates", on="inventory.product_id = updates.product_id")
    .when_matched().do_update(qty="updates.qty")
    .when_not_matched().do_insert(product_id="updates.product_id", qty="updates.qty")
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
| `execute()` | `SQLResult` | INSERT/UPDATE/DELETE metadata |
| `execute_many()` | `SQLResult` | Batch operation metadata |
| `load_from_arrow()` | `StorageBridgeJob` | Native Arrow bulk ingest |
| `load_from_storage()` | `StorageBridgeJob` | Load staged files or cloud URIs |
| `load_from_records()` | `StorageBridgeJob` | Native bulk ingest for in-memory records |

### Arrow Integration Basics

```python
# Native Arrow on ADBC, DuckDB, BigQuery, Spanner, mssql-python, arrow-odbc,
# and oracledb; conversion path on other adapters unless native_only=True.
arrow_result = await db.select_to_arrow(
    "SELECT * FROM large_dataset WHERE region = $1",
    region,
    return_format="reader",
    batch_size=10_000,
)

# Bulk load from Arrow
await db.load_from_arrow("users", arrow_result)

# Bulk load records through the same native ingest path
await db.load_from_records("users", [{"id": 1, "name": "Ada"}])
```

<workflow>

## Workflow

### Step 1: Choose Adapter and Pattern

| Need | Adapter | Key Feature |
| --- | --- | --- |
| PostgreSQL async | `asyncpg`, `psycopg` | Async, NUMERIC/PYFORMAT params |
| PostgreSQL sync | `psycopg` | Sync+async, PYFORMAT params |
| SQLite | `sqlite`, `aiosqlite` | QMARK params, local dev |
| DuckDB analytics | `duckdb` | Arrow-native OLAP, extension load/install lifecycle |
| MySQL async | `asyncmy` | PYFORMAT params |
| Oracle | `oracledb` | NAMED_COLON params, sync+async |
| BigQuery / Spanner | `bigquery`, `spanner` | NAMED_AT params, cloud job/session controls |
| Raw SQL strings | Driver methods | `select()`, `execute()` |
| Dynamic queries | Query builder | `sql.select()...to_statement()` |
| SQL from files | `SQLFileLoader` | Metadata directives, `-- param:` declarations, caching |
| High-volume ingest | Storage bridge | `load_from_arrow()`, `load_from_storage()`, `load_from_records()` |

### Step 2: Implement

1. Configure the adapter with connection details and pool settings
2. Register the config with `SQLSpec.add_config()` and use `SQLSpec.provide_session(config)` for connection lifecycle
3. Choose the appropriate driver method for your query shape
4. Use `schema_type` parameter for typed results (Pydantic or msgspec models)
5. Apply filters with `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`
6. Use `select_stream(..., native_only=True)` when bounded-memory streaming is mandatory
7. Use `load_from_records()` or `load_from_arrow()` for high-volume ingest; avoid row-by-row `execute_many()` for bulk pipelines

### Step 3: Validate

Run through the validation checkpoint below before considering the work complete.

</workflow>

<guardrails>

## Guardrails

- **Always use typed adapters**: import the specific adapter config, not generic base classes
- **Always use `schema_type`** for query results -- get typed objects, not raw dicts
- **Always use context managers** for driver lifecycle -- `async with db_manager.provide_session(config) as db:`
- **Prefer the query builder** for complex dynamic queries -- avoids string concatenation, handles dialect conversion
- **Prefer `SQLFileLoader`** for static queries -- keeps SQL out of Python, enables caching
- **Use `-- param:` declarations for named SQL files that cross service boundaries** -- load-time and execute-time validation catches name drift and required parameter omissions
- **Use `native_only=True` for streaming or Arrow paths only when fallback is unacceptable** -- unsupported adapters otherwise use eager row conversion
- **Pass regular query bind values as positional arguments** -- `await db.select("... WHERE id = $1", user_id, schema_type=User)`, not `await db.select(..., [user_id], ...)`
- **Never concatenate SQL strings** -- use parameterized queries or the query builder
- **Never hold connections outside context managers** -- connection leaks exhaust the pool
- **Match parameter style to adapter**: `$1` for asyncpg, `%s` for psycopg, `?` for sqlite, `:name` for oracledb
- **Do not invent adapter APIs** -- BigQuery job controls live in `driver_features`; Spanner request controls live in `driver_features` or `provide_session()` kwargs
- **Adapter config / driver modules avoid `from __future__ import annotations`**. Consumer app modules MAY use it.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering SQLSpec code, verify:

- [ ] Adapter config uses the correct import path (`sqlspec.adapters.<name>`)
- [ ] Connection lifecycle uses `SQLSpec.provide_session(config)` context manager
- [ ] Parameter style matches the adapter (see adapter registry table)
- [ ] Query results use `schema_type` for type-safe mapping
- [ ] Complex dynamic queries use the builder API, not string concatenation
- [ ] Filters use SQLSpec filter objects (`LimitOffsetFilter`, etc.) not manual LIMIT/OFFSET
- [ ] Streaming code uses context managers and sets `native_only=True` when eager fallback would be a bug
- [ ] Bulk ingest code uses `load_from_arrow()`, `load_from_storage()`, or `load_from_records()` and checks adapter gates such as MySQL local-infile, Oracle direct path load, BigQuery Storage Write API, or Spanner Batch Write API
- [ ] ADK stores are selected from supported adapter `adk` packages; BigQuery is not an ADK backend

</validation>

<example>

## Example

**Task:** "Set up an asyncpg adapter, define a typed model, and execute a parameterized query with pagination."

```python
from dataclasses import dataclass
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.core.filters import LimitOffsetFilter, OrderByFilter


# --- Typed model ---

@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool


# --- Adapter setup ---

config = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://user:pass@localhost:5432/mydb",
        "min_size": 2,
        "max_size": 10,
    },
)
db_manager = SQLSpec()
db_manager.add_config(config)


# --- Query execution ---

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
        count = await db.select_value(
            "SELECT COUNT(*) FROM users WHERE active = $1", True
        )
        return count
```

</example>

## References Index

> **Choosing between `sqlspec` and `advanced-alchemy`:** `advanced-alchemy` gives you an opinionated ORM service layer with `UUIDAuditBase`, lifecycle hooks, repository / service / Alembic integration, and `OffsetPagination[T]` out of the box — pick it when you want a complete CRUD surface with attribute-style row access and you're happy inside the SQLAlchemy ecosystem. `sqlspec` gives you direct SQL control, 18+ driver adapters (asyncpg, oracledb, DuckDB, BigQuery, SQLite, and more), Arrow result paths for analytics, and a builder API when you need it — pick it when you want explicit SQL, heterogeneous database backends, or Arrow integration. Both skills integrate with Litestar via first-party plugins; see [`../advanced-alchemy/SKILL.md`](../advanced-alchemy/SKILL.md) for the ORM path.

For detailed instructions, patterns, and API guides, refer to the following documents:

### Standards & Style

- **[Code Quality & Mypyc](references/standards.md)** -- Type annotation rules, import standards, test structure.

### Core Utilities

- **[SQLglot Best Practices](references/sqlglot.md)** -- v30+ guardrails, AST manipulation, `copy=False` pattern.

### Architecture & Performance

- **[Architecture & Caching](references/architecture.md)** -- Core data flow, NamespacedCache system, statement/cache tuning, Mypyc compilation.
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

- **[Adapter & Driver Registry](references/adapters.md)** -- Full 18+ adapter registry with dialects and parameter styles.

### Framework & Storage Integrations

- **[Framework Extensions](references/extensions.md)** -- Litestar plugin, FastAPI/Starlette integration.
- **[Storage Integration](references/storage.md)** -- ADK store, Litestar session stores, event channel backends.
- **[Event Channels (Pub/Sub)](references/events.md)** -- `AsyncEventChannel`, subscribe/publish patterns.
- **[ADK Extension](references/adk.md)** -- ADK 2 session/memory stores, scoped state, artifact service contracts.

### Migrations & Schema

- **[Native Migration Runner](references/migrations.md)** -- `sqlspec database` CLI, timestamp versioning, `ddl_migrations` tracker, extension migrations, Litestar `litestar db` integration.

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
