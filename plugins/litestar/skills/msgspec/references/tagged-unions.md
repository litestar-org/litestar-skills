# msgspec Tagged Union Patterns

Tagged unions (discriminated unions) let msgspec select the correct Struct type during decoding based on a tag field in the payload. They replace manual `isinstance` dispatch and are faster than runtime type inspection.

## How It Works

When a union contains multiple Structs that all declare a `tag`, msgspec reads the tag field from the incoming payload and routes to the matching Struct class. Tag matching happens before field validation.

---

## Default Tags (Class Name as Tag)

`tag=True` ⇒ class name is the tag value, default tag field is `"type"`.

```python
import msgspec

class Dog(msgspec.Struct, tag=True):
    name: str
    breed: str

class Cat(msgspec.Struct, tag=True):
    name: str
    indoor: bool

Animal = Dog | Cat

dog = Dog(name="Rex", breed="Lab")
data = msgspec.json.encode(dog)
# b'{"type":"Dog","name":"Rex","breed":"Lab"}'

animal = msgspec.json.decode(b'{"type":"Dog","name":"Rex","breed":"Lab"}', type=Animal)
assert isinstance(animal, Dog)
```

---

## Custom Tag Values

```python
class CreateEvent(msgspec.Struct, tag="create"):
    resource_id: int
    created_by: str

class UpdateEvent(msgspec.Struct, tag="update"):
    resource_id: int
    updated_by: str
    changes: dict[str, object]

class DeleteEvent(msgspec.Struct, tag="delete"):
    resource_id: int
    deleted_by: str
    soft: bool = True

Event = CreateEvent | UpdateEvent | DeleteEvent
```

---

## Custom Tag Field Name

`tag_field="..."` changes the discriminator field. All variants in a union must share the same `tag_field`.

```python
class V1Request(msgspec.Struct, tag="v1", tag_field="version", kw_only=True):
    payload: str

class V2Request(msgspec.Struct, tag="v2", tag_field="version", kw_only=True):
    payload: str
    metadata: dict[str, str] = {}

Request = V1Request | V2Request
```

---

## Integer Tags

Tags can be integers (binary protocols, compact representations).

```python
class PingMessage(msgspec.Struct, tag=1):
    seq: int

class PongMessage(msgspec.Struct, tag=2):
    seq: int

Message = PingMessage | PongMessage
```

---

## Nested Unions

```python
class TextContent(msgspec.Struct, tag="text"):
    text: str

class ImageContent(msgspec.Struct, tag="image"):
    url: str
    alt: str | None = None

Content = TextContent | ImageContent

class Post(msgspec.Struct, kw_only=True):
    id: int
    author: str
    content: Content   # union — dispatched at decode
```

---

## Pattern: API Versioning

```python
class CreateUserV1(msgspec.Struct, tag="v1", tag_field="api_version", kw_only=True):
    username: str
    email: str

class CreateUserV2(msgspec.Struct, tag="v2", tag_field="api_version", kw_only=True):
    username: str
    email: str
    display_name: str | None = None
    locale: str = "en"

CreateUserRequest = CreateUserV1 | CreateUserV2
_decoder = msgspec.json.Decoder(CreateUserRequest)

async def handle_create_user(body: bytes) -> dict:
    request = _decoder.decode(body)
    match request:
        case CreateUserV1(username=u, email=e):
            return {"version": 1, "username": u, "email": e}
        case CreateUserV2(username=u, email=e, display_name=d, locale=l):
            return {"version": 2, "username": u, "email": e, "display_name": d, "locale": l}
```

---

## Pattern: Event Bus

```python
import uuid
from datetime import datetime

class OrderPlaced(msgspec.Struct, tag="order.placed", tag_field="event_type", kw_only=True, gc=False):
    event_id: uuid.UUID
    order_id: uuid.UUID
    user_id: int
    total: float
    placed_at: datetime

class OrderShipped(msgspec.Struct, tag="order.shipped", tag_field="event_type", kw_only=True, gc=False):
    event_id: uuid.UUID
    order_id: uuid.UUID
    tracking_number: str
    shipped_at: datetime

OrderEvent = OrderPlaced | OrderShipped
```

---

## Pattern: Command Dispatch

```python
class SendEmailCommand(msgspec.Struct, tag="send_email", kw_only=True):
    to: str
    subject: str
    body: str

class GenerateReportCommand(msgspec.Struct, tag="generate_report", kw_only=True):
    report_type: str
    filters: dict[str, object] = {}
    requested_by: int

Command = SendEmailCommand | GenerateReportCommand
_decoder = msgspec.json.Decoder(Command)

async def dispatch_command(payload: bytes) -> None:
    command = _decoder.decode(payload)
    match command:
        case SendEmailCommand(to=addr, subject=subj):
            await send_email(addr, subj, command.body)
        case GenerateReportCommand(report_type=rtype):
            await generate_report(rtype, command.filters)
```

---

## Common Mistakes

### Mixed `tag_field` across variants — fails at decode

```python
# WRONG
class A(msgspec.Struct, tag="a", tag_field="type"): ...
class B(msgspec.Struct, tag="b", tag_field="kind"): ...
AB = A | B  # decode error

# CORRECT
class A(msgspec.Struct, tag="a", tag_field="kind"): ...
class B(msgspec.Struct, tag="b", tag_field="kind"): ...
```

### Duplicate tag values — ambiguous

```python
# WRONG
class A(msgspec.Struct, tag="same"): ...
class B(msgspec.Struct, tag="same"): ...

# CORRECT
class A(msgspec.Struct, tag="type_a"): ...
class B(msgspec.Struct, tag="type_b"): ...
```

### Without `tag=`, union decoding falls back to structural matching (slower, error-prone)

Always use `tag=` on Struct variants in polymorphic unions.
