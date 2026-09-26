# DTOs (`msgspec`, `MsgspecDTO`, `DataclassDTO`, `PydanticDTO`, `SQLAlchemyDTO`)

Litestar optimizes serialization and validation around `msgspec`, while supporting stdlib dataclasses, Pydantic models, and SQLAlchemy ORM models through first-party DTO factories.

## Match-Your-Stack DTO Selection

| Scenario | Choice | Import |
| --- | --- | --- |
| Greenfield API schemas & hot paths | `msgspec.Struct` (`rename="camel"`) | `import msgspec` |
| Shape/subset an existing `msgspec.Struct` | `MsgspecDTO[T]` | `from litestar.dto import DTOConfig, MsgspecDTO` |
| Shape/subset a stdlib `@dataclass` | `DataclassDTO[T]` | `from litestar.dto import DataclassDTO, DTOConfig` |
| Pydantic-led project (`BaseModel`) | `PydanticDTO[T]` + `PydanticPlugin` | `from litestar.plugins.pydantic import PydanticDTO, PydanticPlugin` |
| Expose/subset a SQLAlchemy ORM model | `SQLAlchemyDTO[T]` + `SQLAlchemyDTOConfig` | `from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig` |

> **Import rule:** Always import `SQLAlchemyDTO` and `SQLAlchemyDTOConfig` from `advanced_alchemy.extensions.litestar` (or `advanced_alchemy.extensions.litestar.dto`). Importing from `litestar.plugins.sqlalchemy` is deprecated since Litestar 2.18.0 and removed in 3.0.0.

## Pattern: `CamelizedBaseStruct` (`msgspec` Stack)

Canonical `msgspec` apps define a shared base in `app/lib/schema.py` so every schema serializes as `camelCase` on the wire while staying `snake_case` in Python:

```python
import msgspec


class CamelizedBaseStruct(msgspec.Struct, rename="camel"):
    """Base Struct: snake_case in Python, camelCase on the wire."""

    def to_dict(self) -> dict[str, object]:
        return msgspec.to_builtins(self)
```

Subclasses inherit `rename="camel"`:

```python
from datetime import datetime
from uuid import UUID

import msgspec
from app.lib.schema import CamelizedBaseStruct


class User(CamelizedBaseStruct):
    id: UUID
    name: str
    email: str
    is_active: bool = True
    created_at: datetime


class LegacyUser(CamelizedBaseStruct):
    id: UUID
    legacy_id: str = msgspec.field(name="legacy_user_id")
```

## DTO Factories — `MsgspecDTO` and `DataclassDTO`

When a single domain class backs multiple endpoints (read, write, patch), wrap it in `MsgspecDTO[T]` or `DataclassDTO[T]` with `DTOConfig`. Avoid `from __future__ import annotations` in modules defining runtime-introspected DTO models if forward references are passed to `AbstractDTO[...]`.

```python
from dataclasses import dataclass

from litestar import get
from litestar.dto import DataclassDTO, DTOConfig
from litestar.params import FromPath


@dataclass
class User:
    id: int
    name: str
    password_hash: str

    @property
    def display_label(self) -> str:
        return f"{self.name} (#{self.id})"


class UserReadDTO(DataclassDTO[User]):
    config = DTOConfig(
        exclude={"password_hash"},
        rename_fields={"name": "full_name"},
        rename_strategy="camel",
    )


@get("/users/{user_id:int}", return_dto=UserReadDTO)
async def get_user(user_id: FromPath[int]) -> User:
    return await fetch_user(user_id)
```

Both `MsgspecDTO` and `DataclassDTO` automatically include public `@property` getters on the model as `Mark.READ_ONLY` fields (properties starting with `_` are ignored).

### Inline `Annotated` Configuration and Custom Schema Names

Attach `DTOConfig` either on a subclass (`config = DTOConfig(...)`) or inline via `Annotated`, and override the OpenAPI component schema name with `__schema_name__`:

```python
from typing import Annotated, ClassVar

from litestar.dto import DTOConfig, MsgspecDTO

UserSummaryDTO = MsgspecDTO[Annotated[User, DTOConfig(include={"id", "name"}, rename_strategy="camel")]]


class PublicUserDTO(MsgspecDTO[User]):
    __schema_name__: ClassVar[str | None] = "PublicUser"
    config = DTOConfig(exclude={"password_hash"}, rename_strategy="camel")
```

### Layer Inheritance (`dto` and `return_dto`)

