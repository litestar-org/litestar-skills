# Path Parameters, Request Parameters, Bodies, and Reserved Kwargs

## Path Parameter Types (`{param_name:type}`)

Every path parameter in a route string must declare `{param_name:type}` with a unique `param_name` per route. Omitting `:type` (`{id}` instead of `{id:int}`) raises `ImproperlyConfiguredException` at route registration:

| Path Type Token | Parsed Python Type | Example |
| --- | --- | --- |
| `str` | `str` | `/users/{username:str}` |
| `int` | `int` | `/items/{item_id:int}` |
| `float` | `float` | `/coords/{lat:float}` |
| `uuid` | `uuid.UUID` | `/tasks/{task_id:uuid}` |
| `decimal` | `decimal.Decimal` | `/prices/{amount:decimal}` |
| `date` | `datetime.date` | `/reports/{day:date}` |
| `datetime` | `datetime.datetime` | `/events/{at:datetime}` |
| `time` | `datetime.time` | `/slots/{start:time}` |
| `timedelta` | `datetime.timedelta` | `/windows/{span:timedelta}` |
| `path` | `pathlib.Path` | `/files/{file_path:path}` |

## Request Parameter Declarations (`litestar.params`)

Request parameter sources are explicit in Litestar 2.25:

| Need | Declaration |
| --- | --- |
| Unconstrained path / query / header / cookie | `FromPath[T]` / `FromQuery[T]` / `FromHeader[T]` / `FromCookie[T]` |
| Constraints, OpenAPI metadata, or wire alias (`name=`) | `Annotated[T, PathParameter(...)]` / `QueryParameter(...)` / `HeaderParameter(...)` / `CookieParameter(...)` |
| Default value | Put `= value` on the function parameter |
| Shared parameter on `Controller` / `Router` / `Litestar` | `parameters={"org_id": PathParameter(annotation=UUID, description="Org ID")}` |

```python
from typing import Annotated
from uuid import UUID

from litestar import get
from litestar.params import (
    FromCookie,
    HeaderParameter,
    PathParameter,
    QueryParameter,
)


@get("/orgs/{org_id:uuid}/items")
async def list_items(
    org_id: Annotated[UUID, PathParameter(description="Organization UUID")],
    api_key: Annotated[str, HeaderParameter(name="X-API-Key", min_length=16)],
    limit: Annotated[int, QueryParameter(ge=1, le=100)] = 20,
    page_token: Annotated[str | None, QueryParameter(name="pageToken")] = None,
    session_id: FromCookie[str | None] = None,
) -> list[Item]:
    _ = (api_key, session_id)
    return await search_items(org_id=org_id, limit=limit, page_token=page_token)
```

`PathParameter`, `QueryParameter`, `HeaderParameter`, and `CookieParameter` (subclasses of `ParameterKwarg` / `KwargDefinition`) accept:

- **Wire naming & presence**: `name: str | None = None` (wire name / alias), `required: bool | None = None`, `default: Any = Empty`, `annotation: Any = Empty` (used in layered `parameters={...}` maps).
- **Numeric constraints**: `gt`, `ge`, `lt`, `le`, `multiple_of`.
- **String / bytes constraints**: `min_length`, `max_length`, `pattern`, `lower_case`, `upper_case`, `format`, `content_encoding`.
- **Collection & value constraints**: `min_items`, `max_items`, `const`, `enum`.
- **OpenAPI schema metadata**: `title`, `description`, `examples`, `external_docs`, `read_only`, `schema_extra`, `schema_component_key`, `include_in_schema: bool = True`.

> **Deprecation rules (2.25 -> 3.0)**: Inferred parameters (no marker), default-value style (`field: T = Parameter(...)`), `Annotated[T, Parameter(...)]`, and `Parameter(query=...|header=...|cookie=...)` emit `LitestarDeprecationWarning` / `DeprecationWarning` and are removed in 3.0. Always use `From*` or `*Parameter(name=...)` inside `Annotated`.

## Request Body Declarations (`data`, `Body`, and `body: RawBody`)

Litestar binds parsed request payloads to the `data` parameter (which must carry a `BodyKwarg` marker in Litestar 2.25+) and raw payload bytes to `body: RawBody` (`from litestar.params import RawBody`):

