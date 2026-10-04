import ast
import importlib.util
import inspect
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any, TypedDict, cast

import attrs
import msgspec
import polyfactory
import polyfactory.factories
import pydantic
import pytest
from polyfactory import (
    AsyncPersistenceProtocol,
    BaseFactory,
    ConfigurationException,
    Ignore,
    PostGenerated,
    Require,
    SyncPersistenceProtocol,
    Use,
)
from polyfactory.decorators import post_generated
from polyfactory.exceptions import MissingBuildKwargException, ParameterException
from polyfactory.factories.attrs_factory import AttrsFactory
from polyfactory.factories.beanie_odm_factory import BeanieDocumentFactory
from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.factories.msgspec_factory import MsgspecFactory
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.factories.sqlalchemy_factory import (
    SQLAlchemyFactory,
    SQLAlchemyPersistenceMethod,
)
from polyfactory.factories.typed_dict_factory import TypedDictFactory
from polyfactory.pytest_plugin import register_fixture
from sqlalchemy import Computed, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column
from typing_extensions import NotRequired, Required


def test_polyfactory_330_public_exports_and_factory_bases() -> None:
    """Verify polyfactory 3.3.0 version, top-level exports, submodule export boundaries, and all 8 factory bases."""
    assert version("polyfactory") == "3.3.0"
    assert polyfactory.factories.__all__ == ("BaseFactory", "DataclassFactory", "TypedDictFactory")
    assert not hasattr(polyfactory.factories, "ModelFactory")
    assert not hasattr(polyfactory.factories, "MsgspecFactory")
    assert not hasattr(polyfactory.factories, "SQLAlchemyFactory")
    assert not hasattr(polyfactory, "register_fixture")
    assert not hasattr(polyfactory, "post_generated")
    assert BaseFactory.__allow_none_optionals__ is True
    assert BaseFactory.__check_model__ is True
    assert BaseFactory.__use_defaults__ is False
    assert BaseFactory.__set_as_default_factory_for_type__ is False
    assert BaseFactory.__randomize_collection_length__ is False
    assert BaseFactory.__min_collection_length__ == 0
    assert BaseFactory.__max_collection_length__ == 5
    assert BaseFactory.__faker__ is not None
    assert BaseFactory.__random__ is not None
    assert hasattr(BaseFactory, "build")
    assert hasattr(BaseFactory, "batch")
    assert hasattr(BaseFactory, "coverage")
    assert hasattr(BaseFactory, "create_async")
    assert hasattr(BaseFactory, "create_batch_async")
    assert hasattr(BaseFactory, "create_sync")
    assert hasattr(BaseFactory, "create_batch_sync")
    assert hasattr(BaseFactory, "seed_random")
    assert hasattr(BaseFactory, "add_provider")
    assert not hasattr(BaseFactory, "build_async")
    assert issubclass(ModelFactory, BaseFactory)
    assert issubclass(DataclassFactory, BaseFactory)
    assert issubclass(MsgspecFactory, BaseFactory)
    assert issubclass(AttrsFactory, BaseFactory)
    assert issubclass(TypedDictFactory, BaseFactory)
    assert issubclass(SQLAlchemyFactory, BaseFactory)
    assert issubclass(BeanieDocumentFactory, ModelFactory)
    assert AsyncPersistenceProtocol is not None
    assert SyncPersistenceProtocol is not None

    odmantic_spec = importlib.util.find_spec("polyfactory.factories.odmantic_odm_factory")
    assert odmantic_spec is not None and odmantic_spec.origin is not None
    odmantic_tree = ast.parse(Path(odmantic_spec.origin).read_text(encoding="utf-8"))
    class_names = {node.name for node in ast.walk(odmantic_tree) if isinstance(node, ast.ClassDef)}
    assert "OdmanticModelFactory" in class_names


