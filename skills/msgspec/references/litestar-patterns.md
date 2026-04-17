# msgspec — Litestar patterns

This file covers patterns specific to Litestar applications. For the generic msgspec API
(Struct definitions, Meta constraints, tagged unions, enc_hook/dec_hook, convert()), see the
parent [`SKILL.md`](../SKILL.md).

## CamelizedBaseStruct

Canonical Litestar apps define a two-level base hierarchy. The pattern below is from
`litestar-fullstack-spa/src/py/app/lib/schema.py:L9–15` (identical shape in
`dma/accelerator/src/py/dma/lib/schemas.py:L14–15` and
`litestar-sqlstack/src/sqlstack/lib/schema.py:L30–31`).

```python
from typing import Any

import msgspec


class BaseStruct(msgspec.Struct):
    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__struct_fields__ if getattr(self, f, None) != msgspec.UNSET}


class CamelizedBaseStruct(BaseStruct, rename="camel"):
    """Camelized Base Struct."""
```

Example subclass using a neutral domain (pattern from
`litestar-fullstack-spa/src/py/app/domain/tags/schemas/_tag.py:L8–13`):

```python
from uuid import UUID


class Tag(CamelizedBaseStruct):
    """Tag Information."""

    id: UUID
    slug: str
    name: str
```

`rename="camel"` serializes `snake_case` field names as `camelCase` JSON keys automatically.
No `from __future__ import annotations` — modules that define `msgspec.Struct` subclasses
must not use it (runtime introspection breaks).

## to_json — pick the branch that matches your stack

### Branch A — sqlspec-stack

Re-export sqlspec's built-in serializer. It installs an `enc_hook` that already handles UUID,
datetime, Enum, Decimal, Pydantic models, dataclasses, attrs, and msgspec.Struct with zero
additional code. Pattern from `dma/accelerator/src/py/dma/utils/serialization.py:L1–3`.

```python
# myapp/utils/serialization.py
from sqlspec.utils.serializers import from_json, to_json

__all__ = ("from_json", "to_json")
```

Usage (pattern from `dma/accelerator/src/py/dma/lib/realtime/_publisher.py:L26–27` and
`dma/accelerator/src/py/dma/db/hooks.py:L65–67`):

```python
from myapp.utils.serialization import to_json

payload = to_json(order, as_bytes=True)
await backend.publish(payload, channels=[f"orders:{order.id}:events"])
```

### Branch B — sqlspec not in-stack

Hand-roll an `Encoder` singleton with a custom `enc_hook`. Pattern from
`litestar-fullstack-spa/src/py/app/utils/serialization.py:L1–47`.

```python
# myapp/utils/serialization.py
import datetime as _dt
from typing import Any
from uuid import UUID

import msgspec
from pydantic import BaseModel


def _default(value: Any) -> str:
    if isinstance(value, BaseModel):
        import json
        return json.dumps(value.model_dump(by_alias=True))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, _dt.datetime):
        return value.astimezone(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


_encoder = msgspec.json.Encoder(enc_hook=_default)


def to_json(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return _encoder.encode(value)
```

Drop the `BaseModel` branch if your project has no Pydantic dependency.

### Decision guide

| Situation | Pick |
| --- | --- |
| sqlspec is in-stack | Branch A — one-line re-export, zero maintenance |
| sqlspec not available | Branch B — hand-rolled enc_hook |

Both are canonical. Choose based on your existing dependencies, not preference.

## Hybrid msgspec + Pydantic

When a single app needs both msgspec Structs for high-throughput response shapes *and*
Pydantic for request bodies that require `validate_assignment` or complex field validators,
pair both base classes. Pattern from
`litestar-fullstack-spa/src/py/app/lib/schema.py:L22–36`.

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
Pattern adapted from `dma/accelerator/src/py/dma/lib/realtime/_contract.py:L60–80`.

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

`__post_init__` runs after `__init__` and after msgspec's own field validation, making it the
correct location for cross-field invariants. Raise `ValueError` (not `TypeError`) so callers
and Litestar's exception handlers can treat it as a validation failure.

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
apps surveyed (litestar-fullstack-spa, dma/accelerator, litestar-sqlstack, oracledb-vertexai-demo)
use it. If your wire protocol already requires MessagePack, the API is symmetric with
`msgspec.json` (encode/decode, Encoder/Decoder). Otherwise default to JSON.

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
