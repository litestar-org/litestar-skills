import inspect
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from google.adk.sessions.base_session_service import GetSessionConfig
from sqlspec import (
    SQL,
    LoggingConfig,
    ObservabilityConfig,
    RedactionConfig,
    SQLFileLoader,
    SQLSpec,
    StackResult,
    StatementStack,
    TelemetryConfig,
    create_statement_observer,
    default_statement_observer,
    nanoid,
    sql,
    uuid4,
    uuid6,
    uuid7,
)
from sqlspec.adapters.aiosqlite import (
    AiosqliteConfig,
    AiosqliteDriver,
    AiosqliteDriverFeatures,
)
from sqlspec.adapters.db2 import (
    Db2AsyncConfig,
    Db2AsyncDataDictionary,
    Db2AsyncDriver,
    Db2AsyncPoolParams,
    Db2ConnectionParams,
    Db2DriverFeatures,
    Db2PoolParams,
    Db2SyncConfig,
    Db2SyncDataDictionary,
    Db2SyncDriver,
    Db2VersionInfo,
    build_connection_config,
)
from sqlspec.adapters.db2.adk import (
    Db2AsyncADKMemoryStore,
    Db2AsyncADKStore,
    Db2SyncADKMemoryStore,
    Db2SyncADKStore,
)
from sqlspec.adapters.db2.events import (
    Db2AsyncEventQueueStore,
    Db2EventsConfig,
    Db2SyncEventQueueStore,
)
from sqlspec.adapters.db2.litestar import (
    Db2AsyncStore,
    Db2LitestarConfig,
    Db2SyncStore,
)
from sqlspec.adapters.sqlite import SqliteConfig, SqliteDriver, SqliteDriverFeatures
from sqlspec.builder import Merge
from sqlspec.cli import add_migration_commands, get_sqlspec_group
from sqlspec.core import CursorPagination, OffsetPagination, Pagination, StatementConfig
from sqlspec.core.config_runtime import (
    build_postgres_extension_probe_names,
    is_postgres_extension_active,
    resolve_postgres_extension_state,
)
from sqlspec.core.filters import (
    AnyCollectionFilter,
    BooleanFilter,
    ChoicesFilter,
    CursorFilter,
    CursorKey,
    LimitOffsetFilter,
    NotAnyCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfterFilter,
    OrderByFilter,
    SearchFilter,
    normalize_cursor_keys,
)
from sqlspec.core.result import SQLResult
from sqlspec.dialects import DB2
from sqlspec.dialects.db2 import DB2Tokenizer
from sqlspec.dialects.postgres import ParadeDB, PGTextSearch, PGVector
from sqlspec.extensions.adk import (
    PruneReport,
    SQLSpecArtifactService,
    SQLSpecMemoryService,
    SQLSpecSessionService,
    SQLSpecSyncMemoryService,
    prune_artifacts,
    prune_events,
    prune_memory,
    prune_sessions,
    prune_user_state,
)
from sqlspec.extensions.events import (
    claim_verified,
    lock_clause,
    row_limit_clause,
    select_limit_prefix,
)
from sqlspec.extensions.litestar import SQLSpecPlugin
from sqlspec.extensions.litestar.channels import SQLSpecChannelsBackend
from sqlspec.extensions.litestar.providers import (
    ChoiceField,
    FieldNameType,
    FilterConfig,
    create_filter_dependencies,
)
from sqlspec.loader import SlotDeclaration
from sqlspec.migrations.tracker import AsyncMigrationTracker, SyncMigrationTracker
from sqlspec.service import SQLSpecAsyncService, SQLSpecSyncService
from sqlspec.storage import (
    AsyncStoragePipeline,
    ResolvedStorageTarget,
    StorageBridgeJob,
    StorageCapabilities,
    StorageDestination,
    StorageFormat,
    StorageRegistry,
    StorageTelemetry,
    SyncStoragePipeline,
    resolve_storage_path,
    storage_registry,
)
from sqlspec.utils.config_tools import (
    normalize_connection_config,
    parse_mysql_dsn,
    parse_odbc_connection_string,
)
from sqlspec.utils.env import get_env, get_env_with_aliases, is_env_set
from sqlspec.utils.fixtures import (
    export_table_fixtures_async,
    export_table_fixtures_sync,
    load_table_fixtures_async,
    load_table_fixtures_sync,
)


