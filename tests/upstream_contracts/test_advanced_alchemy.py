import inspect
from importlib.metadata import version
from typing import Any

from advanced_alchemy import (
    alembic,
    base,
    cache,
    config,
    exceptions,
    filters,
    mixins,
    operations,
    repository,
    routing,
    service,
    types,
)
from advanced_alchemy.alembic import commands as alembic_commands
from advanced_alchemy.config import routing as routing_config
from advanced_alchemy.extensions import fastapi, flask, litestar, sanic, starlette
from advanced_alchemy.extensions.litestar import exception_handler as litestar_exc_handler
from advanced_alchemy.extensions.litestar.cli import database_group
from advanced_alchemy.repository import memory as repo_memory
from advanced_alchemy.types import encrypted_string
from advanced_alchemy.types.password_hash import base as password_hash_base
from advanced_alchemy.utils import dependencies as dep_utils
from advanced_alchemy.utils import serialization as ser_utils
from litestar import Litestar


def test_advanced_alchemy_111_public_api_contract() -> None:
    """Verify the documented Advanced Alchemy 1.12 public entrypoints."""
    assert version("advanced-alchemy") == "1.12.0"
    assert {
        "AdvancedDeclarativeBase",
        "BasicAttributes",
        "CommonTableAttributes",
        "DefaultBase",
        "ModelProtocol",
        "SQLQuery",
        "UUIDBase",
        "UUIDAuditBase",
        "UUIDv6Base",
        "UUIDv6AuditBase",
        "UUIDv7Base",
        "UUIDv7AuditBase",
        "BigIntBase",
        "BigIntAuditBase",
        "IdentityBase",
        "IdentityAuditBase",
        "NanoIDBase",
        "NanoIDAuditBase",
        "convention",
        "create_registry",
        "merge_table_arguments",
        "metadata_registry",
        "model_to_dict",
        "orm_registry",
    } <= set(base.__all__)
    assert {
        "AuditColumns",
        "SlugKey",
        "UniqueMixin",
        "SentinelMixin",
        "UUIDPrimaryKey",
        "UUIDv6PrimaryKey",
        "UUIDv7PrimaryKey",
        "BigIntPrimaryKey",
        "IdentityPrimaryKey",
        "NanoIDPrimaryKey",
    } <= set(mixins.__all__)
    assert {
        "DateTimeUTC",
        "GUID",
        "BigIntIdentity",
        "JsonB",
        "ORA_JSONB",
        "EncryptedString",
        "EncryptedText",
        "EncryptionBackend",
        "FernetBackend",
        "PasswordHash",
        "HashedPassword",
        "Bool",
        "Vector",
        "TOTPSecret",
        "TOTPProvider",
        "generate_totp_secret",
        "OneTimeCode",
        "HashedOneTimeCode",
        "generate_one_time_code",
        "FileObject",
        "FileObjectList",
        "StoredObject",
        "StorageBackend",
        "StorageBackendT",
        "StorageRegistry",
        "storages",
    } <= set(types.__all__)
    assert hasattr(encrypted_string, "PGCryptoBackend")
    assert hasattr(password_hash_base, "HashingBackend")
    assert {
        "SQLAlchemyAsyncRepository",
        "SQLAlchemyAsyncSlugRepository",
        "SQLAlchemyAsyncQueryRepository",
        "SQLAlchemySyncRepository",
        "SQLAlchemySyncSlugRepository",
        "SQLAlchemySyncQueryRepository",
        "LoadSpec",
        "OrderingPair",
    } <= set(repository.__all__)
    assert {
        "SQLAlchemyAsyncMockRepository",
        "SQLAlchemyAsyncMockSlugRepository",
        "SQLAlchemySyncMockRepository",
        "SQLAlchemySyncMockSlugRepository",
    } <= set(repo_memory.__all__)
    assert {
        "SQLAlchemyAsyncRepositoryService",
        "SQLAlchemyAsyncRepositoryReadService",
        "SQLAlchemyAsyncQueryService",
        "SQLAlchemySyncRepositoryService",
        "SQLAlchemySyncRepositoryReadService",
        "SQLAlchemySyncQueryService",
        "OffsetPagination",
        "SchemaDumpConfig",
        "schema_dump",
        "is_dict",
        "is_dict_with_field",
        "is_dict_without_field",
        "is_dto_data",
        "is_msgspec_struct",
        "is_pydantic_model",
        "is_attrs_instance",
        "find_filter",
    } <= set(service.__all__)
    assert {
        "FilterTypes",
        "StatementFilter",
        "PaginationFilter",
        "InAnyFilter",
        "LimitOffset",
        "OrderBy",
        "SearchFilter",
        "CollectionFilter",
        "NotInCollectionFilter",
        "NotInSearchFilter",
        "BeforeAfter",
        "OnBeforeAfter",
        "NullFilter",
        "NotNullFilter",
        "ComparisonFilter",
        "ChoicesFilter",
        "BooleanFilter",
        "ExistsFilter",
        "NotExistsFilter",
        "FilterGroup",
        "MultiFilter",
        "FilterMap",
        "LogicalOperatorMap",
        "LIKE_ESCAPE_CHAR",
        "escape_like_value",
    } <= set(filters.__all__)
    assert {
        "CacheConfig",
        "CacheManager",
        "default_deserializer",
        "default_serializer",
        "setup_cache_listeners",
    } <= set(cache.__all__)
    assert {
        "SQLAlchemyAsyncConfig",
        "SQLAlchemySyncConfig",
        "AlembicAsyncConfig",
        "AlembicSyncConfig",
        "AsyncSessionConfig",
        "SyncSessionConfig",
        "EngineConfig",
    } <= set(config.__all__)
    assert {
        "AdvancedAlchemyError",
        "RepositoryError",
        "NotFoundError",
        "DuplicateKeyError",
        "IntegrityError",
        "ForeignKeyError",
        "MultipleResultsFoundError",
        "ImproperConfigurationError",
        "MissingDependencyError",
        "SerializationError",
        "ErrorMessages",
        "wrap_sqlalchemy_exception",
    } <= set(exceptions.__all__)
    assert hasattr(exceptions, "InvalidRequestError")
    assert hasattr(alembic_commands, "AlembicCommands")
    assert hasattr(alembic_commands, "AlembicCommandConfig")
    assert hasattr(alembic, "commands")
    assert {
        "ChoiceField",
        "DependencyCache",
        "FieldNameType",
        "FilterConfig",
        "resolve_filter_aliases",
    } <= set(dep_utils.__all__)
    assert {
        "SchemaDumpConfig",
        "decode_json",
        "encode_json",
    } <= set(ser_utils.__all__)
    assert {
        "MergeStatement",
        "OnConflictUpsert",
        "UpsertKind",
        "UpsertStrategy",
        "resolve_column_default",
        "resolve_upsert_strategy",
        "validate_identifier",
    } <= set(operations.__all__)
    assert {
        "RoutingAsyncSessionMaker",
        "RoutingSyncSessionMaker",
        "RoundRobinSelector",
        "RandomSelector",
        "dispose_session_maker_async",
        "dispose_session_maker_sync",
    } <= set(routing.__all__)
    assert routing_config.ReplicaConfig is routing_config.EngineConfig
    assert {"ReplicaConfig", "RoutingConfig", "RoutingStrategy"} <= set(routing_config.__all__)
    assert {
        "SQLAlchemyPlugin",
        "SQLAlchemyInitPlugin",
        "SQLAlchemySerializationPlugin",
        "SQLAlchemyAsyncConfig",
        "SQLAlchemySyncConfig",
        "SQLAlchemyDTO",
        "SQLAlchemyDTOConfig",
        "providers",
    } <= set(litestar.__all__)
    assert {
        "create_filter_dependencies",
        "create_service_dependencies",
        "create_service_provider",
    } <= set(litestar.providers.__all__)
    assert {
        "AdvancedAlchemy",
        "assign_cli_group",
        "providers",
    } <= set(fastapi.__all__)
    assert {
        "provide_filters",
        "provide_service",
    } <= set(fastapi.providers.__all__)
    assert {"AdvancedAlchemy", "FlaskServiceMixin"} <= set(flask.__all__)
    assert "AdvancedAlchemy" in sanic.__all__
    assert "AdvancedAlchemy" in starlette.__all__
    assert {"make-migrations", "show-current-revision"} <= database_group.commands.keys()
    assert {"revision", "current", "create-database"}.isdisjoint(database_group.commands)


