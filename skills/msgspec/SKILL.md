---
name: msgspec
description: "Auto-activate for msgspec, Struct, Meta, msgspec.json, msgspec.msgpack, tagged unions, enc_hook, dec_hook, convert(), or Litestar DTO shapes. Not for Pydantic or ORM models — use their stack-specific skill."
---

# msgspec Skill

msgspec is a high-performance Python library for serialization, deserialization, and typed
validation. This guidance targets the immutable `0.21.1` release.

## Code Style Rules

- Use PEP 604 for unions: `T | None` (not `Optional[T]`)
- **`from __future__ import annotations` rule** — Library/shared modules that define runtime-introspected `msgspec.Struct` subclasses should avoid postponed annotations unless the consuming tool resolves them. Consumer modules that only use Structs MAY use future annotations.
- Annotate every serialized field; only annotated attributes become Struct fields
- Use `kw_only=True` for Structs with more than 2 fields
- Put wire-name configuration on `msgspec.field(name=...)` or the Struct's `rename=`
  option; `msgspec.Meta` defines constraints and JSON Schema metadata, not field aliases

## Quick Reference

### Struct Definition

```python
import msgspec

# Basic struct
class User(msgspec.Struct):
    id: int
    name: str
    email: str | None = None

# Performance options
class Event(msgspec.Struct, frozen=True, gc=False):
    """frozen=True: immutable + hashable. gc=False: skip GC for short-lived objects."""
    event_type: str
    payload: dict[str, object]

# Keyword-only (recommended for >2 fields)
class Config(msgspec.Struct, kw_only=True):
    host: str
    port: int = 5432
    ssl: bool = False

# Array-like encoding (tuple encoding, more compact)
class Point(msgspec.Struct, array_like=True):
    x: float
    y: float

# Rename fields for serialization
class ApiResponse(msgspec.Struct, rename="camel"):
    user_id: int         # serialized as "userId"
    created_at: str      # serialized as "createdAt"

# Rename one field explicitly
class Resource(msgspec.Struct):
    resource_id: int = msgspec.field(name="id")

# Reject unknown fields at API boundaries
class StrictInput(msgspec.Struct, forbid_unknown_fields=True):
    name: str
    value: int
```

### Validation Constraints

```python
from datetime import datetime
from typing import Annotated

import msgspec
from msgspec import Meta

class Product(msgspec.Struct):
    name: Annotated[str, Meta(min_length=1, max_length=100)]
    price: Annotated[float, Meta(gt=0)]
    quantity: Annotated[int, Meta(ge=0, le=10_000)]
    sku: Annotated[str, Meta(pattern=r"^[A-Z]{2}-\d{4}$")]
    batch_size: Annotated[int, Meta(multiple_of=5)]
    expires_at: Annotated[datetime, Meta(tz=True)]

# Reusable constraint aliases
PositiveInt = Annotated[int, Meta(gt=0)]
NonEmptyStr = Annotated[str, Meta(min_length=1)]
Percentage = Annotated[float, Meta(ge=0.0, le=100.0)]

class Order(msgspec.Struct):
    id: PositiveInt
    label: NonEmptyStr
    discount: Percentage = 0.0
```

### Serialization

```python
import msgspec

# JSON -- singleton encoder/decoder (cache these!)
encoder = msgspec.json.Encoder()
decoder = msgspec.json.Decoder(User)

data = encoder.encode(user)          # bytes
user = decoder.decode(b'{"id":1,"name":"Alice"}')

# Functional API (convenience, slightly slower)
data = msgspec.json.encode(user)
user = msgspec.json.decode(b'...', type=User)

# MessagePack (binary, more compact)
data = msgspec.msgpack.encode(user)
user = msgspec.msgpack.decode(data, type=User)

# Hooks are only for unsupported custom types. datetime, UUID, Decimal, and
# Enum are already supported.

def enc_hook(obj: object) -> object:
    if isinstance(obj, complex):
        return (obj.real, obj.imag)
    raise NotImplementedError(f"Unsupported type: {type(obj)}")

def dec_hook(target_type: type, obj: object) -> object:
    if target_type is complex:
        real, imag = obj
        return complex(real, imag)
    raise NotImplementedError(f"Unsupported type: {target_type}")

encoder = msgspec.json.Encoder(enc_hook=enc_hook)
decoder = msgspec.json.Decoder(MyStruct, dec_hook=dec_hook)
```

