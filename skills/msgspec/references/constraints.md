# msgspec Meta Constraints Reference

`Meta` constraints are applied via `Annotated[Type, Meta(...)]`. They are evaluated at decode/convert time with zero runtime overhead — no validation code runs on already-valid data.

## Import

```python
from typing import Annotated
from msgspec import Meta
```

---

## Numeric Constraints

Applies to `int`, `float`, `Decimal`.

| Parameter | Description | Example |
| --- | --- | --- |
| `gt` | Greater than (exclusive) | `Meta(gt=0)` → value > 0 |
| `ge` | Greater than or equal (inclusive) | `Meta(ge=0)` → value >= 0 |
| `lt` | Less than (exclusive) | `Meta(lt=100)` → value < 100 |
| `le` | Less than or equal (inclusive) | `Meta(le=100)` → value <= 100 |
| `multiple_of` | Value must be a multiple of N | `Meta(multiple_of=5)` |

```python
import msgspec
from typing import Annotated
from msgspec import Meta

PositiveInt = Annotated[int, Meta(gt=0)]
NonNegInt = Annotated[int, Meta(ge=0)]
Probability = Annotated[float, Meta(ge=0.0, le=1.0)]
Percentage = Annotated[float, Meta(ge=0.0, le=100.0)]
PriceCents = Annotated[int, Meta(ge=0, multiple_of=1)]
Port = Annotated[int, Meta(ge=1, le=65535)]
Rating = Annotated[int, Meta(ge=1, le=5)]

class Product(msgspec.Struct, kw_only=True):
    id: PositiveInt
    price_cents: PriceCents
    stock: NonNegInt
    rating: Rating = 3
```

---

## String Constraints

| Parameter | Description | Example |
| --- | --- | --- |
| `min_length` | Minimum char count | `Meta(min_length=1)` |
| `max_length` | Maximum char count | `Meta(max_length=255)` |
| `pattern` | Regex pattern | `Meta(pattern=r"^\d{4}$")` |

```python
NonEmptyStr = Annotated[str, Meta(min_length=1)]
ShortStr = Annotated[str, Meta(min_length=1, max_length=100)]
LongText = Annotated[str, Meta(max_length=10_000)]
EmailStr = Annotated[str, Meta(pattern=r"^[^@]+@[^@]+\.[^@]+$")]
Slug = Annotated[str, Meta(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=64)]
SKU = Annotated[str, Meta(pattern=r"^[A-Z]{2}-\d{4}$")]
UUIDStr = Annotated[str, Meta(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]

class Article(msgspec.Struct, kw_only=True):
    slug: Slug
    title: ShortStr
    body: LongText
    author_email: EmailStr
```

---

## Bytes Constraints

| Parameter | Description |
| --- | --- |
| `min_length` | Minimum byte count |
| `max_length` | Maximum byte count |

```python
Token = Annotated[bytes, Meta(min_length=32, max_length=32)]
Blob = Annotated[bytes, Meta(max_length=65536)]

class SecurePayload(msgspec.Struct):
    token: Token
    data: Blob
```

---

## Collection Constraints

Applies to `list`, `tuple`, `set`, `frozenset`, `dict`.

| Parameter | Description |
| --- | --- |
| `min_length` | Minimum elements |
| `max_length` | Maximum elements |

```python
NonEmptyList = Annotated[list[str], Meta(min_length=1)]
Tags = Annotated[list[str], Meta(min_length=0, max_length=20)]
NonEmptyDict = Annotated[dict[str, int], Meta(min_length=1)]
```

---

## OpenAPI / JSON Schema Metadata

| Parameter | Description |
| --- | --- |
| `title` | Human-readable field title |
| `description` | Field description for docs |
| `examples` | Example values |
| `extra_json_schema` | Raw dict merged into JSON Schema output |

```python
UserId = Annotated[
    int,
    Meta(
        gt=0,
        title="User ID",
        description="Unique identifier for the user",
        examples=[1, 42, 9999],
    ),
]

ISODate = Annotated[
    str,
    Meta(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        extra_json_schema={"format": "date"},
    ),
]
```

---

## Combining Constraints

```python
ProductCode = Annotated[
    str,
    Meta(
        min_length=3, max_length=20,
        pattern=r"^[A-Z0-9-]+$",
        title="Product Code",
        examples=["ABC-123", "XYZ-999"],
    ),
]

Latitude = Annotated[
    float,
    Meta(
        ge=-90.0, le=90.0,
        title="Latitude",
        extra_json_schema={"format": "double"},
    ),
]

Longitude = Annotated[
    float,
    Meta(
        ge=-180.0, le=180.0,
        title="Longitude",
        extra_json_schema={"format": "double"},
    ),
]

class Coordinate(msgspec.Struct, frozen=True, gc=False):
    lat: Latitude
    lon: Longitude
```

---

## Validation Errors

```python
import msgspec

Price = Annotated[float, Meta(gt=0.0)]

class Item(msgspec.Struct):
    price: Price

try:
    msgspec.json.decode(b'{"price": -1.0}', type=Item)
except msgspec.ValidationError as e:
    print(e)
    # Expected `float` satisfying gt=0.0 - at `$.price`
```

Errors include the JSON path to the offending field — suitable for direct API client surfacing.

---

## Reusable Constraint Aliases (Recommended)

Define a `types.py` or `constraints.py` with shared aliases:

```python
# myapp/types.py
from typing import Annotated
from msgspec import Meta

PositiveInt = Annotated[int, Meta(gt=0)]
NonNegInt   = Annotated[int, Meta(ge=0)]
Port        = Annotated[int, Meta(ge=1, le=65535)]
Rating      = Annotated[int, Meta(ge=1, le=5)]

Probability  = Annotated[float, Meta(ge=0.0, le=1.0)]
Percentage   = Annotated[float, Meta(ge=0.0, le=100.0)]
PriceCents   = Annotated[int, Meta(ge=0, multiple_of=1)]

NonEmptyStr  = Annotated[str, Meta(min_length=1)]
ShortStr     = Annotated[str, Meta(min_length=1, max_length=255)]
Slug         = Annotated[str, Meta(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=64)]

NonEmptyList = Annotated[list, Meta(min_length=1)]
```