@dataclass
class UserRow:
    id: int
    name: str


def test_sqlspec_065_contract() -> None:
    """Validate sqlspec 0.65.0 core contracts and exported API surface."""
    assert version("sqlspec") == "0.65.0"

    assert "sqlspec" in inspect.signature(SQLSpecPlugin).parameters
    spec = SQLSpec()
    plugin = SQLSpecPlugin(spec)
    assert plugin is not None

    assert callable(sql.select)
    assert callable(sql.insert)
    assert callable(sql.update)
    assert callable(sql.delete)
    assert callable(sql.merge)
    assert callable(sql.upsert)
    assert callable(sql.explain)
    assert callable(sql.create_table)
    assert callable(sql.alter_table)
    assert callable(sql.drop_table)
    assert callable(sql.copy)
    assert callable(sql.copy_from)
    assert callable(sql.copy_to)
    assert callable(sql.case)
    assert callable(sql.column)
    assert callable(sql.to_literal)

    assert hasattr(sql, "row_number_")
    assert hasattr(sql, "rank_")
    assert hasattr(sql, "dense_rank_")
    assert hasattr(sql, "count_over_")
    assert hasattr(sql, "sum_over_")
    assert hasattr(sql, "avg_over_")
    assert hasattr(sql, "min_over_")
    assert hasattr(sql, "max_over_")
    assert hasattr(sql, "lag_")
    assert hasattr(sql, "lead_")
    assert hasattr(sql, "inner_join_")
    assert hasattr(sql, "left_join_")
    assert hasattr(sql, "right_join_")
    assert hasattr(sql, "full_join_")
    assert hasattr(sql, "cross_join_")
    assert hasattr(sql, "lateral_join_")
    assert hasattr(sql, "left_lateral_join_")
    assert hasattr(sql, "cross_lateral_join_")

    assert callable(uuid4)
    assert callable(uuid6)
    assert callable(uuid7)
    assert callable(nanoid)

    loader = SQLFileLoader()
    loader.add_named_sql("test-query", "SELECT 1")
    assert loader.has_query("test-query")
    assert loader.get_sql("test-query").sql.strip() == "SELECT 1"

    commands = add_migration_commands(get_sqlspec_group()).commands
    assert "create-migration" in commands
    assert "upgrade" in commands
    assert "downgrade" in commands
    assert "show-current-revision" in commands
    assert "stamp" in commands
    assert "init" in commands
    assert "fix" in commands
    assert "squash" in commands
    assert "show-config" in commands
    assert "adk" in commands
    assert "database" not in commands

    obs = ObservabilityConfig(
        logging=LoggingConfig(include_sql_hash=True),
        telemetry=TelemetryConfig(enable_spans=False),
        redaction=RedactionConfig(mask_parameters=True),
    )
    assert obs.logging is not None
    assert obs.logging.include_sql_hash is True
    assert callable(create_statement_observer)
    assert callable(default_statement_observer)

    assert issubclass(SQLSpecSessionService, object)
    assert issubclass(SQLSpecMemoryService, object)
    assert issubclass(SQLSpecSyncMemoryService, object)
    assert issubclass(SQLSpecArtifactService, object)
    assert callable(prune_sessions)
    assert callable(prune_memory)
    assert callable(prune_events)
    assert callable(prune_artifacts)
    assert callable(prune_user_state)

    assert issubclass(SQLSpecAsyncService, object)
    assert issubclass(SQLSpecSyncService, object)
    assert issubclass(OffsetPagination, object)
    assert issubclass(CursorPagination, object)
    assert Pagination is not None
    assert issubclass(LimitOffsetFilter, object)
    assert issubclass(CursorFilter, object)
    assert issubclass(CursorKey, object)
    assert issubclass(OrderByFilter, object)
    assert issubclass(SearchFilter, object)
    assert issubclass(NotInSearchFilter, object)
    assert issubclass(OnBeforeAfterFilter, object)
    assert issubclass(AnyCollectionFilter, object)
    assert issubclass(NotAnyCollectionFilter, object)
    assert issubclass(BooleanFilter, object)
    assert issubclass(ChoicesFilter, object)
    assert callable(normalize_cursor_keys)

    assert isinstance(storage_registry, StorageRegistry)
    assert issubclass(AsyncStoragePipeline, object)
    assert issubclass(SyncStoragePipeline, object)
    assert issubclass(StorageCapabilities, object)
    assert issubclass(ResolvedStorageTarget, object)
    assert issubclass(StorageBridgeJob, object)
    assert issubclass(StorageTelemetry, object)
    assert StorageDestination is not None
    assert StorageFormat is not None
    assert callable(resolve_storage_path)


