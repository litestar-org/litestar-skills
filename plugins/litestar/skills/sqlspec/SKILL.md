---
name: sqlspec
description: "Auto-activate for sqlspec, SQLSpec, SQLFileLoader, drivers, query builders, named SQL, filters, pagination, Arrow, framework extensions, ADK stores, data dictionary, or observers. Not for ORM repositories."
---

# SQLSpec Skill

SQLSpec is a **type-safe SQL query mapper for Python** -- NOT an ORM. It provides flexible connectivity with consistent interfaces across 18+ database adapters. Write raw SQL, use the builder API, or load SQL from files. All statements pass through a sqlglot-powered AST pipeline for validation and dialect conversion.

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
    users = await db.select_many(
        "SELECT * FROM users WHERE active = $1",
        [True],
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
| `select_value()` | Single scalar | `COUNT(*)`, `MAX()`, existence checks |
| `select_one()` | One row (strict) | Get-by-ID, raises `NotFoundError` |
| `select_one_or_none()` | One row or `None` | Optional lookup |
| `select_many()` | List of rows | Filtered queries, listing |
| `select_to_arrow()` | `pyarrow.Table` | Bulk data export, analytics |
| `execute()` | Row count | INSERT/UPDATE/DELETE |
| `execute_many()` | Row count | Batch operations |

### Arrow Integration Basics

```python
# Zero-copy on DuckDB, ADBC adapters; conversion on others
arrow_table = await db.select_to_arrow(
    "SELECT * FROM large_dataset WHERE region = $1", [region]
)

# Bulk load from Arrow
await db.copy_from_arrow(arrow_table, target_table="users")
```

<workflow>

## Workflow

### Step 1: Choose Adapter and Pattern

| Need | Adapter | Key Feature |
| --- | --- | --- |
| PostgreSQL async | `asyncpg`, `psycopg` | Async, NUMERIC/PYFORMAT params |
| PostgreSQL sync | `psycopg` | Sync+async, PYFORMAT params |
| SQLite | `sqlite`, `aiosqlite` | QMARK params, local dev |
| DuckDB analytics | `duckdb` | Arrow-native, zero-copy |
| MySQL async | `asyncmy` | PYFORMAT params |
| Oracle | `oracledb` | NAMED_COLON params, sync+async |
| BigQuery / Spanner | `bigquery`, `spanner` | NAMED_AT params |
| Raw SQL strings | Driver methods | `select_many()`, `execute()` |
| Dynamic queries | Query builder | `sql.select()...to_statement()` |
| SQL from files | `SQLFileLoader` | Metadata directives, caching |

### Step 2: Implement

1. Configure the adapter with connection details and pool settings
2. Register the config with `SQLSpec.add_config()` and use `SQLSpec.provide_session(config)` for connection lifecycle
3. Choose the appropriate driver method for your query shape
4. Use `schema_type` parameter for typed results (Pydantic or msgspec models)
5. Apply filters with `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`

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
- **Never concatenate SQL strings** -- use parameterized queries or the query builder
- **Never hold connections outside context managers** -- connection leaks exhaust the pool
- **Match parameter style to adapter**: `$1` for asyncpg, `%s` for psycopg, `?` for sqlite, `:name` for oracledb
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
        users = await db.select_many(
            "SELECT id, name, email, active FROM users WHERE active = $1",
            [True],
            *filters,
            schema_type=User,
        )
        return users


async def get_user_count() -> int:
    async with db_manager.provide_session(config) as db:
        count = await db.select_value(
            "SELECT COUNT(*) FROM users WHERE active = $1", [True]
        )
        return count
```

</example>

## Query Builder

The `sql` factory provides a fluent builder API with full method chaining. All builders terminate with `.to_statement()` and pass through sqlglot for validation and dialect conversion.

| Builder | Entry Point | Key Methods |
| --- | --- | --- |
| SELECT | `sql.select(*cols)` | `.from_()`, `.where()`, `.where_eq()`, `.join()`, `.order_by()`, `.limit()`, `.offset()` |
| INSERT | `sql.insert(table)` | `.columns()`, `.values()`, `.returning()` |
| UPDATE | `sql.update(table)` | `.set_()`, `.where()`, `.returning()` |
| DELETE | `sql.delete(table)` | `.where()`, `.returning()` |
| MERGE | `sql.merge_(target)` | `.using()`, `.when_matched()`, `.when_not_matched()` |
| CREATE TABLE | `sql.create_table(name)` | `.column()`, `.primary_key()`, `.if_not_exists()` |
| DROP TABLE | `sql.drop_table(name)` | `.if_exists()`, `.cascade()` |

## ArrowResult

`select_to_arrow()` returns an Apache Arrow `Table` for bulk and analytical workloads:

- **Zero-copy** on DuckDB and ADBC-native adapters — no serialization overhead
- **Conversion path** on other adapters — rows are materialized into an Arrow schema
- Returned tables are compatible with Polars, Pandas, and PyArrow directly
- Use `copy_from_arrow(table, target_table)` for bulk loads back into the database

## Filters

SQLSpec filter objects are passed directly to driver methods alongside the SQL string. They modify the statement before execution.

| Filter | Purpose | Example Use |
| --- | --- | --- |
| `BeforeAfterFilter` | Date range bounds (`before`, `after`) | Audit log queries, time-range pagination |
| `InCollectionFilter` | SQL `IN (...)` clause | Filter by a set of IDs or enum values |
| `LimitOffsetFilter` | Page-based pagination | `limit=25, offset=50` |
| `OrderByFilter` | Dynamic sort columns and direction | User-supplied sort fields |
| `SearchFilter` | Text search (`ILIKE` / `LIKE`) | Full-text style search on string columns |

Filters are composable — pass multiple to a single `select_many()` call and they are applied in order.

## Framework Integrations

| Framework | Integration | Key Feature |
| --- | --- | --- |
| Litestar | `SQLSpecPlugin` | Dependency injection of typed driver; auto session lifecycle |
| FastAPI / Starlette | Middleware | Request-scoped connection; injects driver into route dependencies |
| Flask | Extension | `init_app()` pattern; driver available via `g` or `current_app` |

`SQLSpecPlugin` for Litestar registers the driver as a DI provider — inject it into route handlers via type annotation without manual context management.

## Event Channels

For databases that support server-side pub/sub (e.g., PostgreSQL `LISTEN`/`NOTIFY`):

- Use `AsyncEventChannel` to subscribe to named channels
- Publish with `NOTIFY channel, payload` from SQL or from the `publish()` method
- Handlers receive `EventMessage` objects with channel name, payload, and PID
- Useful for real-time cache invalidation, cross-process coordination, and background job triggers

## Key Design Principles

1. **Single Source of Truth**: The `SQL` object holds all state for a given statement
2. **Immutability**: All operations on a `SQL` object return new instances
3. **Type Safety**: Parameters carry type information through the processing pipeline
4. **Protocol-Based Design**: Uses Python protocols for runtime type checking instead of inheritance
5. **Single-Pass Processing**: Parse once, transform once, validate once

## References Index

> **Choosing between `sqlspec` and `advanced-alchemy`:** `advanced-alchemy` gives you an opinionated ORM service layer with `UUIDAuditBase`, lifecycle hooks, repository / service / Alembic integration, and `OffsetPagination[T]` out of the box — pick it when you want a complete CRUD surface with attribute-style row access and you're happy inside the SQLAlchemy ecosystem. `sqlspec` gives you direct SQL control, 18+ driver adapters (asyncpg, oracledb, DuckDB, BigQuery, SQLite, and more), Arrow-native result streams for analytics, and a builder API when you need it — pick it when you want explicit SQL, heterogeneous database backends, or Arrow integration. Both skills integrate with Litestar via first-party plugins; see [`../advanced-alchemy/SKILL.md`](../advanced-alchemy/SKILL.md) for the ORM path.

For detailed instructions, patterns, and API guides, refer to the following documents:

### Standards & Style

- **[Code Quality & Mypyc](references/standards.md)** -- Type annotation rules, import standards, test structure.

### Core Utilities

- **[SQLglot Best Practices](references/sqlglot.md)** -- v30+ guardrails, AST manipulation, `copy=False` pattern.

### Architecture & Performance

- **[Architecture & Caching](references/architecture.md)** -- Core data flow, NamespacedCache system, Mypyc compilation.
- **[Data Dictionary](references/data-dictionary.md)** -- Dialect feature flags, runtime introspection (`get_tables`, `get_columns`, `get_indexes`), driver-side metadata API.

### Query Building & Execution

- **[Query Builder API](references/query_builder.md)** -- `sql` factory: select, insert, update, delete, merge.
- **[Driver Method Reference](references/driver_api.md)** -- `select_value()`, `select_one()`, `select_many()`, `select_to_arrow()`.
- **[Filter & Pagination System](references/filters.md)** -- `LimitOffsetFilter`, `OrderByFilter`, `SearchFilter`.

### Data Integration

- **[Arrow & ADBC Integration](references/arrow.md)** -- `select_to_arrow()` zero-copy, `copy_from_arrow()` bulk loading.
- **[SQL File Loading](references/loader.md)** -- `SQLFileLoader` with search paths, metadata directives.

### Adapters & Drivers

- **[Adapter & Driver Registry](references/adapters.md)** -- Full 18+ adapter registry with dialects and parameter styles.

### Framework & Storage Integrations

- **[Framework Extensions](references/extensions.md)** -- Litestar plugin, FastAPI/Starlette integration.
- **[Storage Integration](references/storage.md)** -- ADK store, Litestar session stores, event channel backends.
- **[Event Channels (Pub/Sub)](references/events.md)** -- `AsyncEventChannel`, subscribe/publish patterns.
- **[ADK Extension](references/adk.md)** -- `SQLSpecSessionService`, `SQLSpecMemoryService`, `SQLSpecArtifactService`, per-adapter ADK stores.

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