`dec_hook` runs only for unsupported custom annotations. `TypeError` and `ValueError` raised by
the hook become path-aware `ValidationError`s. In 0.21.1, a `ValidationError` or `DecodeError`
raised by the hook propagates directly and is not wrapped in another `ValidationError`.

### Canonical Litestar serializers (match-your-stack)

Litestar apps typically need `to_json(value, as_bytes=True)` that handles UUID / datetime / Enum / Decimal for Channels broadcasts, log contexts, and JSONB writes. Pick the branch that matches your project.

**Branch A — sqlspec is in-stack.** Re-export sqlspec's serializer; it already installs an `enc_hook` covering UUID, datetime, Enum, Decimal, Pydantic, dataclasses, attrs, and msgspec.Struct.

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

**Branch B — sqlspec is not in-stack.** Use a plain msgspec `Encoder`; the package natively
handles UUID, datetime, date, time, Decimal, Enum, dataclasses, attrs classes, and Structs.

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

### Type Coercion with convert()

```python
import msgspec

raw = {"id": "42", "name": "Alice"}  # id is a string

# Strict mode (default): raises on type mismatch
user = msgspec.convert(raw, User)  # ValidationError: id must be int

# Lax mode: coerces compatible types
user = msgspec.convert(raw, User, strict=False)  # id coerced to 42

# str_keys: dict keys are strings (useful for JSON-loaded dicts)
data = {"1": "Alice", "2": "Bob"}
result = msgspec.convert(data, dict[int, str], str_keys=True)

# Convert with dec_hook for an unsupported custom type
measurement = msgspec.convert(raw_measurement, Measurement, dec_hook=dec_hook)

# Convert a dataclass or arbitrary object to a Struct by reading attributes
from dataclasses import dataclass

@dataclass
class LegacyUser:
    id: int
    name: str

legacy = LegacyUser(id=1, name="Alice")
user = msgspec.convert(legacy, User, from_attributes=True)
```

`from_attributes=False` is the default. Plain mappings convert to object-like output types
without this option; dataclass, attrs, ORM, and other objects require `from_attributes=True`.
`msgspec.structs.asdict()` accepts a `msgspec.Struct`, not an arbitrary dataclass.

### Dynamic Struct Creation

```python
import msgspec

# Runtime struct from field definitions
fields = [
    ("id", int),
    ("name", str),
    ("score", Annotated[float, Meta(ge=0.0)]),
]
DynamicModel = msgspec.defstruct("DynamicModel", fields, kw_only=True)

# With defaults
fields_with_defaults = [
    ("id", int),
    ("active", bool, True),   # (name, type, default)
]
FlexModel = msgspec.defstruct("FlexModel", fields_with_defaults)
```

### Tagged Unions (Discriminated Unions)

```python
import msgspec

# Default tag field is "type", tag value is the class name
class Dog(msgspec.Struct, tag=True):
    name: str
    breed: str

class Cat(msgspec.Struct, tag=True):
    name: str
    indoor: bool

Animal = Dog | Cat

# Deserialize: inspects "type" field to pick correct class
animal = msgspec.json.decode(b'{"type":"Dog","name":"Rex","breed":"Lab"}', type=Animal)

# Custom tag values
class CreateEvent(msgspec.Struct, tag="create"):
    resource: str

class DeleteEvent(msgspec.Struct, tag="delete"):
    resource: str
    soft: bool = True

Event = CreateEvent | DeleteEvent

# Custom tag field name
class V1Request(msgspec.Struct, tag="v1", tag_field="version"):
    payload: str

class V2Request(msgspec.Struct, tag="v2", tag_field="version"):
    payload: str
    metadata: dict[str, str] = {}

Request = V1Request | V2Request
```

