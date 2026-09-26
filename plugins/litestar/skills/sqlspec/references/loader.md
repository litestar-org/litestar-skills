# SQLSpec SQL File Loading

## Overview

`SQLFileLoader` loads SQL statements from external files, supporting metadata directives, declared parameter annotations, multiple search paths, and content caching with checksums.

---

## Basic Usage

```python
from sqlspec.loader import SQLFileLoader

loader = SQLFileLoader()
loader.load_sql("./sql", "./sql/queries")

stmt = loader.get_sql("get-user-by-id")
result = await db_session.select_one(stmt, user_id, schema_type=User)
```

---

## SQL File Format

SQL files use metadata directives as comments to define name, dialect, and other properties:

```sql
-- name: get-user-by-id
-- dialect: postgres
-- description: Fetch a single user by primary key
SELECT id, name, email, created_at
FROM users
WHERE id = $1
```

### Supported Directives & Markers

| Directive / Marker | Required | Description |
| --- | --- | --- |
| `-- name:` | Yes (or `-- fragment:`) | Unique identifier for an executable query |
| `-- fragment:` | No | Reusable SQL fragment for static `/* include: */` or dynamic `/* slot: */` splicing |
| `-- dialect:` | No | Source dialect for sqlglot parsing |
| `-- param:` | No | Declared parameter metadata and validation |
| `-- slot:` | No | Declared slot default (`-- slot: <name> = <default_sql>`) |
| `-- description:` | No | Human-readable description |
| `-- result:` | No | Expected result type hint (`one`, `many`, `value`, `affected`) |
| `/* include: <name> */` | No | Static load-time splice of a named fragment |
| `/* slot: <name> */` | No | Dynamic runtime splice resolved via `loader.get_sql(name, <slot>=...)` |

### Multiple Queries Per File

A single `.sql` file can contain multiple named queries and fragments separated by directives:

```sql
-- name: list-users
SELECT id, name, email FROM users ORDER BY name

-- name: count-users
SELECT COUNT(*) FROM users

-- name: get-user-by-email
-- dialect: postgres
SELECT * FROM users WHERE email = $1
```

---

## Fragments, Includes, and Slots

`SQLFileLoader` supports two complementary composition mechanisms so SQL files can share column lists, CTEs, and optional filter predicates without string concatenation:

### 1. Static Includes (`-- fragment:` + `/* include: <name> */`)

Fragments are defined with `-- fragment: <name>` (or `loader.add_fragment(name, sql)`) and spliced at load time wherever `/* include: <name> */` appears. Cyclic or missing includes raise `SQLFileParseError` / `SQLFragmentNotFoundError`.

```sql
-- fragment: user-columns
u.id, u.name, u.email, u.created_at

-- name: list-active-users
SELECT /* include: user-columns */
FROM users AS u
WHERE u.active = TRUE
ORDER BY u.created_at DESC
```

Inspect registered fragments with `loader.has_fragment(name)`, `loader.list_fragments()`, and `loader.get_fragment_text(name)`.

### 2. Dynamic Slots (`/* slot: <name> */` + `-- slot: <name> = <default_sql>`)

