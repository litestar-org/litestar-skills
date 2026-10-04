import enum
import inspect as stdlib_inspect
from decimal import Decimal
from importlib.metadata import version
from typing import Annotated, Any, Literal, cast

import msgspec
import pytest
from litestar import Litestar, post
from litestar.dto import DTOConfig, MsgspecDTO
from litestar.testing import TestClient


def test_msgspec_0220_public_api_and_exceptions_contract() -> None:
    """Verify top-level exports, submodules, and exception hierarchy in msgspec 0.22.0."""
    assert version("msgspec") == "0.22.0"
    assert msgspec.__version__ == "0.22.0"

    expected_exports = {
        "NODEFAULT",
        "UNSET",
        "DecodeError",
        "EncodeError",
        "Meta",
        "MsgspecError",
        "Raw",
        "Struct",
        "StructMeta",
        "UnsetType",
        "ValidationError",
        "convert",
        "defstruct",
        "field",
        "inspect",
        "json",
        "msgpack",
        "structs",
        "to_builtins",
        "toml",
        "yaml",
    }
    assert expected_exports <= set(dir(msgspec))
    assert "FrozenDictType" in set(dir(msgspec.inspect))
    assert issubclass(msgspec.EncodeError, msgspec.MsgspecError)
    assert issubclass(msgspec.DecodeError, msgspec.MsgspecError)
    assert issubclass(msgspec.ValidationError, msgspec.DecodeError)
    assert isinstance(msgspec.UNSET, msgspec.UnsetType)
    assert bool(msgspec.UNSET) is False


def test_msgspec_0220_struct_options_and_helpers_contract() -> None:
    """Verify Struct options, StructConfig, structs helpers, and 0.20-0.22 behavior."""
    with pytest.raises(ValueError, match="Cannot set gc=False and dict=True"):
        msgspec.defstruct("InvalidDictStruct", [("x", int)], gc=False, dict=True)

    with pytest.raises(ValueError, match="Cannot set gc=False and weakref=True"):
        msgspec.defstruct("InvalidWeakrefStruct", [("x", int)], gc=False, weakref=True)

    class WeakBase(msgspec.Struct, weakref=True):
        x: int

    with pytest.raises(ValueError, match="Cannot set gc=False and weakref=True"):
        msgspec.defstruct("InvalidInheritedWeakref", [("y", int)], bases=(WeakBase,), gc=False)

    class User(
        msgspec.Struct,
        tag="user",
        tag_field="kind",
        rename="camel",
        omit_defaults=True,
        forbid_unknown_fields=True,
        frozen=True,
        eq=True,
        order=True,
        kw_only=True,
        repr_omit_defaults=True,
        array_like=False,
        gc=True,
        weakref=True,
        dict=True,
        cache_hash=True,
    ):
        first_name: str
        nickname: str | msgspec.UnsetType = msgspec.UNSET
        role: str = msgspec.field(default="member", name="userRole")

    cfg = User.__struct_config__
    assert isinstance(cfg, msgspec.structs.StructConfig)
    assert cfg.tag == "user"
    assert cfg.tag_field == "kind"
    assert cfg.omit_defaults is True
    assert cfg.forbid_unknown_fields is True
    assert cfg.frozen is True
    assert cfg.eq is True
    assert cfg.order is True
    assert cfg.repr_omit_defaults is True
    assert cfg.array_like is False
    assert cfg.gc is True
    assert cfg.weakref is True
    assert cfg.dict is True
    assert cfg.cache_hash is True

    u = User(first_name="Ada")
    assert msgspec.to_builtins(u) == {"kind": "user", "firstName": "Ada"}
    assert msgspec.structs.asdict(u) == {"first_name": "Ada", "nickname": msgspec.UNSET, "role": "member"}
    assert msgspec.structs.astuple(u) == ("Ada", msgspec.UNSET, "member")

    msgspec.structs.force_setattr(u, "first_name", "Grace")
    assert u.first_name == "Grace"

    field_infos = msgspec.structs.fields(User)
    assert [f.name for f in field_infos] == ["first_name", "nickname", "role"]
    assert [f.encode_name for f in field_infos] == ["firstName", "nickname", "userRole"]
    assert [f.required for f in field_infos] == [True, False, False]
    assert field_infos[0].default is msgspec.NODEFAULT

    assert msgspec.inspect.is_struct(u) is True
    assert msgspec.inspect.is_struct_type(User) is True
    assert isinstance(User, msgspec.StructMeta)

    class AliasBase(msgspec.Struct):
        first_name: str = msgspec.field(name="firstName")

    class AliasResetChild(AliasBase):
        first_name: str = msgspec.field(name="first_name")

    assert msgspec.json.encode(AliasResetChild(first_name="Ada")) == b'{"first_name":"Ada"}'

    class PostInitStruct(msgspec.Struct):
        count: int
        initialized: bool = False

        def __post_init__(self) -> None:
            self.initialized = True

    replaced = msgspec.structs.replace(PostInitStruct(count=1), count=2)
    assert replaced.count == 2
    assert replaced.initialized is True

    copied = PostInitStruct(count=1).__replace__(count=3)
    assert copied.count == 3
    assert copied.initialized is True


