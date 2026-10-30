# Database Adapter Documentation

Standard pattern for documenting multi-driver database libraries (`sqlspec`, `advanced-alchemy`, `pytest-databases`) without duplicating core concepts across 20 driver pages.

## Three-Tier Adapter Architecture

1. **Central Capability Matrix (`docs/databases/index.md`)**:
   - Opens the `Databases` tab with a single comparison table across all supported adapters (`Adapter`, `Driver Package`, `Sync / Async`, `Parameter Style`, `Native Pool`, `Arrow / Bulk Ingest`, `ADK / Litestar / Events Stores`).
   - Lists individual engine tabs/sections in the left sidebar (`PostgreSQL`, `CockroachDB`, `SQLite`, `DuckDB`, `MySQL / MariaDB`, `Oracle`, `SQL Server`, `IBM Db2`, `Google Cloud` (`Spanner`, `BigQuery`), and `Arrow & ADBC`).
2. **Concise 1-Page Per-Driver Setup Guide (`docs/databases/<engine>/<adapter>.md`)**:
   - Strictly `<= 10` viewports (`~80–140` Markdown lines).
   - Covers **only** driver-specific concerns; never re-teach `SQL(...)`, `select()`, or general framework middleware on adapter pages.
3. **Own-Symbols-Only Adapter API Reference (`docs/reference/adapters/<adapter>.md`)**:
   - Documents the adapter's own `*Config`, `*ConnectionParams`, `*PoolParams`, `*DriverFeatures`, `*Driver` (`inherited_members: false`, `show_bases: true`), `*ExceptionHandler`, and extension stores.
   - Links to [`SyncDriverAdapterBase`](../driver/sync.md) or [`AsyncDriverAdapterBase`](../driver/async.md) for the 40+ inherited execution methods (`select`, `select_one`, `select_one_or_none`, `execute`, `execute_many`, `select_to_arrow`).

## Canonical 1-Page Database Guide Template

Every `docs/databases/<engine>/<adapter>.md` page follows these 5 sections:

1. **Installation & At-a-Glance Table**:
   - `uv add "sqlspec[<extra>]"` command (use real PyPI package extras; for `adbc-drivers/mssql`, use `dbc install mssql` via the `dbc` CLI, never `uv add`).
   - Compact metadata table (`Driver`, `Config Class`, `Driver Class`, `Execution Mode`, `Param Style`, `API Reference` link).
2. **Quickstart Snippet**:
   - Standalone runnable example embedded via `--8<-- "docs/examples/databases/<adapter>/connect.py"`.
3. **Connection & Pool Configuration**:
   - Concise table or example of top `connection_config` / `pool_config` keys linking to the full `TypedDict` table on `Reference -> Database Adapters -> <Adapter>`.
4. **Type Mapping & Dialect Quirks**:
   - Engine-specific behaviors (`JSONB` codecs, `VECTOR` embeddings, `pooler_mode="transaction"` prepared-statement bypass, `MERGE` / `RETURNING` support, wallet/TLS setup).
5. **See Also**:
   - Links to the Central Capability Matrix, Core Configuration guide, and the adapter's API Reference page.
