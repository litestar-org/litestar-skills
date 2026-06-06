# DTOs (msgspec, OpenAPI, camelCase rename)

Litestar is heavily optimized for `msgspec`. DTOs provide data mapping, validation, and OpenAPI schema generation — all from a single Struct definition.

## Pattern: `CamelizedBaseStruct`

Canonical apps define a shared base in `app/lib/schema.py` so every DTO ships camelCase on the wire while staying snake_case in Python:

```python
import msgspec


class CamelizedBaseStruct(msgspec.Struct, rename="camel"):
    """Base Struct: snake_case in Python, camelCase on the wire."""

    def to_dict(self) -> dict:
        return msgspec.to_builtins(self)
```

Subclasses inherit the rename:

```python
from datetime import datetime
from uuid import UUID

from app.lib.schema import CamelizedBaseStruct


class User(CamelizedBaseStruct):
    id: UUID
    name: str
    email: str
    is_active: bool = True       # → "isActive"
    created_at: datetime         # → "createdAt"


class UserCreate(CamelizedBaseStruct):
    name: str
    email: str
    password: str
```

## `msgspec.field(name=...)` per-field

For finer control (e.g. matching a legacy field name), use `msgspec.field(name=...)`:

```python
import msgspec


class LegacyUser(CamelizedBaseStruct):
    id: UUID
    legacy_id: str = msgspec.field(name="legacy_user_id")
```

## DTOs from existing classes — `MsgspecDTO` / `DataclassDTO`

When you want to expose an ORM model (or any class) and shape it with `DTOConfig`:

```python
from __future__ import annotations

from dataclasses import dataclass
from litestar.dto import DataclassDTO, DTOConfig, MsgspecDTO


@dataclass
class User:
    id: int
    name: str
    password_hash: str  # sensitive


class UserReadDTO(DataclassDTO[User]):
    config = DTOConfig(
        exclude={"password_hash"},
        rename_fields={"name": "full_name"},
        rename_strategy="camel",
    )


@get("/users/{user_id:int}", return_dto=UserReadDTO)
async def get_user(user_id: int) -> User:
    return await fetch_user(user_id)
```

## `DTOConfig` Knobs

| Knob | Purpose |
| --- | --- |
| `exclude={"password_hash", ...}` | Drop fields from input/output |
| `include={"id", "name"}` | Whitelist (mutually exclusive with `exclude`) |
| `rename_fields={"name": "full_name"}` | Per-field rename |
| `rename_strategy="camel"` | Bulk rename: `camel`, `pascal`, `upper`, `lower`, or a custom callable |
| `partial=True` | All fields optional (PATCH endpoints) |
| `max_nested_depth=N` | Cap nested DTO recursion |

## msgspec vs DataclassDTO

| Use | Pick |
| --- | --- |
| API DTOs in greenfield code | `msgspec.Struct` + `CamelizedBaseStruct` |
| Wrapping legacy dataclasses / SQLAlchemy models | `DataclassDTO` / `SQLAlchemyDTO` with `DTOConfig` |
| Maximum performance (microservices, hot paths) | msgspec — Rust-backed encode/decode |

## Cross-references

- `to_schema` in repository services automatically converts ORM → DTO: [services.md](../../litestar-data-services/references/services.md)
- Pagination wraps DTOs in `OffsetPagination[T]`: [pagination.md](../../litestar-data-services/references/pagination.md)
- Sibling skill for msgspec deep dive: `../../msgspec/SKILL.md` (if present)
