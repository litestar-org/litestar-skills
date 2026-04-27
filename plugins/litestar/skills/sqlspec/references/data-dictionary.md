# SQLSpec Data Dictionary

`sqlspec.data_dictionary` is the introspection layer that exposes `information_schema`-style metadata — table lists, column definitions, indexes, foreign keys, database version, feature flags — uniformly across every supported dialect. It is what the migration tracker uses to decide whether `ddl_migrations` needs schema upgrades, and what adapter-specific code uses to pick an optimal column type for a logical category (e.g. "give me the best JSON type this Postgres version can handle").

## What It Is

Two layers live side-by-side:

1. **Static dialect configuration** — `DialectConfig` objects describing feature flags, minimum versions required for each feature, and logical-to-physical type mappings. Loaded from `sqlspec.data_dictionary.dialects.*`.
2. **Runtime introspection** — async and sync `DataDictionary` classes attached to each driver that run SQL against live system catalogs and return typed metadata.

Useful for: schema migrations that must adapt to existing columns, DDL generation, query planning, feature-gated code paths ("only emit `INSERT ... ON CONFLICT` when `supports_upsert` is true at the detected version"), and table introspection without executing migrations.

## Core API

Top-level exports in `sqlspec.data_dictionary.__init__`:

- `DataDictionaryLoader`, `get_data_dictionary_loader()` — singleton that lazy-loads the per-dialect SQL queries from `sqlspec/data_dictionary/sql/<dialect>/*.sql`.
- `get_dialect_config(dialect)`, `list_registered_dialects()`, `register_dialect(config)`, `normalize_dialect_name(dialect)` — the dialect registry.
- `DialectConfig`, `FeatureFlags`, `FeatureVersions` — the static-config types in `sqlspec/data_dictionary/_types.py`.

`DialectConfig` fields (see `sqlspec/data_dictionary/_types.py`):

```python
from sqlspec.data_dictionary import DialectConfig

config = DialectConfig(
    name="postgres",
    feature_versions={"supports_upsert": ...},
    feature_flags={"supports_uuid": True, "supports_arrays": True},
    type_mappings={"json": "JSONB", "uuid": "UUID"},
    version_pattern=...,
    default_schema="public",
)
```

`FeatureFlags` is a `TypedDict` with keys like `supports_arrays`, `supports_clustering`, `supports_cte`, `supports_json`, `supports_returning`, `supports_upsert`, `supports_uuid`, `supports_window_functions`. `FeatureVersions` maps a subset of those to `VersionInfo(major, minor, patch)` minimums.

Runtime metadata types live in `sqlspec.typing` and are `TypedDict`s:

- `TableMetadata` — `schema_name`, `table_name`, `table_type`, `table_catalog`.
- `ColumnMetadata` — `column_name`, `data_type`, `is_nullable`, `column_default`, `ordinal_position`, `max_length`, `numeric_precision`, `numeric_scale`, `is_primary`, `is_unique`, `extra`.
- `IndexMetadata` — `index_name`, `columns`, `is_unique`, `is_primary`.
- `ForeignKeyMetadata` — source/target columns and schemas.

## Dialect Coverage

Eight dialect modules register a `DialectConfig` when imported (`sqlspec/data_dictionary/dialects/__init__.py`):

| Dialect module | Exported config |
| --- | --- |
| `bigquery.py` | `BIGQUERY_CONFIG` |
| `cockroachdb.py` | `COCKROACHDB_CONFIG` |
| `duckdb.py` | `DUCKDB_CONFIG` |
| `mysql.py` | `MYSQL_CONFIG` |
| `oracle.py` | `ORACLE_CONFIG` |
| `postgres.py` | `POSTGRES_CONFIG` |
| `spanner.py` | `SPANNER_CONFIG` |
| `sqlite.py` | `SQLITE_CONFIG` |

Aliases defined in `_registry.DIALECT_ALIASES`: `postgresql` → `postgres`, `mariadb` → `mysql`, `cockroach` → `cockroachdb`.