Declare `dto` (request body DTO) and `return_dto` (response DTO) on `Litestar`, `Router`, `Controller`, or individual route handlers (`@get`, `@post`, `@patch`). If `return_dto` is omitted on a layer where `dto` is set, Litestar uses `dto` for both directions unless `return_dto=None` is explicitly passed. Pass `dto=None` or `return_dto=None` on a route handler to disable a parent controller/router DTO.

## `DTOConfig` Knobs

`DTOConfig` (`from litestar.dto import DTOConfig`) is a frozen dataclass:

| Knob | Type & Default | Purpose |
| --- | --- | --- |
| `exclude` | `AbstractSet[str] = set()` | Drop fields from transfer. Supports dot-separated nested paths (e.g. `"address.street"`). Mutually exclusive with `include`. |
| `include` | `AbstractSet[str] = set()` | Whitelist fields for transfer (supports dot-separated nested paths). Mutually exclusive with `exclude` (setting both raises `ImproperlyConfiguredException`). |
| `rename_fields` | `dict[str, str] = {}` | Explicit field rename mapping. Fields in `rename_fields` bypass `rename_strategy`. |
| `rename_strategy` | `RenameStrategy \| None = None` | Bulk rename: `"camel"`, `"pascal"`, `"upper"`, `"lower"`, or a `Callable[[str], str]`. |
| `max_nested_depth` | `int = 1` | Maximum recursion depth for nested model fields. |
| `partial` | `bool = False` | Makes all fields optional (`UNSET` default) for `PATCH` endpoints. |
| `underscore_fields_private` | `bool = True` | Automatically marks fields starting with `_` as `Mark.PRIVATE`. |
| `forbid_unknown_fields` | `bool = False` | Raises `ValidationException` when unknown keys appear in incoming payloads. |
| `experimental_codegen_backend` | `bool \| None = None` | Controls the codegen backend (`DTOCodegenBackend` runs unless set to `False`). |

## Field Marking — `DTOField`, `dto_field`, and `Mark`

Mark fields directly on the model so every DTO derived from that model enforces read/write visibility automatically:

```python
from dataclasses import dataclass, field
from typing import Annotated

import msgspec
from litestar.dto import DTOField, Mark, dto_field
```

| Mark | Value | Inbound (`dto`) | Outbound (`return_dto`) | Typical Use |
| --- | --- | --- | --- | --- |
| `Mark.READ_ONLY` | `"read-only"` | Excluded | Included | `id`, `created_at`, `updated_at`, computed properties |
| `Mark.WRITE_ONLY` | `"write-only"` | Included | Excluded | `password`, one-time tokens, confirmation fields |
| `Mark.PRIVATE` | `"private"` | Excluded | Excluded | `password_hash`, internal state, audit secrets |

### Marking Styles by Model Type

- **`Annotated[T, DTOField(mark=...)]`** — works everywhere (`msgspec.Struct`, `@dataclass`, Pydantic `BaseModel`, SQLAlchemy `Mapped[...]`):

```python
class Account(msgspec.Struct):
    id: Annotated[int, DTOField(mark=Mark.READ_ONLY)]
    email: str
    password: Annotated[str, DTOField(mark=Mark.WRITE_ONLY)]
    password_hash: Annotated[str, DTOField(mark=Mark.PRIVATE)] = ""
```

- **`dto_field(mark=...)` metadata dict** (`{"__dto__": DTOField(mark=Mark(mark))}`) — used with `@dataclass` `field(metadata=...)` or SQLAlchemy `mapped_column(info=...)` / `relationship(info=...)`. Metadata mapping takes precedence over `Annotated`:

```python
@dataclass
class AccountRecord:
    id: int = field(metadata=dto_field("read-only"))
    email: str = ""
    password_hash: str = field(default="", metadata=dto_field(Mark.PRIVATE))
```

> **Pydantic deprecation:** Declaring `DTOField` via Pydantic's `Field(extra=dto_field(...))` or `json_schema_extra` emits a `DeprecationWarning` and is removed in Litestar 3.0. Always use `Annotated[T, DTOField(mark="read-only")]` on Pydantic fields.

## `DTOData[T]` — Validated Payload Helper

When required fields are excluded from a write DTO (e.g. server-generated `id` or `password_hash`) or `partial=True` is set for a `PATCH` route, Litestar cannot instantiate `T` directly from client input. Annotate the `data` parameter as `DTOData[T]`:

