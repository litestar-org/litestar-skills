from importlib.metadata import version

from advanced_alchemy import base, filters, mixins, operations, repository, routing, service, types
from advanced_alchemy.config import routing as routing_config
from advanced_alchemy.extensions import fastapi, flask, litestar, sanic, starlette
from advanced_alchemy.extensions.litestar.cli import database_group


def test_advanced_alchemy_111_public_api_contract() -> None:
    """Verify the documented Advanced Alchemy 1.11 public entrypoints."""
    assert version("advanced-alchemy") == "1.11.0"
    assert {
        "DefaultBase",
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
        "metadata_registry",
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
        "JsonB",
        "EncryptedString",
        "EncryptedText",
        "PasswordHash",
        "Bool",
        "Vector",
        "TOTPSecret",
        "OneTimeCode",
        "FileObject",
        "StoredObject",
        "StorageRegistry",
        "storages",
    } <= set(types.__all__)
    assert {
        "SQLAlchemyAsyncRepository",
        "SQLAlchemyAsyncSlugRepository",
        "SQLAlchemyAsyncQueryRepository",
    } <= set(repository.__all__)
    assert {
        "SQLAlchemyAsyncRepositoryService",
        "SQLAlchemyAsyncRepositoryReadService",
        "OffsetPagination",
    } <= set(service.__all__)
    assert {
        "FilterTypes",
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
    } <= set(filters.__all__)
    assert {"MergeStatement", "OnConflictUpsert"} <= set(operations.__all__)
    assert {"RoutingAsyncSessionMaker", "RoundRobinSelector", "RandomSelector"} <= set(routing.__all__)
    assert routing_config.ReplicaConfig is routing_config.EngineConfig
    assert {"RoutingConfig", "RoutingStrategy"} <= set(routing_config.__all__)
    assert {"SQLAlchemyPlugin", "SQLAlchemyAsyncConfig", "SQLAlchemyDTO", "SQLAlchemyDTOConfig"} <= set(
        litestar.__all__
    )
    assert {"AdvancedAlchemy", "assign_cli_group"} <= set(fastapi.__all__)
    assert {"AdvancedAlchemy", "FlaskServiceMixin"} <= set(flask.__all__)
    assert "AdvancedAlchemy" in sanic.__all__
    assert "AdvancedAlchemy" in starlette.__all__
    assert {"make-migrations", "show-current-revision"} <= database_group.commands.keys()
    assert {"revision", "current", "create-database"}.isdisjoint(database_group.commands)