def test_sqlspec_065_loader_fragments_includes_and_slots_contract(tmp_path: Path) -> None:
    """Verify SQLFileLoader fragments, includes, and dynamic slots in 0.65.0."""
    loader = SQLFileLoader()
    loader.add_fragment("active_predicate", "is_active = TRUE")
    assert loader.has_fragment("active_predicate")
    assert "active_predicate" in loader.list_fragments()
    assert loader.get_fragment_text("active_predicate") == "is_active = TRUE"

    sql_content = """
-- fragment: tenant_scope
tenant_id = :tenant_id

-- name: list_users
-- slot: extra_where = 1=1
-- slot: order_clause = created_at DESC
SELECT id, email
FROM users
WHERE /* include: active_predicate */
  AND /* include: tenant_scope */
  AND /* slot: extra_where */
ORDER BY /* slot: order_clause */
"""
    sql_file = tmp_path / "queries.sql"
    sql_file.write_text(sql_content, encoding="utf-8")
    loader.load_sql(sql_file)
    slots = loader.get_query_slots("list_users")
    assert len(slots) == 2
    assert all(isinstance(slot, SlotDeclaration) for slot in slots)

    default_stmt = loader.get_sql("list_users")
    assert "is_active = TRUE" in default_stmt.sql
    assert "tenant_id = :tenant_id" in default_stmt.sql
    assert "1=1" in default_stmt.sql
    assert "created_at DESC" in default_stmt.sql

    overridden_stmt = loader.get_sql(
        "list_users",
        extra_where=SQL("role = :role", {"role": "admin"}),
        order_clause="email ASC",
    )
    assert "email ASC" in overridden_stmt.sql


def test_sqlspec_065_config_backed_service_and_cursor_pagination_contract() -> None:
    """Verify config-backed SQLSpecSyncService, savepoints, and cursor pagination."""

    class UserService(SQLSpecSyncService[SqliteDriver]):
        __slots__ = ("custom_tag",)

        def __init__(self, config: SqliteConfig, loader: SQLFileLoader) -> None:
            super().__init__(config=config, loader=loader)
            self.custom_tag = "users"

    config = SQLSpec().add_config(SqliteConfig(connection_config={"database": ":memory:"}))
    loader = SQLFileLoader()
    loader.add_named_sql("select_users", "SELECT id, name FROM users")
    service = UserService(config=config, loader=loader)
    assert service.custom_tag == "users"

    with service.begin_transaction() as tx:
        tx.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        tx.execute("INSERT INTO users (id, name) VALUES (1, 'Ada'), (2, 'Grace'), (3, 'Lin')")
        with service.begin_transaction() as nested_tx:
            nested_tx.execute("INSERT INTO users (id, name) VALUES (4, 'Temp')")
            assert nested_tx is tx

    page1 = service.paginate_cursor(
        "SELECT id, name FROM users",
        CursorFilter(keys=(CursorKey("id"),), limit=2),
        schema_type=UserRow,
    )
    assert isinstance(page1, CursorPagination)
    assert len(page1.items) == 2
    assert page1.has_next is True
    assert page1.has_previous is False
    assert page1.next_cursor is not None

    page2 = service.paginate(
        "SELECT id, name FROM users",
        CursorFilter(keys=(CursorKey("id"),), limit=2, cursor=page1.next_cursor),
        schema_type=UserRow,
    )
    assert isinstance(page2, CursorPagination)
    assert len(page2.items) == 2
    assert page2.has_next is False


