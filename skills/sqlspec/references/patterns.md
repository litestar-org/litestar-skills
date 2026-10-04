# SQLSpec Design Patterns

## Service Layer Pattern

`SQLSpecAsyncService` ships upstream in `sqlspec.service`. Use it as the base class for app services that wrap an async driver with helpers like `paginate`, `get_one`, `exists`, and `begin_transaction`.

```python
from sqlspec.core.filters import LimitOffsetFilter, OffsetPagination
from sqlspec.service import SQLSpecAsyncService


class UserService(SQLSpecAsyncService):
    async def list_users(self, page: int = 1, page_size: int = 20) -> OffsetPagination[User]:
        return await self.paginate(
            "SELECT * FROM users ORDER BY created_at DESC",
            LimitOffsetFilter(limit=page_size, offset=page_size * (page - 1)),
            schema_type=User,
        )

    async def get_user(self, user_id: str) -> User:
        return await self.get_one(
            "SELECT * FROM users WHERE id = $1",
            user_id,
            schema_type=User,
        )

    async def user_exists(self, email: str) -> bool:
        return await self.exists(
            "SELECT 1 FROM users WHERE email = $1",
            email,
        )

    async def transfer_funds(self, from_id: str, to_id: str, amount: float) -> None:
        async with self.begin_transaction() as tx:
            await tx.execute(
                "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
                amount,
                from_id,
            )
            await tx.execute(
                "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
                amount,
                to_id,
            )
```

### Key Service Methods

| Method | Returns | Description |
| --- | --- | --- |
| `paginate()` | `OffsetPagination[T]` | Paginated query with total count |
| `get_one()` | `T` | Single row or raise `NotFoundError` |
| `exists()` | `bool` | Check if any row matches |
| `begin_transaction()` | context manager | Explicit transaction scope |

---

## Batch Operations

### execute_many with Tuples

For bulk inserts and updates, pass parameters as a list of tuples:

```python
users = [
    ("alice", "alice@example.com"),
    ("bob", "bob@example.com"),
    ("carol", "carol@example.com"),
]

result = await db_session.execute_many(
    "INSERT INTO users (name, email) VALUES ($1, $2)",
    users,
)
print(f"Inserted {result.rows_affected} rows")
```

### Batch with Dicts

```python
users = [
    {"name": "alice", "email": "alice@example.com"},
    {"name": "bob", "email": "bob@example.com"},
]

result = await db_session.execute_many(
    "INSERT INTO users (name, email) VALUES (:name, :email)",
    users,
)
```

---

## Upsert with on_conflict

Use the query builder for INSERT ... ON CONFLICT:

```python
from sqlspec import sql

query = (
    sql.insert("users")
    .columns("id", "name", "email", "updated_at")
    .values(id=1, name="Alice", email="alice@example.com", updated_at="now()")
    .on_conflict("id")
    .do_update(name="src.name", email="src.email", updated_at="NOW()")
)

stmt = query.to_statement()
await db_session.execute(stmt)
```

---

## Complex SELECT with GROUP BY

```python
from sqlspec import sql

query = (
    sql.select("department", "COUNT(*) AS headcount", "AVG(salary) AS avg_salary")
    .from_("employees")
    .join("departments", on="employees.dept_id = departments.id")
    .where("employees.active = true")
    .group_by("department")
    .having("COUNT(*) > 5")
    .order_by("headcount DESC")
    .limit(10)
)

stmt = query.to_statement()
rows = await db_session.select(stmt, schema_type=DeptSummary)
```

---

## MERGE Statement Builder

### High Performance Upsert

Use `sql.merge(dialect=...)` only for dialects that implement `MERGE`, including PostgreSQL 15+, Oracle, BigQuery, SQL Server (T-SQL), and IBM Db2. Use `INSERT ... ON CONFLICT` or the dialect-specific duplicate-key API for SQLite, DuckDB, and MySQL, or `sql.upsert(table, dialect=...)` to select the dialect-appropriate form automatically.

```python
from sqlspec import sql

query = (
    sql.merge(dialect="postgres")
    .into("products", alias="t")
    .using({"id": 1, "name": "Widget"}, alias="src")
    .on("t.id = src.id")
    .when_matched_then_update(name="src.name")
    .when_not_matched_then_insert(id="src.id", name="src.name")
)
```

### Bulk Merge Upsert

For 100+ rows, pass a list of dicts:

```python
products = [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]

query = (
    sql.merge(dialect="postgres")
    .into("products", alias="t")
    .using(products, alias="src")
    .on("t.id = src.id")
    .when_matched_then_update(name="src.name")
    .when_not_matched_then_insert(id="src.id", name="src.name")
)
```

---

## Security Patterns

### Injection Prevention

Wrap user-supplied identifiers using `parse_one` for AST validation before use:

```python
from sqlglot import parse_one, exp


def sanitize_table(user_input: str) -> str:
    parsed = parse_one(f"SELECT * FROM {user_input}")
    table = parsed.find(exp.Table)
    if not table or not isinstance(table.this, exp.Identifier):
        raise ValueError("Invalid table name")
    return table.name
```

---

## AST Manipulation Patterns

### Tenant Filter Injection

Programmatically enforce multi-tenancy by injecting WHERE clauses into the AST:

```python
from sqlglot import parse_one, exp


def add_tenant_guard(raw_sql: str, tenant_id: int) -> str:
    ast = parse_one(raw_sql)
    if select := ast.find(exp.Select):
        select.where(exp.column("tenant_id").eq(tenant_id), copy=False)
    return ast.sql()
```

### Dynamic Column Selection

```python
from sqlglot import parse_one, exp, select


def build_projection(columns: list[str], table: str) -> str:
    query = select(*[exp.column(c) for c in columns]).from_(table)
    return query.sql()
```

---

## Table Fixtures (`sqlspec.utils.fixtures`)

Load and export per-table `.json` or `.jsonl` (including `.gz`) fixtures with automatic schema-driven type coercion, sparse row normalization, topological `table_order`, `conflict_keys` upserts (accepting a bare column name string or sequence of column names per table), `ignore_unknown_columns=True` for evolved schemas, `exclude_update_columns` to preserve immutable columns (such as `["created_at"]`) on conflict updates, `batch_size`, and identity sequence resynchronization (`resync_sequences=True`). Exported JSON strings that look like JSON literals (such as `"true"` or `"[1]"`) round-trip as strings rather than being coerced to booleans or arrays:

```python
from pathlib import Path
from sqlspec.utils.fixtures import export_table_fixtures_async, load_table_fixtures_async

loaded_counts = await load_table_fixtures_async(
    db_session,
    Path("db/fixtures"),
    table_order=["roles", "users"],
    conflict_keys={"roles": "slug", "users": ["email"]},
    ignore_unknown_columns=True,
    exclude_update_columns=["created_at"],
    resync_sequences=True,
)

exported_paths = await export_table_fixtures_async(
    db_session,
    Path("db/fixtures/snapshots"),
    tables=["roles", "users"],
    jsonl=True,
    compress=True,
)
```

Synchronous drivers use `load_table_fixtures_sync()` and `export_table_fixtures_sync()`.

---

## ID Generation Helpers (`uuid4`, `uuid6`, `uuid7`, `nanoid`)

Top-level `sqlspec` (and `sqlspec.utils.uuids`) exports fast, dependency-consistent ID generators (`uuid7` for time-ordered UUID primary keys, `uuid4`, `uuid6`, and `nanoid`):

```python
from sqlspec import nanoid, uuid7

record_id = uuid7()
public_slug = nanoid()
```