Each dialect ships a parallel SQL directory under `sqlspec/data_dictionary/sql/<dialect>/` containing named queries for `columns`, `foreign_keys`, `indexes`, `tables`, and `version`. These are loaded on demand by `DataDictionaryLoader` via `SQLFileLoader` — the first time you ask for a dialect's query, its file tree is parsed and cached.

## Typical Usage

Drivers expose a `data_dictionary` property (declared as an abstract property on `AsyncDriverAdapterBase` / `SyncDriverAdapterBase`) that returns an `AsyncDataDictionaryBase` / `SyncDataDictionaryBase` bound to that dialect. That is the runtime entry point.

### Async

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"}
)


async def describe_table(table: str) -> None:
    async with config.provide_session() as driver:
        columns = await driver.data_dictionary.get_columns(driver, table=table)
        for col in columns:
            name = col.get("column_name")
            data_type = col.get("data_type")
            nullable = col.get("is_nullable")
            print(f"{name}: {data_type} (nullable={nullable})")
```

Available driver-side methods (async signatures shown; sync drivers expose the same without `await`):

- `await driver.data_dictionary.get_version(driver)` → `VersionInfo | None`
- `await driver.data_dictionary.get_feature_flag(driver, feature)` → `bool`
- `await driver.data_dictionary.get_optimal_type(driver, logical_type)` → `str`
- `await driver.data_dictionary.get_tables(driver, schema=None)` → `list[TableMetadata]`
- `await driver.data_dictionary.get_columns(driver, table=None, schema=None)` → `list[ColumnMetadata]`
- `await driver.data_dictionary.get_indexes(driver, table=None, schema=None)` → `list[IndexMetadata]`
- `await driver.data_dictionary.get_foreign_keys(driver, table=None, schema=None)` → `list[ForeignKeyMetadata]`

### Sync

```python
from sqlspec.adapters.sqlite import SqliteConfig


config = SqliteConfig(connection_config={"database": "app.db"})


def list_user_tables() -> list[str]:
    with config.provide_session() as driver:
        tables = driver.data_dictionary.get_tables(driver)
        return [t.get("table_name", "") for t in tables if t.get("table_name")]
```

## Integration With the Query Builder

The query builder (`sqlspec.builder`, entry point `from sqlspec import sql`) does **not** consult the data dictionary during statement construction — it relies on sqlglot for dialect conversion and parameter-style translation. The data dictionary is deliberately a runtime / introspection concern, separate from the parse-and-render pipeline. If you need schema-aware code generation, query the data dictionary explicitly and feed the result into your own logic.

The migration tracker is the canonical consumer: `sqlspec/migrations/tracker.py` calls `driver.data_dictionary.get_columns(driver, self.version_table)` to detect missing columns on the tracking table and auto-add them when the runner upgrades.

## Example: Introspect a Table's Columns

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"}
)


async def has_column(table: str, column: str) -> bool:
    async with config.provide_session() as driver:
        columns = await driver.data_dictionary.get_columns(driver, table=table)
        return any(col.get("column_name") == column for col in columns)


async def supports_jsonb() -> bool:
    async with config.provide_session() as driver:
        return await driver.data_dictionary.get_feature_flag(driver, "supports_jsonb")
```

## Static Config Access Without a Driver

When you need only the static config (e.g., in a module-level constant), use the registry directly:

```python
from sqlspec.data_dictionary import get_dialect_config


POSTGRES = get_dialect_config("postgres")
assert POSTGRES.default_schema == "public"
assert POSTGRES.get_feature_flag("supports_arrays") is True

JSON_TYPE = POSTGRES.get_optimal_type("json")  # "JSONB"
```

## Cross References

- [adapters.md](adapters.md) — each adapter's dialect mapping.
- [architecture.md](architecture.md) — where the data dictionary sits in the wider pipeline.
- [migrations.md](migrations.md) — the tracking table uses `get_columns` for schema upgrades.
