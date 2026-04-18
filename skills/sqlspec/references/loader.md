# SQLSpec SQL File Loading

## Overview

`SQLFileLoader` loads SQL statements from external files, supporting metadata directives, multiple search paths, and content caching with checksums.

---

## Basic Usage

```python
from sqlspec.loader import SQLFileLoader

loader = SQLFileLoader()
loader.load_sql("./sql", "./sql/queries")

# Load a named query
stmt = loader.get_sql("get-user-by-id")
result = await db_session.select_one(stmt, [user_id], schema_type=User)
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

### Supported Directives

| Directive | Required | Description |
| --- | --- | --- |
| `-- name:` | Yes | Unique identifier for the query |
| `-- dialect:` | No | Source dialect for sqlglot parsing |
| `-- description:` | No | Human-readable description |
| `-- result:` | No | Expected result type hint (`one`, `many`, `value`, `affected`) |

### Multiple Queries Per File

A single `.sql` file can contain multiple named queries separated by directives:

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

## Search Paths

Pass any number of file or directory paths to `load_sql()`. Directories are walked recursively for `*.sql` files; later loads override earlier ones for the same query name:

```python
loader = SQLFileLoader()
loader.load_sql(
    "./sql/shared",        # Shared across projects (loaded first)
    "./sql/queries",       # Standard queries
    "./sql/overrides",     # Project-specific overrides (win on conflict)
)
```

---

## File Caching with Checksums

Loaded SQL files are cached in the `file_cache` namespace. Each entry stores a content checksum (SHA-256). On subsequent loads:

1. If the file has not been modified (checksum matches), the cached `SQL` object is returned.
2. If the file has changed, the cache entry is invalidated and the file is re-parsed.

```python
# Force cache invalidation
loader.invalidate("get-user-by-id")

# Invalidate all cached files
loader.invalidate_all()
```

---

## Storage Backends

SQL files can be loaded from any URI supported by sqlspec's storage registry — local files, S3, GCS, Azure, in-memory. Pass URIs (or aliases registered with the storage registry) directly to `load_sql()`:

### Local Filesystem (Default)

```python
loader = SQLFileLoader()
loader.load_sql("./sql")
```

### S3 / GCS / Azure (via obstore)

```python
from sqlspec.loader import default_storage_registry

# Register an alias for S3-hosted queries
default_storage_registry.register_alias(
    "queries",
    uri="s3://my-sql-queries/v2/",
)

loader = SQLFileLoader()
loader.load_sql("queries://list-users.sql")
```

The storage registry uses `sqlspec.storage.backends.obstore.ObStoreBackend` under the hood for `s3://`, `gs://`, and `az://` URIs. For pure-Python fsspec adapters use `sqlspec.storage.backends.fsspec.FSSpecBackend`. Local filesystem URIs (`file://`) and bare paths are handled by `sqlspec.storage.backends.local.LocalStore`.

---

## Integration with Driver Sessions

```python
from sqlspec.loader import SQLFileLoader

loader = SQLFileLoader()
loader.load_sql("./sql")

# Load and execute
stmt = loader.get_sql("list-active-users")
users = await db_session.select_many(stmt, schema_type=User)

# Load with parameter override
stmt = loader.get_sql("get-user-by-id")
user = await db_session.select_one(stmt, [user_id], schema_type=User)
```
