# msgspec — Litestar patterns

This file covers patterns specific to Litestar applications. For the generic msgspec API
(Struct definitions, Meta constraints, tagged unions, enc_hook/dec_hook, convert()), see the
parent [`SKILL.md`](../SKILL.md).

## CamelizedBaseStruct

Canonical Litestar apps define a two-level base hierarchy. The pattern below is from
[litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/py/app/lib/schema.py:L9–15`, identical shape in
[litestar-sqlstack](https://github.com/cofin/litestar-sqlstack) `src/sqlstack/lib/schema.py:L30–31`).

```python
from typing import Any

import msgspec


class BaseStruct(msgspec.Struct):
    def to_dict(self) -> dict[str, Any]:
        return msgspec.to_builtins(self)


class CamelizedBaseStruct(BaseStruct, rename="camel"):
    """Camelized Base Struct."""
```

Example subclass using a neutral domain (pattern from
`litestar-fullstack/src/py/app/domain/tags/schemas/_tag.py:L8–13`):

```python
from uuid import UUID


class Tag(CamelizedBaseStruct):
    """Tag Information."""

    id: UUID
    slug: str
    name: str
```

`rename="camel"` serializes `snake_case` field names as `camelCase` JSON keys automatically.
Library/shared modules that define runtime-introspected `msgspec.Struct` subclasses usually avoid postponed annotations unless the consuming tool resolves them. Consumer modules that import/use these structs MAY use future annotations freely.

### Partial Updates (`PATCH`) with `msgspec.UNSET`

Use `msgspec.UNSET` (`msgspec.UnsetType`) on `PATCH` request Structs so handlers can distinguish an
omitted key from an explicit `null`:

```python
from typing import Any
import msgspec


class PatchBaseStruct(CamelizedBaseStruct, kw_only=True, forbid_unknown_fields=True):
    def to_update_dict(self) -> dict[str, Any]:
        """Return set fields keyed by Python attribute name for service/repository updates."""
        return {f: val for f in self.__struct_fields__ if (val := getattr(self, f)) is not msgspec.UNSET}


class TagUpdate(PatchBaseStruct):
    name: str | msgspec.UnsetType = msgspec.UNSET
    description: str | None | msgspec.UnsetType = msgspec.UNSET
```

- `msgspec.to_builtins(self)` recursively converts to builtin types using wire names (`camelCase`)
  and omits `msgspec.UNSET` fields.
- `msgspec.structs.asdict(self)` returns a shallow dict keyed by Python attribute names
  (`snake_case`) and retains `msgspec.UNSET` values unless filtered as shown in `to_update_dict()`.

## to_json — pick the branch that matches your stack

### Branch A — sqlspec-stack

Re-export sqlspec's built-in serializer. It installs an `enc_hook` that already handles UUID,
datetime, Enum, Decimal, Pydantic models, dataclasses, attrs, and msgspec.Struct with zero
additional code.

```python
# myapp/utils/serialization.py
from sqlspec.utils.serializers import from_json, to_json

__all__ = ("from_json", "to_json")
```

Usage:

```python
from myapp.utils.serialization import to_json

payload = to_json(order, as_bytes=True)
await backend.publish(payload, channels=[f"orders:{order.id}:events"])
```

### Branch B — sqlspec not in-stack

Use a plain `Encoder` singleton. msgspec natively handles UUID, datetime, date, time, Decimal,
Enum, dataclasses, attrs classes, and Struct instances; do not duplicate those types in an
`enc_hook`.

```python
# myapp/utils/serialization.py
from typing import Any

import msgspec


_encoder = msgspec.json.Encoder()


def to_json(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return _encoder.encode(value)
```

If the payload contains an unsupported custom type, add a narrow `enc_hook` that handles only
that type and raises `NotImplementedError` for all others. If Pydantic is already in-stack and a
Pydantic model must cross this serializer, return `value.model_dump(by_alias=True)` from that
specific hook branch; never return a JSON string from an `enc_hook`.

### Decision guide

| Situation | Pick |
| --- | --- |
| sqlspec is in-stack | Branch A — one-line re-export, zero maintenance |
| sqlspec not available | Branch B — plain msgspec encoder |

Both are canonical. Choose based on your existing dependencies, not preference.

## Hybrid msgspec + Pydantic

When a single app needs both msgspec Structs for high-throughput response shapes *and*
Pydantic for request bodies that require `validate_assignment` or complex field validators,
pair both base classes. Pattern from
`litestar-fullstack/src/py/app/lib/schema.py:L22–36`.

```python
from advanced_alchemy.utils.text import camelize
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base Pydantic schema."""

    model_config = ConfigDict(
        validate_assignment=True,
        from_attributes=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
    )


class CamelizedBaseSchema(BaseSchema):
    """Camelized base Pydantic schema."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=camelize)
```

Usage convention:

- **`CamelizedBaseStruct`** for response shapes — fast, memory-efficient, camelCase wire format.
- **`CamelizedBaseSchema`** for request bodies — Pydantic's `validate_assignment`, `alias_generator=camelize`, and validator ecosystem when needed.

`alias_generator=camelize` (from `advanced_alchemy.utils.text`) is the Pydantic equivalent of
msgspec's `rename="camel"`.

## \_\_post_init\_\_ validation

`msgspec.Struct` supports `__post_init__` for cross-field validation after construction.

```python
from typing import Literal
from uuid import UUID

import msgspec


class Order(CamelizedBaseStruct, kw_only=True):
    id: UUID
    status: Literal["draft", "placed", "shipped"]
    shipping_address: str | None = None

    def __post_init__(self) -> None:
        if self.status in {"placed", "shipped"} and self.shipping_address is None:
            msg = "shipping_address is required once the order leaves draft"
            raise ValueError(msg)
```

`__post_init__` runs after direct `__init__`, typed decode, `convert()`, and, as of msgspec
0.21.0, `msgspec.structs.replace()` and Python's `copy.replace()`. Direct construction does not
validate field annotations first. Typed decode and `convert()` validate fields before the hook;
in those paths a `ValueError` or `TypeError` becomes a path-aware `msgspec.ValidationError`.
To normalize a field inside `__post_init__` on a `frozen=True` Struct, call
`msgspec.structs.force_setattr(self, "field_name", normalized_value)`.

## DTO vs response schema

Choose the right layer for the job:

- **`msgspec.Struct`** for wire shapes and internal messaging — lowest overhead, fastest
  encode/decode, sufficient for the vast majority of Litestar response bodies.
- **Pydantic (`BaseModel` / `CamelizedBaseSchema`)** when Litestar-Pydantic DTO paths are
  required, or when Pydantic validators (`@field_validator`, `@model_validator`) are essential
  for the request body.
- **Hybrid (`CamelizedBaseStruct` + `CamelizedBaseSchema`)** only when both concerns coexist
  in the same application — use Struct for responses and Pydantic schema for the request side.

Avoid reaching for the hybrid pattern purely for familiarity; the added dependency surface and
dual base-class maintenance cost is only justified when Pydantic-ecosystem tooling is genuinely
required.

## MessagePack — honest scope

msgspec supports MessagePack via `msgspec.msgpack`. None of the canonical Litestar reference
apps surveyed (litestar-fullstack, litestar-sqlstack, [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo)) use it. If
your wire protocol already requires MessagePack, the API is symmetric with `msgspec.json`
(encode/decode, Encoder/Decoder). Otherwise default to JSON.

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
