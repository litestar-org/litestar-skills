# SQLSpec Query Builder API

## Overview

The `sql` factory object is the primary entry point for building parameterized SQL statements programmatically. Builder methods mutate the current builder and return it for chaining. Do not reuse one builder as multiple query templates. Convert the finished builder to an executable `SQL` object with `.to_statement()`, or inspect a `BuiltQuery` with `.build(dialect=...)`.

```python
from sqlspec import sql
```

**Preferred pattern:** Use the AST builder to dynamically append filters and conditions to base queries. This lets you store a base query in a SQL file (via `SQLFileLoader`) and compose runtime conditions on top of it — the AST ensures correct SQL generation across dialects without string concatenation.

```python
from sqlspec.loader import SQLFileLoader

loader = SQLFileLoader()
loader.load_sql("./sql")

base = loader.get_sql("list-users")
```

You can pass SQLSpec filter objects directly to driver methods or `apply_filter()` — the driver applies them to the `SQL` statement or builder AST automatically:

```python
from sqlspec.core.filters import LimitOffsetFilter, OrderByFilter, SearchFilter

base = loader.get_sql("list-users")

filters = [
    SearchFilter(field_name="name", value="alice"),
    OrderByFilter(field_name="created_at", sort_order="desc", nulls="last"),
    LimitOffsetFilter(limit=20, offset=0),
]

rows = await db_session.select(base, *filters, schema_type=User)
rows, total = await db_session.select_with_total(base, *filters, schema_type=User)
```

This approach gives you:

- **Single source of truth**: base SQL lives in a file, reviewed and optimized once
- **Composability**: runtime filters are appended via AST — no string formatting or injection risk
- **Dialect portability**: the builder handles parameter style conversion (`$1`, `?`, `%s`, `:name`) automatically
- **Reusability**: one base query serves many endpoints with different filter combinations
- **Filter objects**: pass `StatementFilter` instances to driver methods — they compose with the query at execution time

---

## sql.select()

Build SELECT statements with a fluent API:

```python
query = (
    sql.select("id", "name", "email").from_("users").where("active = true").order_by("name ASC").limit(20).offset(40)
)
```

### Full Method Reference

| Method | Description | Example |
| --- | --- | --- |
| `.select(*cols)` | Columns to select | `sql.select("id", "name")` |
| `.from_(table)` | Source table | `.from_("users")` |
| `.join(table, on=)` | INNER JOIN | `.join("orders", on="users.id = orders.user_id")` |
| `.left_join(table, on=)` | LEFT JOIN | `.left_join("profiles", on="users.id = profiles.user_id")` |
| `.where(expr)` | WHERE clause (AND-combined) | `.where("active = true")` |
| `.where_eq(column, value)` | WHERE col = value (parameterized) | `.where_eq("status", "active")` |
| `.group_by(*cols)` | GROUP BY | `.group_by("department")` |
| `.having(expr)` | HAVING clause | `.having("COUNT(*) > 5")` |
| `.order_by(*exprs)` | ORDER BY | `.order_by("created_at DESC")` |
| `.limit(n)` | LIMIT | `.limit(20)` |
| `.offset(n)` | OFFSET | `.offset(40)` |
| `.distinct()` | SELECT DISTINCT | `.distinct()` |

### Set Operations

```python
active = sql.select("id", "name").from_("active_users")
archived = sql.select("id", "name").from_("archived_users")

all_users = active.union(archived)
common = active.intersect(archived)
only_active = active.except_(archived)
```

### Common Table Expressions (CTEs)

`with_()` and `with_cte()` work on `SELECT`, `INSERT`, `UPDATE`, and `DELETE` builders, preserving CTEs across DML compilation:

```python
query = (
    sql.select("*")
    .with_cte("recent_orders", "SELECT * FROM orders WHERE created_at > now() - interval '7 days'")
    .from_("recent_orders")
    .where("total > 100")
)

query_with = (
    sql.select("*")
    .with_("top_customers", "SELECT user_id, SUM(total) as total FROM orders GROUP BY user_id")
    .from_("top_customers")
    .order_by("total DESC")
    .limit(10)
)
```

### Pivot / Unpivot

```python
query = sql.select("*").from_("sales").pivot("SUM", "revenue", "quarter", ["Q1", "Q2", "Q3", "Q4"])

query = sql.select("*").from_("quarterly_sales").unpivot("revenue", "quarter", ["q1", "q2", "q3", "q4"])
```

---

## sql.insert()

```python
query = (
    sql.insert().into("users").columns("name", "email").values(name="Alice", email="alice@example.com").returning("id")
)

query_from_select = (
    sql.insert()
    .into("user_archive")
    .columns("id", "name", "email")
    .from_select(sql.select("id", "name", "email").from_("users").where_eq("deleted", True))
)

query_on_conflict = (
    sql.insert()
    .into("users")
    .columns("id", "name", "email")
    .values(id=1, name="Alice", email="alice@example.com")
    .on_conflict("id")
    .do_update(name="EXCLUDED.name", email="EXCLUDED.email")
)
```