def test_sqlspec_065_filter_dependencies_contract() -> None:
    """Verify Litestar filter dependencies support cursor pagination and extended filters."""
    offset_config: FilterConfig = {
        "id_filter": int,
        "created_at": True,
        "updated_at": True,
        "pagination_type": "limit_offset",
        "pagination_size": 25,
        "pagination_max_size": 100,
        "search": "name,email",
        "not_in_fields": [FieldNameType(name="status", type_hint=str)],
        "boolean_fields": {"is_active", "is_verified"},
        "choice_fields": [ChoiceField(name="tier", choices=("free", "pro", "enterprise"))],
        "sort_field": {"created_at", "id"},
        "sort_order": "desc",
        "sort_field_aliases": {"created": "created_at", "id": "id"},
    }
    offset_deps = create_filter_dependencies(offset_config)
    assert "limit_offset_filter" in offset_deps
    assert "filters" in offset_deps
    assert "is_active_boolean_filter" in offset_deps
    assert "tier_choices_filter" in offset_deps

    cursor_config: FilterConfig = {
        "pagination_type": "cursor",
        "pagination_size": 25,
        "pagination_max_size": 100,
        "cursor_keys": (CursorKey("created_at", sort_order="desc"), "id"),
        "search": "name,email",
    }
    cursor_deps = create_filter_dependencies(cursor_config)
    assert "cursor_filter" in cursor_deps
    assert "filters" in cursor_deps


def test_sqlspec_065_query_builder_and_dialect_contract() -> None:
    """Verify UPDATE FROM, DML CTE preservation, MySQL/Db2 upsert, DDL, and NULLS ordering."""
    cte_update = (
        sql.update("accounts")
        .with_cte("stale_ids", sql.select("id").from_("accounts").where_eq("active", False))
        .set(status="archived")
        .from_("stale_ids")
        .where("accounts.id = stale_ids.id")
    )
    rendered_update = cte_update.build(dialect="postgres").sql
    assert "WITH" in rendered_update
    assert "FROM" in rendered_update

    mysql_insert = (
        sql.insert("metrics", dialect="mysql")
        .columns("metric_key", "total")
        .values("requests", 1)
        .on_duplicate_key_update(total=2)
    )
    assert "ON DUPLICATE KEY UPDATE" in mysql_insert.build(dialect="mysql").sql
    assert isinstance(sql.upsert("metrics", dialect="mysql"), type(mysql_insert))

    ddl = (
        sql.create_table("audit_events", dialect="postgres")
        .if_not_exists()
        .column("id", "UUID", primary_key=True)
        .column("created_at", "TIMESTAMPTZ", not_null=True, default="NOW()")
    )
    assert "CREATE TABLE IF NOT EXISTS" in ddl.build().sql

    quoted_ddl = (
        sql.create_table('"app_schema"."AuditEvents"', dialect="postgres")
        .if_not_exists()
        .column('"EventId"', "UUID", primary_key=True)
    )
    assert '"app_schema"."AuditEvents"' in quoted_ddl.build(dialect="postgres").sql

    ordered = sql.select("id").from_("users").order_by(sql.column("last_login_at").desc(nulls="last"))
    assert "NULLS LAST" in ordered.build(dialect="postgres").sql

    order_filter = OrderByFilter(field_name="last_login_at", sort_order="desc", nulls="last")
    filtered = order_filter.append_to_statement(sql.select("id", dialect="postgres").from_("users").to_statement())
    assert order_filter.nulls == "last"
    assert "NULLS LAST" in filtered.compile()[0]