```python
from uuid import UUID, uuid4

from litestar import patch, post
from litestar.dto import DTOConfig, DTOData, MsgspecDTO
from litestar.params import FromPath


class UserWriteDTO(MsgspecDTO[User]):
    config = DTOConfig(exclude={"id", "created_at"}, forbid_unknown_fields=True)


class UserPatchDTO(MsgspecDTO[User]):
    config = DTOConfig(exclude={"id", "created_at"}, partial=True, forbid_unknown_fields=True)


@post("/users", dto=UserWriteDTO, return_dto=UserReadDTO)
async def create_user(data: DTOData[User]) -> User:
    return data.create_instance(id=uuid4(), address__country="US")


@patch("/users/{user_id:uuid}", dto=UserPatchDTO, return_dto=UserReadDTO)
async def patch_user(user_id: FromPath[UUID], data: DTOData[User]) -> User:
    user = await fetch_user(user_id)
    return data.update_instance(user)
```

| `DTOData[T]` Method | Behavior |
| --- | --- |
| `data.create_instance(**kwargs) -> T` | Instantiates `T` from validated payload merged with `**kwargs` (kwargs take precedence; supports `nested__field=value` double-underscore paths). |
| `data.update_instance(instance: T, **kwargs) -> T` | Mutates `instance` in-place via `setattr` using only the fields present in the validated payload (plus `**kwargs`) and returns `instance`. |
| `data.as_builtins() -> Any` | Returns the validated payload as plain Python `dict` / builtins (ideal for passing to `service.create(data.as_builtins())` or `service.update(data.as_builtins(), item_id=...)`). |

## `SQLAlchemyDTO` and `SQLAlchemyDTOConfig` (`advanced-alchemy`)

Import `SQLAlchemyDTO` and `SQLAlchemyDTOConfig` from `advanced_alchemy.extensions.litestar`:

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig
from litestar.dto import dto_field
from sqlalchemy.orm import Mapped, mapped_column


class UserModel(UUIDAuditBase):
    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str | None] = mapped_column(default=None)
    password_hash: Mapped[str] = mapped_column(info=dto_field("private"))


class UserModelReadDTO(SQLAlchemyDTO[UserModel]):
    config = SQLAlchemyDTOConfig(
        rename_strategy="camel",
        max_nested_depth=1,
    )


class UserModelWriteDTO(SQLAlchemyDTO[UserModel]):
    config = SQLAlchemyDTOConfig(
        exclude={UserModel.id, UserModel.created_at, UserModel.updated_at},
        rename_strategy="camel",
        forbid_unknown_fields=True,
    )
```

Key `SQLAlchemyDTO` and `SQLAlchemyDTOConfig` capabilities:

- **`InstrumentedAttribute` support:** `exclude`, `include`, and `rename_fields` accept either `str` names (including dot-separated paths like `"addresses.zip_code"`) or SQLAlchemy `InstrumentedAttribute` descriptors directly (e.g. `exclude={UserModel.created_at}`).
- **`include_implicit_fields: bool | Literal["hybrid-only"] = True`:**
  - `True` (default): includes columns, relationships, composites, `AssociationProxy` (marked `Mark.READ_ONLY`), `@hybrid_property` (getter `Mark.READ_ONLY`, setter `Mark.WRITE_ONLY`), and `@property` / `@cached_property` (`Mark.READ_ONLY`).
  - `False`: excludes all descriptors not explicitly annotated with `Mapped[...]` (unless marked with `Mark.READ_ONLY` or `Mark.WRITE_ONLY`).
  - `"hybrid-only"`: excludes unannotated implicit fields except `@hybrid_property`.
- **Nullable relationship detection:** `MANYTOONE` relationships with all-nullable local FK columns and inverse one-to-one (`ONETOMANY` with `uselist=False`) relationships are automatically typed as optional (`T | None = None`).

## `PydanticDTO` and `PydanticPlugin` (Pydantic Stack)

When a project is standardized on Pydantic v2, use `PydanticDTO` and `PydanticPlugin`:

```python
from typing import Annotated

from litestar import Litestar, post
from litestar.dto import DTOConfig, DTOField, Mark
from litestar.plugins.pydantic import PydanticDTO, PydanticPlugin
from pydantic import BaseModel, ConfigDict


class CustomerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[int, DTOField(mark=Mark.READ_ONLY)]
    email: str
    internal_notes: Annotated[str, DTOField(mark=Mark.PRIVATE)] = ""