def test_polyfactory_330_fields_and_post_generated_contract() -> None:
    """Verify Use, Ignore(), Require(), PostGenerated, @post_generated, seed_random, and add_provider behavior."""
    assert list(inspect.signature(PostGenerated).parameters)[:2] == ["fn", "args"]

    class CustomToken(str):
        pass

    BaseFactory.add_provider(CustomToken, lambda: CustomToken("tok_fixed"))

    @dataclass
    class Order:
        order_id: int
        total_cents: int
        status: str
        tenant_id: str
        token: CustomToken
        reference: str
        summary: str
        internal_note: str = field(default="default-note")

    def build_reference(name: str, values: dict[str, object], prefix: str) -> str:
        return f"{prefix}-{values['order_id']}"

    class OrderFactory(DataclassFactory[Order]):
        __random_seed__ = 42
        status = "pending"
        total_cents = Use(lambda: 500)
        tenant_id = Require()
        internal_note = Ignore()
        reference = PostGenerated(build_reference, "ord")

        @post_generated
        @classmethod
        def summary(cls, order_id: int, status: str) -> str:
            return f"{status}:{order_id}"

    assert vars(OrderFactory)["__model__"] is Order

    with pytest.raises(MissingBuildKwargException):
        OrderFactory.build()

    OrderFactory.seed_random(42)
    built = OrderFactory.build(tenant_id="acme")
    OrderFactory.seed_random(42)
    rebuilt = OrderFactory.build(tenant_id="acme")
    assert built == rebuilt
    assert built.status == "pending"
    assert built.total_cents == 500
    assert built.tenant_id == "acme"
    assert built.token == CustomToken("tok_fixed")
    assert built.internal_note == "default-note"
    assert built.reference == f"ord-{built.order_id}"
    assert built.summary == f"pending:{built.order_id}"
    assert len(OrderFactory.batch(2, tenant_id="acme")) == 2
    assert len(list(OrderFactory.coverage(tenant_id="acme"))) >= 1

    with pytest.raises(TypeError, match="post_generated decorator can only be used on classmethods"):
        post_generated(build_reference)


def test_polyfactory_330_pydantic_msgspec_attrs_typeddict_contract() -> None:
    """Verify ModelFactory, MsgspecFactory, AttrsFactory, and TypedDictFactory."""

    class PayloadModel(pydantic.BaseModel):
        item_name: str = pydantic.Field(validation_alias="itemName", examples=["widget"])
        count: int

    class PayloadFactory(ModelFactory[PayloadModel]):
        __by_name__ = True
        __use_examples__ = True

    model_instance = PayloadFactory.build()
    assert model_instance.item_name == "widget"
    constructed = PayloadFactory.build(factory_use_construct=True, count="not-an-int")
    assert cast("object", constructed.count) == "not-an-int"

    class EventStruct(msgspec.Struct):
        name: str
        optional_tag: str | msgspec.UnsetType = msgspec.UNSET

    class EventFactory(MsgspecFactory[EventStruct]):
        pass

    event_instance = EventFactory.build()
    assert isinstance(event_instance, EventStruct)

    @attrs.define
    class ItemAttrs:
        sku: str
        qty: int

    class ItemAttrsFactory(AttrsFactory[ItemAttrs]):
        pass

    attrs_instance = ItemAttrsFactory.build()
    assert isinstance(attrs_instance, ItemAttrs)

    class ConfigDict(TypedDict):
        host: Required[str]
        port: NotRequired[int]

    class ConfigDictFactory(TypedDictFactory[ConfigDict]):
        pass

    td_instance = ConfigDictFactory.build()
    assert "host" in td_instance

    with pytest.raises(ConfigurationException):
        ModelFactory.create_factory(cast("Any", EventStruct))


def test_polyfactory_330_sqlalchemy_and_pytest_plugin_contract() -> None:
    """Verify SQLAlchemyFactory 3.3 flags, persistence enum, MappedAsDataclass, and register_fixture."""
    assert hasattr(SQLAlchemyPersistenceMethod, "FLUSH")
    assert hasattr(SQLAlchemyPersistenceMethod, "COMMIT")
    assert SQLAlchemyFactory.__set_primary_key__ is True
    assert SQLAlchemyFactory.__set_foreign_keys__ is True
    assert SQLAlchemyFactory.__set_relationships__ is True
    assert SQLAlchemyFactory.__set_association_proxy__ is True
    assert SQLAlchemyFactory.__persistence_method__ == SQLAlchemyPersistenceMethod.COMMIT

    class Base(MappedAsDataclass, DeclarativeBase):
        pass

    class InvoiceModel(Base):
        __tablename__ = "invoices_contract_test"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
        code: Mapped[str] = mapped_column(String(32))
        computed_tag: Mapped[str] = mapped_column(
            String(64),
            Computed("code || '-tag'"),
            init=False,
        )

    class InvoiceModelFactory(SQLAlchemyFactory[InvoiceModel]):
        pass

    invoice = InvoiceModelFactory.build()
    assert isinstance(invoice, InvoiceModel)
    assert isinstance(invoice.code, str)

    reg_sig = inspect.signature(register_fixture)
    assert list(reg_sig.parameters) == ["factory", "scope", "autouse", "name"]

    with pytest.raises(ParameterException):
        register_fixture(cast("Any", InvoiceModel))