All Struct variants in a multi-Struct union must be tagged, use the same `tag_field`, use unique
tag values, and use one tag type (`str` or `int`) consistently. A union may contain non-Struct
types, but it may contain at most one untagged Struct.

### Validation and 0.21 Behavior

- Direct Struct construction trusts the caller and does not enforce field annotations.
  Typed `decode()` and `convert()` perform runtime type and `Meta` constraint validation.
- `msgspec.structs.replace()` and Python's `copy.replace()` call `__post_init__` as of 0.21.0.
- `msgspec.json.schema()` and `schema_components()` accept
  `ref_template="#/$defs/{name}"`; 0.21.1 includes the parameter in the type stub.
- JSON Schema output marks `set` and `frozenset` fields with `uniqueItems`.

<workflow>

## Workflow

### Step 1: Define Structs

Create msgspec Structs for all data shapes. Use `kw_only=True` for Structs with more than 2 fields. Use `frozen=True` for immutable value objects. Use `forbid_unknown_fields=True` for API-boundary input validation.

### Step 2: Add Constraints

Annotate fields with `Annotated[Type, Meta(...)]` for numeric ranges, string lengths, and regex patterns. Define reusable constraint aliases at module level to avoid repetition.

### Step 3: Choose Serialization Strategy

Use `msgspec.json` for JSON APIs and `msgspec.msgpack` for binary protocols or internal
messaging. Instantiate reusable `Encoder`/`Decoder` objects once at module level. Add
`enc_hook`/`dec_hook` only for unsupported custom types; msgspec natively supports datetime,
UUID, Decimal, and Enum.

### Step 4: Handle Polymorphism

Use tagged unions (`tag=True` or `tag="value"`) for discriminated unions. Define a union type alias (`Event = CreateEvent | DeleteEvent`) and decode against it. Use `tag_field` to customize the discriminator field name.

### Step 5: Validate

Test round-trip encode/decode. Confirm `ValidationError` is raised for constraint violations. Verify tag dispatch selects the correct Struct type for all union variants.

</workflow>

<guardrails>

## Guardrails

- **Annotate every serialized field** -- only annotated attributes become Struct fields.
- **Reuse Encoder/Decoder instances** -- configured codec objects are designed for repeated calls.
- **Use `kw_only=True` for Structs with >2 fields** -- prevents positional argument confusion and makes instantiation self-documenting.
- **Use `forbid_unknown_fields=True` at API boundaries** -- rejects payloads with unexpected keys, preventing silent data loss.
- **Use `Meta` for supported field constraints** -- typed decode and `convert()` check these
  constraints and report the failing path; direct Struct construction does not.
- **Never pass `rename` to `Meta`** -- alias one field with `msgspec.field(name=...)` or configure
  the Struct with `rename=`.
- **Avoid non-integral float `multiple_of` constraints** -- binary floating-point precision may
  reject mathematically valid values; use an integer unit when possible.
- **Use `gc=False` for short-lived, non-circular objects** -- eliminates GC overhead for hot-path objects like request/response shapes.
- **Tagged unions for polymorphism** -- faster than manual dispatch and eliminates `isinstance` chains.
- **`from __future__ import annotations` rule** — Library/shared modules that define runtime-introspected types (advanced-alchemy models, sqlspec configs, msgspec Structs, dishka providers) avoid postponed annotations unless their consumers resolve them. Consumer applications MAY use it. The restriction applies only to modules that define introspected types, not handler/service/test modules that use them.
- **Use `strict=False` only at trust boundaries** -- lax coercion is useful for converting legacy dicts but can mask type errors in internal code.
- **Prefer `sqlspec.utils.serializers.to_json` when sqlspec is in-stack** — its built-in enc_hook covers UUID, datetime, Enum, Decimal, Pydantic, msgspec.Struct, dataclasses, and attrs in one import. Hand-rolling is only needed when sqlspec is not a dependency.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering msgspec code, verify:

