from importlib.metadata import version
from typing import Any, cast

import msgspec
import pytest


def test_msgspec_0211_rename_and_meta_contract() -> None:
    assert version("msgspec") == "0.21.1"

    class User(msgspec.Struct, rename="camel"):
        first_name: str

    assert msgspec.to_builtins(User(first_name="Ada")) == {"firstName": "Ada"}
    with pytest.raises(TypeError):
        cast("Any", msgspec.Meta)(rename="camel")

    class PostInitStruct(msgspec.Struct):
        count: int
        initialized: bool = False

        def __post_init__(self) -> None:
            self.initialized = True

    replaced = msgspec.structs.replace(PostInitStruct(count=1), count=2)
    assert replaced.count == 2
    assert replaced.initialized is True
