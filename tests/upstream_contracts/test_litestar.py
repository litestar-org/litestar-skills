from importlib.metadata import version
from typing import get_args

from litestar.di import NamedDependency
from litestar.params import FromPath, FromQuery, PathParameter, QueryParameter


def test_litestar_224_explicit_parameter_and_dependency_contract() -> None:
    assert version("litestar") == "2.24.0"
    assert isinstance(get_args(FromPath[int])[1], PathParameter)
    assert isinstance(get_args(FromQuery[str])[1], QueryParameter)
    assert get_args(NamedDependency[str])[0] is str