- [ ] All Struct fields have explicit type annotations
- [ ] If this library/shared module defines runtime-introspected types, avoid `from __future__ import annotations` unless all consumers resolve postponed annotations. Consumer modules may use it.
- [ ] Encoder/Decoder instances are module-level singletons (not created per-request)
- [ ] API-boundary Structs use `forbid_unknown_fields=True`
- [ ] Numeric/string constraints use `Meta` (not manual `if` checks)
- [ ] Field aliases use `msgspec.field(name=...)` or Struct `rename=`; `Meta` does not accept `rename`.
- [ ] Hooks are used only for unsupported custom types; native datetime/UUID/Decimal/Enum paths
      do not duplicate built-in handling
- [ ] Object-to-Struct conversion uses `from_attributes=True`
- [ ] Tagged union tag values are unique across all variants in a union
- [ ] Tagged union variants share one `tag_field` and one tag value type
- [ ] `kw_only=True` on Structs with more than 2 fields
- [ ] If sqlspec is in-stack, to_json is imported from sqlspec.utils.serializers (not hand-rolled)

</validation>

<example>

## Example

**Task:** Define an event system with tagged unions, constraints, and JSON serialization.

```python
# Library/shared modules that define runtime-introspected Structs usually avoid postponed annotations.
```

```python
# events.py
from datetime import UTC, datetime
from typing import Annotated
import uuid

import msgspec
from msgspec import Meta

# --- Constraint aliases ---
NonEmptyStr = Annotated[str, Meta(min_length=1, max_length=255)]
PositiveInt = Annotated[int, Meta(gt=0)]

# --- Event variants (tagged union) ---
class UserCreatedEvent(msgspec.Struct, tag="user.created", tag_field="event_type", kw_only=True, gc=False):
    event_id: uuid.UUID
    user_id: PositiveInt
    email: NonEmptyStr
    occurred_at: datetime

class UserDeletedEvent(msgspec.Struct, tag="user.deleted", tag_field="event_type", kw_only=True, gc=False):
    event_id: uuid.UUID
    user_id: PositiveInt
    occurred_at: datetime
    reason: str | None = None

UserEvent = UserCreatedEvent | UserDeletedEvent

# --- Reusable codec; datetime and UUID are supported natively ---
_encoder = msgspec.json.Encoder()
_decoder = msgspec.json.Decoder(UserEvent)

def encode_event(event: UserEvent) -> bytes:
    return _encoder.encode(event)

def decode_event(data: bytes) -> UserEvent:
    return _decoder.decode(data)

# --- Usage ---
event = UserCreatedEvent(
    event_id=uuid.uuid4(),
    user_id=42,
    email="alice@example.com",
    occurred_at=datetime.now(UTC),
)
payload = encode_event(event)
# b'{"event_type":"user.created","event_id":"...","user_id":42,"email":"alice@example.com","occurred_at":"..."}'

recovered = decode_event(payload)
assert isinstance(recovered, UserCreatedEvent)
```

</example>

---

## References Index

For detailed guides and reference tables, refer to the following documents in `references/`:

- **[Meta Constraints Reference](references/constraints.md)** -- Full table of all Meta constraint parameters with examples for numeric, string, bytes, and OpenAPI metadata.
- **[Tagged Union Patterns](references/tagged-unions.md)** -- Discriminated union patterns: default tags, custom tag fields/values, nested unions, API versioning, and event systems.
- **[Litestar Patterns](references/litestar-patterns.md)** — CamelizedBaseStruct, sqlspec-vs-manual to_json branches, hybrid msgspec + Pydantic schema pattern, `__post_init__` validation for Litestar apps.

---

## Official References

- <https://pypi.org/project/msgspec/0.21.1/>
- <https://github.com/jcrist/msgspec/tree/0.21.1>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/structs.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/constraints.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/supported-types.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/jsonschema.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/converters.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/extending.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/api.rst>
- <https://github.com/jcrist/msgspec/blob/0.21.1/docs/changelog.md>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