def test_sqlspec_065_db2_adapter_and_dialect_contract() -> None:
    """Verify IBM Db2 sync/async adapters, extension stores, and DB2 SQLGlot dialect."""
    assert issubclass(Db2SyncConfig, object)
    assert issubclass(Db2SyncDriver, object)
    assert issubclass(Db2AsyncConfig, object)
    assert issubclass(Db2AsyncDriver, object)
    assert issubclass(Db2SyncDataDictionary, object)
    assert issubclass(Db2AsyncDataDictionary, object)
    assert issubclass(Db2VersionInfo, object)
    assert issubclass(Db2SyncStore, object)
    assert issubclass(Db2AsyncStore, object)
    assert issubclass(Db2SyncEventQueueStore, object)
    assert issubclass(Db2AsyncEventQueueStore, object)
    assert issubclass(Db2SyncADKStore, object)
    assert issubclass(Db2AsyncADKStore, object)
    assert issubclass(Db2SyncADKMemoryStore, object)
    assert issubclass(Db2AsyncADKMemoryStore, object)
    assert issubclass(DB2, object)
    assert issubclass(DB2Tokenizer, object)
    assert Db2ConnectionParams is not None
    assert Db2PoolParams is not None
    assert Db2AsyncPoolParams is not None
    assert Db2DriverFeatures is not None
    assert Db2LitestarConfig is not None
    assert Db2EventsConfig is not None
    assert callable(build_connection_config)

    sync_cfg = Db2SyncConfig(
        connection_config={
            "database": "testdb",
            "hostname": "localhost",
            "port": 50000,
            "user": "db2inst1",
            "password": "secret",
        }
    )
    assert sync_cfg.driver_type is Db2SyncDriver
    assert sync_cfg.supports_transactional_ddl is True
    assert sync_cfg.supports_native_arrow_export is False
    assert sync_cfg.supports_native_arrow_import is False
    assert hasattr(Db2SyncDriver, "select_to_arrow")
    assert hasattr(Db2SyncDriver, "load_from_arrow")

    async_cfg = Db2AsyncConfig(connection_config={"dsn": "DATABASE=testdb;HOSTNAME=localhost;PORT=50000;"})
    assert async_cfg.driver_type is Db2AsyncDriver

    db2_upsert = sql.upsert("products", dialect="db2")
    assert isinstance(db2_upsert, Merge)
    db2_merge = (
        db2_upsert.using([{"id": 1, "name": "Widget"}], alias="src")
        .on("products.id = src.id")
        .when_matched_then_update(name="src.name")
        .when_not_matched_then_insert(id="src.id", name="src.name")
    )
    rendered_upsert = db2_merge.build(dialect="db2").sql
    assert "MERGE INTO" in rendered_upsert
    assert "SYSIBM.SYSDUMMY1" in rendered_upsert

    db2_lock_select = sql.select("id", dialect="db2").from_("jobs").limit(5).for_update(skip_locked=True)
    rendered_lock = db2_lock_select.build(dialect="db2").sql
    assert "FETCH FIRST 5 ROWS ONLY" in rendered_lock
    assert "WITH RS USE AND KEEP UPDATE LOCKS SKIP LOCKED DATA" in rendered_lock


def test_sqlspec_065_sqlite_and_migration_tracker_contract() -> None:
    """Verify SQLite/AioSQLite driver surface and quoted migration tracker identifiers."""
    assert not hasattr(SqliteDriver, "backup")
    assert not hasattr(SqliteDriver, "run_in_transaction")
    assert not hasattr(SqliteConfig, "backup")
    assert not hasattr(SqliteConfig, "run_in_transaction")
    assert not hasattr(AiosqliteDriver, "backup")
    assert not hasattr(AiosqliteDriver, "run_in_transaction")
    assert not hasattr(AiosqliteConfig, "backup")
    assert not hasattr(AiosqliteConfig, "run_in_transaction")

    assert "batch_size" in inspect.signature(SqliteDriver.load_from_arrow).parameters
    assert "batch_size" in inspect.signature(AiosqliteDriver.load_from_arrow).parameters
    assert {"enable_custom_adapters", "custom_window_functions", "default_transaction_mode"}.issubset(
        SqliteDriverFeatures.__annotations__
    )
    assert {"enable_custom_adapters", "custom_window_functions", "default_transaction_mode"}.issubset(
        AiosqliteDriverFeatures.__annotations__
    )

    sync_tracker = SyncMigrationTracker(version_table_name='"app_schema"."DdlMigrations"')
    assert sync_tracker.version_table_schema == "app_schema"
    assert sync_tracker.version_table_name == "DdlMigrations"
    assert sync_tracker.version_table == '"app_schema"."DdlMigrations"'

    async_tracker = AsyncMigrationTracker(version_table_name="app_schema.ddl_migrations")
    assert async_tracker.version_table_schema == "app_schema"
    assert async_tracker.version_table_name == "ddl_migrations"


