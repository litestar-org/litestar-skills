# SQLSpec Data Dictionary

The data dictionary is SQLSpec's runtime database-introspection interface. Use the selected driver's `data_dictionary` property. Do not infer support from an empty list.

## Metadata Contract

SQLSpec 0.56 distinguishes capability, result, identity, and fidelity:

- `MetadataCapabilityProfile` reports support by metadata domain.
- `MetadataCapability` distinguishes supported, gated, unsupported, unknown, and not-implemented domains.
- `MetadataResult` wraps domain lookups.
- `ObjectIdentity` identifies catalog, schema, name, object type, dialect, quoting, and source.
- `DDLResult` carries DDL plus status, fidelity, warnings, and dependency edges.
- `SystemMetadataRequest` and `SystemMetadataResult` isolate operational metadata behind explicit risk gates.

Inspect `result.capability` before reading `MetadataResult.items` or `SystemMetadataResult.rows`. Inspect `DDLResult.status` and `DDLResult.fidelity` before replaying DDL.

## Capability-First Usage

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://app:app@localhost/app"},
)


async def inspect_orders() -> None:
    async with config.provide_session() as db:
        profile = await db.data_dictionary.get_metadata_capabilities(db)
        capability = profile.get("tables")
        if capability.support != "supported":
            return

        result = await db.data_dictionary.get_table_details(
            db,
            "orders",
            schema="public",
        )
        if result.capability.support == "supported":
            for item in result.items:
                ...
```

Sync drivers expose the same contract without `await`.

## Convenience Lists vs Result Envelopes

These structural convenience methods return lists:

- `get_tables(driver, schema=None)`
- `get_columns(driver, table=None, schema=None)`
- `get_indexes(driver, table=None, schema=None)`
- `get_foreign_keys(driver, table=None, schema=None)`

Richer domain methods return `MetadataResult`, including `get_objects()`, `get_table_details()`, and `get_dependencies()`. An unsupported result is distinct from a supported result containing no items.

## DDL and Dependency Ordering

`get_ddl()` returns one `DDLResult`. `get_schema_ddl()` returns a `MetadataResult` whose items are `DDLResult` objects.

```python
from sqlspec.data_dictionary import sort_ddl_results


schema_result = await db.data_dictionary.get_schema_ddl(db, schema="public")
if schema_result.capability.support == "supported":
    ordered = sort_ddl_results(schema_result.items, order="create")
```

Fidelity values include native, generated, hybrid, lossy, partial, transport fallback, and unsupported. Review lossy, partial, or transport-fallback DDL before replay. `sort_ddl_results(..., order="drop")` reverses dependency direction and raises `DependencyCycleError` by default when a cycle prevents a complete order.

## System Metadata

System metadata is separate because it can expose SQL text, users, hosts, grants, topology, billing data, or license-gated diagnostics.

```python
from sqlspec.data_dictionary import SystemMetadataRequest


capabilities = await db.data_dictionary.get_system_metadata_capabilities(db)
table_stats = next(item for item in capabilities if item.domain == "table_statistics")
if table_stats.support == "supported":
    request = SystemMetadataRequest(
        "table_statistics",
        include_performance=True,
        schema="public",
        table="orders",
    )
    result = await db.data_dictionary.get_system_metadata(db, request)
```

Branch on the domain capability before execution, then branch on the returned result capability. Keep redaction enabled unless the workflow explicitly authorizes sensitive diagnostics.

## Adapter Boundaries

- PostgreSQL, MySQL/MariaDB, Oracle, SQL Server, SQLite, DuckDB, BigQuery, and Spanner use database-specific catalog/query packs.
- ADBC metadata can be a transport fallback. Treat transport-fallback or lossy output as inspection data, not lossless export.
- BigQuery operational metadata can be region-scoped or billed.
- Oracle diagnostics can require privileges or licensed packs.
- Spanner has separate GoogleSQL and PostgreSQL metadata shapes.
- Arrow ODBC does not expose a portable raw ODBC catalog bridge in Python.

Use the runtime capability profile as the final answer; do not hard-code a static support matrix into application logic.

## Version and Capability Caches

Adapter data dictionaries cache server-version and capability probes at the config/pool scope. Oracle 0.56 shares server-version, JSON-storage, and extension-table capability detection through that cache. Do not create a second application-global cache for these probes.

## Additive Schema Reconciliation

Schema reconciliation is a migration utility, not a metadata-result API:

```python
from sqlspec.migrations import SchemaTarget, ensure_schema_async


target = SchemaTarget.from_ddl(
    "widgets",
    "CREATE TABLE widgets (id INTEGER PRIMARY KEY, label VARCHAR(50))",
    dialect="sqlite",
)
result = await ensure_schema_async(
    db,
    [target],
    manage_schema=True,
    create_schema=True,
)
```

It creates missing tables and adds missing columns derived from canonical DDL. It does not rename or drop columns or change incompatible types. Extension stores expose `manage_schema`, `create_schema`, and `run_migrations` controls around this lifecycle.

## Query Builder Boundary

The query builder does not consult live metadata while constructing a statement. Query the data dictionary explicitly, make a capability decision, then build the statement.

## Cross References

- [adapters.md](adapters.md) — adapter selection.
- [migrations.md](migrations.md) — migration runner and schema ownership.
- [storage.md](storage.md) — extension schema lifecycle.