def test_msgspec_0220_meta_schema_and_codecs_contract() -> None:
    """Verify Meta constraints, JSON Schema 0.21-0.22 options, decimal_format, Raw, dec_hook, and MsgspecDTO."""
    with pytest.raises(TypeError):
        cast("Any", msgspec.Meta)(rename="camel")

    with pytest.raises(ValueError, match="Cannot specify both `gt` and `ge`"):
        cast("Any", msgspec.Meta)(gt=0, ge=0)

    with pytest.raises(ValueError, match="Cannot specify both `lt` and `le`"):
        cast("Any", msgspec.Meta)(lt=10, le=10)

    with pytest.raises(TypeError):
        msgspec.json.Decoder(Annotated[Decimal, msgspec.Meta(gt=0)])

    with pytest.raises(TypeError):
        msgspec.json.Decoder(Annotated[tuple[int, str], msgspec.Meta(min_length=1)])

    class Item(msgspec.Struct):
        tags: set[Annotated[str, msgspec.Meta(min_length=1)]]
        scores: Annotated[tuple[int, ...], msgspec.Meta(min_length=1)]
        counts: dict[Annotated[str, msgspec.Meta(pattern=r"^[a-z0-9-]+$", title="Slug")], int]
        buf: bytearray = msgspec.field(default_factory=bytearray)
        note: str | None = None

    schema_sig = stdlib_inspect.signature(msgspec.json.schema)
    assert "ref_template" in schema_sig.parameters
    assert "schema_hook" in schema_sig.parameters

    item_schema = msgspec.json.schema(Item, ref_template="#/components/schemas/{name}")
    assert item_schema["$ref"] == "#/components/schemas/Item"
    defs = item_schema["$defs"]["Item"]
    assert defs["properties"]["tags"]["uniqueItems"] is True
    assert defs["properties"]["buf"]["default"] == ""
    assert defs["properties"]["note"]["anyOf"][-1] == {"type": "null"}
    assert defs["properties"]["counts"]["propertyNames"] == {"title": "Slug", "pattern": "^[a-z0-9-]+$"}

    assert msgspec.json.decode(b"true", type=Literal[True]) is True
    assert msgspec.json.schema(Literal[1, None]) == {"enum": [None, 1]}

    dec_encoder = msgspec.json.Encoder(decimal_format=float)
    assert dec_encoder.encode(Decimal("1.25")) == b"1.25"

    class Color(enum.Enum):
        RED = "red"

    assert msgspec.json.encode({Color.RED: 1}) == b'{"red":1}'

    raw = msgspec.Raw(b'{"tags":["a"],"scores":[1,2],"counts":{"ok-1":3}}')
    assert msgspec.convert(raw.copy(), msgspec.Raw) == raw
    decoded = msgspec.json.decode(raw.copy(), type=Item)
    assert decoded == Item(tags={"a"}, scores=(1, 2), counts={"ok-1": 3})

    def raising_dec_hook(tp: type, obj: object) -> object:
        if tp is complex:
            raise msgspec.DecodeError("custom decode failure")
        raise NotImplementedError

    with pytest.raises(msgspec.DecodeError) as exc_info:
        msgspec.json.decode(b'"bad"', type=complex, dec_hook=raising_dec_hook)
    assert type(exc_info.value) is msgspec.DecodeError

    class Account(msgspec.Struct, kw_only=True):
        id: int = 1
        name: str
        internal_note: str = "audit-only"

    class AccountCreateDTO(MsgspecDTO[Account]):
        config = DTOConfig(exclude={"id", "internal_note"})

    class AccountReadDTO(MsgspecDTO[Account]):
        config = DTOConfig(exclude={"internal_note"})

    @post("/accounts", dto=AccountCreateDTO, return_dto=AccountReadDTO, sync_to_thread=False)
    def create_account(data: Account) -> Account:
        return data

    with TestClient(app=Litestar(route_handlers=[create_account])) as client:
        response = client.post("/accounts", json={"name": "Ada"})
        assert response.status_code == 201
        assert response.json() == {"id": 1, "name": "Ada"}

    assert {"Encoder", "Decoder", "encode", "decode", "format", "schema", "schema_components"} <= set(dir(msgspec.json))
    assert {"Encoder", "Decoder", "Ext", "encode", "decode"} <= set(dir(msgspec.msgpack))
    assert set(msgspec.yaml.__all__) == {"encode", "decode"}
    assert set(msgspec.toml.__all__) == {"encode", "decode"}
