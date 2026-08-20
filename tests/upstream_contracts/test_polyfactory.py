import inspect
from importlib.metadata import version

from polyfactory.factories import BaseFactory
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyPersistenceMethod
from polyfactory.fields import PostGenerated


def test_polyfactory_330_persistence_and_post_generated_contract() -> None:
    assert version("polyfactory") == "3.3.0"
    assert BaseFactory.__allow_none_optionals__ is True
    assert hasattr(BaseFactory, "create_async")
    assert not hasattr(BaseFactory, "build_async")
    assert list(inspect.signature(PostGenerated).parameters)[:2] == ["fn", "args"]
    assert hasattr(SQLAlchemyPersistenceMethod, "FLUSH")
    assert hasattr(SQLAlchemyPersistenceMethod, "COMMIT")