def test_advanced_alchemy_filter_and_service_behavioral_contracts() -> None:
    """Verify filter defaults, operators, FilterConfig keys, and service signatures."""
    search_filter = filters.SearchFilter(field_name="name", value="alice")
    assert search_filter.ignore_case is False
    assert search_filter.escape_wildcards is False
    assert filters.LIKE_ESCAPE_CHAR == "/"
    assert filters.escape_like_value("100%_done/ok") == "100/%/_done//ok"
    assert set(filters.SearchFilter.__dataclass_fields__) == {
        "field_name",
        "value",
        "ignore_case",
        "escape_wildcards",
    }
    order_by = filters.OrderBy(field_name="name")
    assert order_by.nulls is None
    assert set(filters.OrderBy.__dataclass_fields__) == {"field_name", "sort_order", "nulls"}

    assert {
        "eq",
        "ne",
        "gt",
        "ge",
        "lt",
        "le",
        "in",
        "notin",
        "between",
        "like",
        "ilike",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "dateeq",
    } == filters.VALID_OPERATORS

    assert {
        "id_filter",
        "id_field",
        "sort_field",
        "sort_order",
        "sort_nulls",
        "pagination_type",
        "pagination_size",
        "search",
        "search_ignore_case",
        "search_escape_wildcards",
        "created_at",
        "updated_at",
        "not_in_fields",
        "in_fields",
        "boolean_fields",
        "choice_fields",
        "alias_generator",
    } == set(dep_utils.FilterConfig.__annotations__)

    service_get_params = inspect.signature(service.SQLAlchemyAsyncRepositoryReadService[Any, Any].get).parameters
    assert "with_for_update" not in service_get_params

    for method_name in ("get_one", "get_one_or_none"):
        params = inspect.signature(getattr(service.SQLAlchemyAsyncRepositoryReadService, method_name)).parameters
        assert "with_for_update" in params

    for method_name in ("update", "upsert", "get_or_upsert", "get_and_update"):
        params = inspect.signature(getattr(service.SQLAlchemyAsyncRepositoryService, method_name)).parameters
        assert "with_for_update" in params

    for target_cls in (
        repository.SQLAlchemyAsyncRepository[Any],
        repository.SQLAlchemySyncRepository[Any],
        service.SQLAlchemyAsyncRepositoryService[Any, Any],
        service.SQLAlchemySyncRepositoryService[Any, Any],
    ):
        upsert_many_params = inspect.signature(target_cls.upsert_many).parameters
        assert "no_merge" in upsert_many_params
        assert "chunk_size" in upsert_many_params
        assert upsert_many_params["no_merge"].default is False
        assert upsert_many_params["chunk_size"].default is None

    for bulk_method in ("create_upsert_many", "create_merge_many", "create_insert_or_update_many"):
        assert hasattr(operations.OnConflictUpsert, bulk_method)

    repo_get_params = inspect.signature(repository.SQLAlchemyAsyncRepository[Any].get).parameters
    assert "with_for_update" in repo_get_params

    sync_create_params = inspect.signature(service.SQLAlchemySyncRepositoryService[Any, Any].create).parameters
    assert "data" in sync_create_params
    assert all(p.kind != inspect.Parameter.VAR_KEYWORD for p in sync_create_params.values())

    sync_update_params = inspect.signature(service.SQLAlchemySyncRepositoryService[Any, Any].update).parameters
    assert "data" in sync_update_params
    assert "item_id" in sync_update_params
    assert all(p.kind != inspect.Parameter.VAR_KEYWORD for p in sync_update_params.values())