| Payload Encoding | Declaration |
| --- | --- |
| JSON (`application/json`, default) | `data: JSONBody[MyDTO]` or `data: RequestBody[MyDTO]` |
| MessagePack (`application/x-msgpack`) | `data: MsgPackBody[MyDTO]` |
| Multipart form (`multipart/form-data`) | `data: MultipartBody[UploadDTO]` |
| URL-encoded form (`application/x-www-form-urlencoded`) | `data: URLEncodedBody[LoginDTO]` |
| Constrained body, custom `media_type`, or `multipart_form_part_limit` | `data: Annotated[MyDTO, Body(media_type=..., multipart_form_part_limit=10, title=..., description=..., examples=..., schema_extra=..., schema_component_key=...)]` |
| Raw unparsed request bytes | `body: RawBody` (`RawBody = NewType("RawBody", bytes)`; declaring `body: bytes` emits `LitestarDeprecationWarning`, and any non-`bytes` type raises `ImproperlyConfiguredException`) |

`Body(...)` accepts all `KwargDefinition` constraint and OpenAPI fields (`gt`, `ge`, `lt`, `le`, `multiple_of`, `min_items`, `max_items`, `min_length`, `max_length`, `pattern`, `const`, `title`, `description`, `examples`, `external_docs`, `content_encoding`, `schema_extra`, `schema_component_key`) plus `media_type: str | RequestEncodingType = RequestEncodingType.JSON` and `multipart_form_part_limit: int | None = None`.

## Reserved Kwargs & Ambiguity Validation

Litestar reserves 9 parameter names (`RESERVED_KWARGS`) and requires explicit Litestar 2.25+ types when they are declared on route handlers or dependencies:

| Reserved Kwarg | Required Type Annotation (2.25+) | Import | Route Handler Alternative |
| --- | --- | --- | --- |
| `data` | `JSONBody[T]`, `RequestBody[T]`, `MsgPackBody[T]`, `MultipartBody[T]`, `URLEncodedBody[T]`, or `Annotated[T, Body(...)]` | `litestar.params` | Always annotate `data` with a body marker (even when `dto=...` is configured on the route/controller, e.g. `data: JSONBody[DTOData[User]]`). |
| `body` | `RawBody` | `litestar.params` | `await request.body()` |
| `request` | `Request` (or `ASGIConnection`) | `litestar` / `litestar.connection` | HTTP handlers and dependencies only. |
| `socket` | `WebSocket` (or `ASGIConnection`) | `litestar` / `litestar.connection` | WebSocket handlers and dependencies only. |
| `state` | `State` or `ImmutableState` | `litestar.datastructures` | `request.app.state` |
| `headers` | `Headers` | `litestar.datastructures` | Prefer `request.headers` (or `socket.headers`) inside route handlers. |
| `query` | `QueryParams` (`NewType("QueryParams", MultiDict[Any])`) | `litestar.params` | Prefer `request.query_params` (or `socket.query_params`) inside route handlers, or `FromQuery[T]` for individual parameters. |
| `cookies` | `RequestCookies` (`NewType("RequestCookies", dict[str, str])`) | `litestar.params` | Prefer `request.cookies` (or `socket.cookies`) inside route handlers, or `FromCookie[T]` for individual cookies. |
| `scope` | `Scope` | `litestar.types` | Prefer `request.scope` (or `socket.scope`) inside route handlers. |

- Declaring any reserved kwarg without its required type annotation emits `LitestarDeprecationWarning` in Litestar 2.25 and will stop resolving as a reserved kwarg in Litestar 3.0.
- `request`, `socket`, `scope`, `receive`, and `send` (`SKIP_VALIDATION_NAMES`) automatically bypass `SignatureModel` validation.
- **Disjoint namespace rule**: reserved kwargs cannot be used as path parameter names, aliased parameter names, or dependency keys. Path parameter names, parameter names, and dependency keys must also be mutually disjoint (`ImproperlyConfiguredException: Kwarg resolution ambiguity detected`).

## Cross-References

- Route decorators, Controllers, Routers, and layered resolution: [handlers.md](handlers.md)
- DTOs (`MsgspecDTO`, `DTOConfig`, `DTOData`) and body markers: [dtos.md](dtos.md)
- OpenAPI parameter and body schema customization (`schema_extra`, `examples`): [openapi.md](openapi.md)
- Dependency injection (`NamedDependency`, `SkipValidation`, `Provide`): [di-and-dishka.md](di-and-dishka.md)

## Tagged Source

- [2.25 parameter declarations](https://github.com/litestar-org/litestar/blob/v2.25.0/docs/usage/routing/parameters.rst)
- [2.25 explicit declarations](https://github.com/litestar-org/litestar/blob/v2.25.0/docs/topics/explicit_declarations.rst)