Slots mark fill points in a named query where a caller may splice a `str` (verbatim SQL), a `sqlglot` / `sql.column(...)` expression (rendered in the statement's dialect), or a `SQL` object (splicing its text and binding its named parameters) at `get_sql(name, **slots)` time:

- Declare an optional default with `-- slot: <name> = <default_sql>`.
- An undeclared `/* slot: <name> */` marker (or `-- slot: <name>` without `= ...`) has `default=None` and **must** be supplied by the caller at `get_sql()` time.
- Missing required slots, unknown slot keyword arguments, positional parameters inside a `SQL` slot value, or colliding parameter names raise `SQLSlotError`.
- Inspect declared slots with `loader.get_query_slots(name)` (returns `tuple[SlotDeclaration, ...]`).

```sql
-- name: search-users
-- dialect: postgres
-- slot: extra_where = 1=1
-- slot: order_clause = u.name ASC
SELECT u.id, u.name, u.email
FROM users AS u
WHERE u.active = TRUE
  AND /* slot: extra_where */
ORDER BY /* slot: order_clause */
```

```python
from sqlspec import SQL, sql
from sqlspec.loader import SQLFileLoader, SlotDeclaration

loader = SQLFileLoader()
loader.load_sql("./sql")

slots: tuple[SlotDeclaration, ...] = loader.get_query_slots("search-users")
default_stmt = loader.get_sql("search-users")
role_stmt = loader.get_sql(
    "search-users",
    extra_where=SQL("u.role = :role", {"role": "admin"}),
    order_clause="u.created_at DESC",
)
```

---

## Declared Parameters

Use `-- param:` lines in the leading comment block for named SQL that crosses service boundaries:

```sql
-- name: get-team-by-name
-- param: name str  The team name to look up
SELECT id, name FROM teams WHERE name = :name

-- name: list-teams
-- param: name str?  Optional team name filter
SELECT id, name FROM teams
WHERE (:name IS NULL OR name = :name)
ORDER BY id
```

Grammar: `-- param: <name> <type> [description]`. Append `?` to the type or end the description with `(optional)` to mark a named parameter optional.

Behavior:

- No `-- param:` lines means no declaration validation and no behavior change.
- Required declarations must be supplied at execution time.
- Missing optional named declarations bind `None`; the SQL must express the intended nullable condition.
- Declared names are cross-checked against actual placeholders at load time.
- Type strings from the allowlist are checked at execution time; unresolved type strings are documentation-only.
- Extra parameters are allowed because filters may add `limit`, `offset`, and related parameters.
- Malformed `-- param:` lines warn and are skipped by default. Pass `strict_parameter_annotations=True` to `SQLFileLoader` to make malformed annotations fail.

Introspect declarations with `spec.get_query_parameters(name)` or `spec.get_sql(name).declared_parameters`.

---

## Search Paths

Pass any number of file or directory paths to `load_sql()`. Directories are walked recursively for `*.sql` files; later loads override earlier ones for the same query name:

```python
loader = SQLFileLoader()
loader.load_sql(
    "./sql/shared",
    "./sql/queries",
    "./sql/overrides",
)
```

---

## File Caching with Checksums

Loaded SQL files are cached in the `file` namespace. Each entry stores an MD5 content checksum used only for change detection. On subsequent loads:

1. If the file has not been modified (checksum matches), the cached `SQL` object is returned.
2. If the file has changed, the cache entry is invalidated and the file is re-parsed.

```python
loader.clear_cache()
loader.clear_file_cache()
```

---

## Storage Backends

SQL files can be loaded from local paths or any URI supported by SQLSpec's storage registry. Pass a URI or a registered alias path directly to `load_sql()`:

### Local Filesystem (Default)

```python
loader = SQLFileLoader()
loader.load_sql("./sql")
```

### S3 / GCS / Azure (via obstore)

```python
from sqlspec.storage import storage_registry

storage_registry.register_alias(
    "queries",
    uri="s3://my-sql-queries/v2/",
)

loader = SQLFileLoader()
loader.load_sql("queries/list-users.sql")
```

The storage registry uses `sqlspec.storage.backends.obstore.ObStoreBackend` under the hood for `s3://`, `gs://`, and `az://` URIs. For pure-Python fsspec adapters use `sqlspec.storage.backends.fsspec.FSSpecBackend`. Local filesystem URIs (`file://`) and bare paths are handled by `sqlspec.storage.backends.local.LocalStore`.

---

## Integration with Driver Sessions

```python
from sqlspec.loader import SQLFileLoader

loader = SQLFileLoader()
loader.load_sql("./sql")

stmt = loader.get_sql("list-active-users")
users = await db_session.select(stmt, schema_type=User)

stmt_override = loader.get_sql("get-user-by-id")
user = await db_session.select_one(stmt_override, user_id, schema_type=User)
```