def test_advanced_alchemy_litestar_exception_handler_contract() -> None:
    """Verify SQLAlchemyInitPlugin exception handler registration and integer status-code key behavior."""
    assert hasattr(litestar_exc_handler, "exception_to_http_response")
    assert hasattr(litestar_exc_handler, "ConflictError")

    default_cfg = litestar.SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    default_app: Any = Litestar(route_handlers=[], plugins=[litestar.SQLAlchemyPlugin(config=default_cfg)])
    assert (
        default_app.exception_handlers.get(exceptions.RepositoryError)
        is litestar_exc_handler.exception_to_http_response
    )

    def custom_500_handler(request: Any, exc: Exception) -> Any:
        return None

    int_key_cfg = litestar.SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    int_key_app: Any = Litestar(
        route_handlers=[],
        plugins=[litestar.SQLAlchemyPlugin(config=int_key_cfg)],
        exception_handlers={500: custom_500_handler},
    )
    assert exceptions.RepositoryError not in int_key_app.exception_handlers

    explicit_cfg = litestar.SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    explicit_app: Any = Litestar(
        route_handlers=[],
        plugins=[litestar.SQLAlchemyPlugin(config=explicit_cfg)],
        exception_handlers={
            500: custom_500_handler,
            exceptions.RepositoryError: litestar_exc_handler.exception_to_http_response,
        },
    )
    assert (
        explicit_app.exception_handlers.get(exceptions.RepositoryError)
        is litestar_exc_handler.exception_to_http_response
    )