class CustomerDTO(PydanticDTO[CustomerModel]):
    config = DTOConfig(rename_strategy="camel")


@post("/customers", dto=CustomerDTO, return_dto=CustomerDTO)
async def create_customer(data: CustomerModel) -> CustomerModel:
    return data


app = Litestar(
    route_handlers=[create_customer],
    plugins=[PydanticPlugin(prefer_alias=True, validate_strict=False)],
)
```

- `PydanticDTO` converts Pydantic `ValidationError` into Litestar's `ValidationException` (`400`) with structured `extra` error details.
- If a Pydantic model sets `model_config = ConfigDict(extra="forbid")` (or `Config.extra = "forbid"` in v1), `PydanticDTO` automatically enables `forbid_unknown_fields=True` on its `DTOConfig`.
- `PydanticPlugin` configures app-wide Pydantic serialization and validation (`prefer_alias`, `validate_strict`, `round_trip`, `exclude_none`, `exclude_unset`, `exclude_defaults`, `include`, `exclude`).

## OpenAPI Required vs Nullable

OpenAPI requiredness follows the Python default, not the presence of `None` in the union:

```python
import msgspec


class UserPatch(msgspec.Struct):
    display_name: str | None
    biography: str | None = None
```

- `display_name` is **required and nullable**. Clients must include `"display_name"` in the payload, and its value may be `null`.
- `biography` is **optional and nullable**. Clients may omit `"biography"` because it has a default (`None`).

Litestar 2.24 ensures required nullable fields remain in the OpenAPI `required` array across `msgspec.Struct`, dataclasses, `attrs` classes, and Pydantic models.

## Request Body Markers (Litestar ≥ 2.23)

Declare request body media types with the generic body markers from `litestar.params` instead of `Annotated[T, Body(media_type=RequestEncodingType.…)]`:

```python
from typing import Annotated

from litestar import post
from litestar.params import Body, JSONBody, MsgPackBody, MultipartBody, URLEncodedBody


@post("/orders")
async def create_order(data: JSONBody[OrderCreate]) -> Order: ...


@post("/events")
async def ingest_event(data: MsgPackBody[EventPayload]) -> None: ...


@post("/upload")
async def upload(data: MultipartBody[UploadForm]) -> Receipt: ...


@post("/login")
async def login(data: URLEncodedBody[Credentials]) -> Token: ...


@post("/bulk-upload")
async def bulk_upload(
    data: Annotated[
        UploadForm,
        Body(
            media_type="multipart/form-data",
            multipart_form_part_limit=50,
            schema_extra={"examples": [{"filename": "report.csv"}]},
            schema_component_key="BulkUploadPayload",
        ),
    ],
) -> Receipt: ...
```

| Marker | Media Type | Old Form |
| --- | --- | --- |
| `JSONBody[T]` | `application/json` (default) | `Annotated[T, Body()]` |
| `MsgPackBody[T]` | `application/x-msgpack` | `Annotated[T, Body(media_type=RequestEncodingType.MESSAGEPACK)]` |
| `MultipartBody[T]` | `multipart/form-data` | `Annotated[T, Body(media_type=RequestEncodingType.MULTI_PART)]` |
| `URLEncodedBody[T]` | `application/x-www-form-urlencoded` | `Annotated[T, Body(media_type=RequestEncodingType.URL_ENCODED)]` |

Use `Annotated[T, Body(...)]` when you need body constraints or OpenAPI metadata (`multipart_form_part_limit`, `description`, `title`, `examples`, `schema_extra`, `schema_component_key`).

## Cross-References

- OpenAPI configuration, UI render plugins, `ResponseSpec`, `Operation`, and security schemes: [openapi.md](openapi.md)
- `to_schema` in repository services converts ORM rows to DTOs: [services-and-repos.md](services-and-repos.md)
- Pagination wraps DTOs in `OffsetPagination[T]`: [filters-and-pagination.md](filters-and-pagination.md)
- Deep `msgspec.Struct` modeling: [msgspec](../../msgspec/SKILL.md)

## Tagged Source

- [2.24 DTO implementation](https://github.com/litestar-org/litestar/tree/v2.24.0/litestar/dto)
- [2.24 nullable-required changelog](https://github.com/litestar-org/litestar/blob/v2.24.0/docs/release-notes/changelog.rst)
- [Advanced Alchemy 1.11 Litestar DTO](https://github.com/litestar-org/advanced-alchemy/blob/v1.11.0/advanced_alchemy/extensions/litestar/dto.py)