def test_sqlspec_065_fixtures_roundtrip_and_upsert_contract(tmp_path: Path) -> None:
    """Verify 0.65.0 fixture loader options, bare-string conflict_keys, and JSON string preservation."""
    load_params = inspect.signature(load_table_fixtures_sync).parameters
    export_params = inspect.signature(export_table_fixtures_sync).parameters
    assert {
        "tables",
        "table_order",
        "conflict_keys",
        "batch_size",
        "resync_sequences",
        "ignore_unknown_columns",
        "exclude_update_columns",
    }.issubset(load_params)
    assert {"tables", "compress", "jsonl"}.issubset(export_params)
    assert "file_format" not in export_params

    dd_sql_dir = (
        Path(inspect.getfile(SqliteDriver)).resolve().parents[2] / "data_dictionary" / "dialects" / "sqlite" / "sql"
    )
    registry_any: Any = storage_registry
    instances: dict[Any, Any] = registry_any._instances
    for directory in (tmp_path.resolve(), dd_sql_dir):
        uri = directory.as_uri()
        instances[uri] = storage_registry.get(directory, backend="local")

    config = SQLSpec().add_config(SqliteConfig(connection_config={"database": ":memory:"}))
    with config.provide_session() as session:
        session.execute("CREATE TABLE roles (slug TEXT PRIMARY KEY, label TEXT, created_at TEXT)")
        session.execute(
            "INSERT INTO roles (slug, label, created_at) VALUES (?, ?, ?), (?, ?, ?)",
            ("admin", "true", "2026-01-01", "viewer", "[1]", "2026-01-01"),
        )

        exported = export_table_fixtures_sync(
            session,
            tmp_path,
            tables=["roles"],
            compress=False,
            jsonl=True,
        )
        assert "roles" in exported

        fixture_file = tmp_path / "roles.jsonl"
        fixture_file.write_text(
            '{"slug": "admin", "label": "true", "created_at": "2099-01-01", "retired_col": "ignored"}\n'
            '{"slug": "editor", "label": "[1]"}\n',
            encoding="utf-8",
        )

        counts = load_table_fixtures_sync(
            session,
            tmp_path,
            tables=["roles"],
            table_order=["nonexistent_table", "roles"],
            conflict_keys={"roles": "slug"},
            ignore_unknown_columns=True,
            exclude_update_columns=["created_at"],
        )
        assert counts == {"roles": 2}

        rows = session.select("SELECT slug, label, created_at FROM roles ORDER BY slug")
        assert rows == [
            {"slug": "admin", "label": "true", "created_at": "2026-01-01"},
            {"slug": "editor", "label": "[1]", "created_at": None},
            {"slug": "viewer", "label": "[1]", "created_at": "2026-01-01"},
        ]