---

## sql.update() and `UPDATE ... FROM`

`sql.update()` supports `.from_(*tables)` for joined `UPDATE ... FROM` statements (accepting table names, aliased tables, subqueries, or `Select` builders) and preserves attached CTEs:

```python
query = sql.update("users").set(name="Bob", updated_at="now()").where_eq("id", 1).returning("id", "name")

query_from = (
    sql.update("users")
    .set(department="Engineering")
    .from_("department_changes")
    .where("users.id = department_changes.user_id")
    .returning("users.id")
)
```

---

## sql.delete()

```python
query = sql.delete().from_("users").where_eq("id", 1).returning("id")
```

---

## sql.merge() and sql.upsert()

Use `sql.merge(table, dialect=...)` when the target table or dialect is known. `sql.merge_` is a no-argument property shorthand; never call it as a function.

```python
query = (
    sql.merge("target_table", dialect="postgres")
    .using(source_data, alias="src")
    .on("target_table.id = src.id")
    .when_matched_then_update(name="src.name", updated_at="now()")
    .when_not_matched_then_insert(id="src.id", name="src.name")
)
```

`sql.upsert(table, dialect=...)` automatically generates `MERGE` (PostgreSQL 15+, Oracle, BigQuery, T-SQL), `INSERT ... ON CONFLICT` (SQLite, DuckDB), or `INSERT ... ON DUPLICATE KEY UPDATE` (MySQL/MariaDB) depending on dialect capabilities.

---

## Dialect-Aware DDL Builders

`sql.create_table(table, dialect=...)` and `sql.alter_table(table, dialect=...)` parse column data types against the configured target dialect and preserve dialect overrides on `.build(dialect=...)` and `.to_statement()`:

```python
create_users = (
    sql.create_table("users", dialect="postgres")
    .if_not_exists()
    .column("id", "UUID", primary_key=True)
    .column("email", "TEXT", not_null=True, unique=True)
    .column("created_at", "TIMESTAMPTZ", default="CURRENT_TIMESTAMP", not_null=True)
)
```

---

## Window Functions, Column Ordering & Expressions

SQLSpec provides fluent window function helpers and column expression builders (`sql.column("col")` / `sql.col`):

```python
query = (
    sql.select(
        "id",
        "department",
        sql.row_number(partition_by="department", order_by="salary DESC").as_("rank"),
        sql.sum_over("salary", partition_by="department").as_("dept_total"),
        sql.lag("salary", partition_by="department", order_by="hire_date").as_("prev_salary"),
    )
    .from_("employees")
    .where(sql.column("department").any_(["eng", "product"]))
    .order_by(sql.column("salary").desc(nulls="last"))
)
```

### Vector Distance Expressions

For vector similarity search across dialects (PostgreSQL pgvector, Oracle, MySQL, BigQuery, DuckDB):

```python
query_vector = [0.1, 0.2, 0.3]
distance = sql.column("embedding").vector_distance(query_vector, metric="cosine")

query = sql.select("id", "title").from_("documents").where(distance < 0.3).order_by(distance.asc()).limit(10)
```

Supported metrics: `"cosine"`, `"euclidean"`, `"inner_product"`, `"euclidean_squared"`.

---

## Statement Stacks

`StatementStack` provides an immutable builder for batching heterogeneous SQL operations:

```python
from sqlspec import StatementStack

stack = (
    StatementStack()
    .push_execute("INSERT INTO audit_log (action) VALUES ($1)", "user_created")
    .push_execute_many("INSERT INTO user_roles (user_id, role) VALUES ($1, $2)", [(1, "admin"), (1, "member")])
    .push_execute_script("ANALYZE users;")
)

results = await db_session.execute_stack(stack)
```

---

## Converting to Executable SQL

### .to_statement()

Convert a builder chain into an executable `SQL` object:

```python
query = sql.select("*").from_("users").where_eq("active", True)
stmt = query.to_statement()

rows = await db_session.select(stmt, schema_type=User)
```

### `.build(dialect=...)`

Get a `BuiltQuery` containing rendered named-placeholder SQL and the builder's parameter mapping:

```python
query = sql.select("*").from_("users").where_eq("active", True)

built = query.build(dialect="postgres")
built.sql
built.parameters
```

`build()` renders the builder for inspection. Adapter parameter-style conversion happens when the `SQL` statement is compiled by a driver. Execute `query` directly or call `query.to_statement()`; do not execute interpolated output from `to_sql(show_parameters=True)`.