def test_sqlspec_065_postgres_extensions_and_utilities_contract() -> None:
    """Verify Postgres extension probing, dialects, config normalization, events, and fixtures."""
    assert issubclass(PGVector, object)
    assert issubclass(ParadeDB, object)
    assert issubclass(PGTextSearch, object)

    features: dict[str, Any] = {
        "enable_pgvector": True,
        "enable_paradedb": False,
        "enable_pg_textsearch": True,
    }
    probes = build_postgres_extension_probe_names(
        {
            "enable_pgvector": True,
            "enable_paradedb": True,
            "enable_pg_textsearch": True,
        }
    )
    assert {"vector", "pg_search", "pg_textsearch"}.issubset(set(probes))

    promoted_config, pgvector_ok, paradedb_ok = resolve_postgres_extension_state(
        StatementConfig(dialect="postgres"),
        features,
        detected_extensions={"vector", "pg_textsearch"},
    )
    assert promoted_config.dialect == "pg_textsearch"
    assert pgvector_ok is True
    assert paradedb_ok is False
    assert is_postgres_extension_active(features, "pg_textsearch") is True

    normalized = normalize_connection_config(
        {"host": "localhost", "extra": {"port": 5432}},
    )
    assert normalized == {"host": "localhost", "port": 5432}
    assert callable(parse_mysql_dsn)
    assert callable(parse_odbc_connection_string)

    assert callable(claim_verified)
    assert callable(lock_clause)
    assert callable(row_limit_clause)
    assert callable(select_limit_prefix)
    assert issubclass(SQLSpecChannelsBackend, object)

    assert callable(get_env)
    assert callable(get_env_with_aliases)
    assert callable(is_env_set)
    assert callable(load_table_fixtures_sync)
    assert callable(load_table_fixtures_async)
    assert callable(export_table_fixtures_sync)
    assert callable(export_table_fixtures_async)
    assert hasattr(SqliteDriver, "select_to_storage")
    assert hasattr(SqliteDriver, "transaction")


def test_sqlspec_065_statement_stack_execution_contract() -> None:
    """Verify immutable stack construction and ordered SQLite execution."""
    config = SQLSpec().add_config(SqliteConfig(connection_config={"database": ":memory:"}))
    initial_stack = StatementStack()
    stack = (
        initial_stack.push_execute("CREATE TABLE users (name TEXT)")
        .push_execute_many("INSERT INTO users (name) VALUES (?)", [("Ada",), ("Lin",)])
        .push_execute("SELECT name FROM users ORDER BY name")
    )

    assert len(initial_stack) == 0
    assert len(stack.operations) == 3

    with config.provide_session() as session:
        results = session.execute_stack(stack)

    assert isinstance(results, tuple)
    assert len(results) == 3
    assert all(isinstance(result, StackResult) for result in results)
    query_result = results[-1].result
    assert isinstance(query_result, SQLResult)
    assert query_result.all() == [{"name": "Ada"}, {"name": "Lin"}]


def test_sqlspec_065_vector_expression_contract() -> None:
    """Verify vector distance is a column expression that can order a query."""
    distance = sql.column("embedding").vector_distance([0.1, 0.2, 0.3], metric="cosine")
    query = sql.select("id").from_("documents").where(distance < 0.3).order_by(distance.asc()).limit(10)

    assert "<=>" in query.build(dialect="postgres").sql


def test_sqlspec_065_adk_retention_contract() -> None:
    """Verify the public retention helpers and their distinct day parameters."""
    assert set(PruneReport.__annotations__) == {"deleted_count", "elapsed_ms", "table"}
    assert {"target", "idle_days", "app_name"}.issubset(inspect.signature(prune_sessions).parameters)
    assert {"target", "older_than_days", "app_name"}.issubset(inspect.signature(prune_events).parameters)
    assert {"target", "older_than_days", "app_name", "scope"}.issubset(inspect.signature(prune_memory).parameters)
    assert {"target", "older_than_days", "app_name"}.issubset(inspect.signature(prune_artifacts).parameters)
    assert {"target", "idle_days", "app_name"}.issubset(inspect.signature(prune_user_state).parameters)


def test_sqlspec_065_adk_bounded_session_contract() -> None:
    """Verify bounded event reads and ordered session-list parameters."""
    config = GetSessionConfig(num_recent_events=200, after_timestamp=1_725_000_000.0)
    get_session_params = inspect.signature(SQLSpecSessionService.get_session).parameters
    list_sessions_params = inspect.signature(SQLSpecSessionService.list_sessions).parameters

    assert config.num_recent_events == 200
    assert config.after_timestamp == 1_725_000_000.0
    assert {"app_name", "user_id", "session_id", "config"}.issubset(get_session_params)
    assert {"app_name", "user_id", "order_by", "descending", "limit", "offset"}.issubset(list_sessions_params)
