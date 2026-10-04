# OpenAPI Configuration, Render Plugins & Security Reference

Deep-dive patterns for configuring `OpenAPIConfig`, selecting UI and raw-spec `render_plugins`, customizing operation and response schemas (`ResponseSpec`, `Operation`, `raises`, `schema_extra`), and wiring OpenAPI security schemes in Litestar.

Related references:

- [`dtos.md`](dtos.md) — `MsgspecDTO`, `DataclassDTO`, `PydanticDTO`, `SQLAlchemyDTO`, `DTOConfig`, `dto_field`, `Mark`, and `DTOData`
- [`SKILL.md`](../SKILL.md) — workflow, guardrails, validation, and complete end-to-end example
- [`../../litestar-styleguide/SKILL.md`](../../litestar-styleguide/SKILL.md) — shared styleguide baseline

---

## `OpenAPIConfig` Options

Import `OpenAPIConfig` from `litestar.openapi` (`from litestar.openapi import OpenAPIConfig`) and pass it to `Litestar(openapi_config=...)`. Litestar enables `OpenAPIPlugin` automatically whenever `openapi_config` is not `None`.

| Option | Type / Default | Purpose |
| --- | --- | --- |
| `title` | `str` (required) | API title in the `info` block. |
| `version` | `str` (required) | API version string in the `info` block. |
| `path` | `str \| None = None` | Base path for OpenAPI docs and raw specs (defaults to `"/schema"` when `openapi_router` is not supplied). |
| `render_plugins` | `Sequence[OpenAPIRenderPlugin] = ()` | UI and raw-spec plugins to mount under `path`. Defaults to `(ScalarRenderPlugin(),)` when empty and `openapi_controller` is not set. |
| `openapi_router` | `Router \| None = None` | Optional custom `Router` for hosting OpenAPI endpoints (attach `guards`, `middleware`, or custom `path` here; when set, `OpenAPIConfig.path` is ignored). |
| `create_examples` | `bool = False` | Auto-generate deterministic schema examples via Polyfactory (`random_seed: int = 10`). |
| `random_seed` | `int = 10` | Random seed used by Polyfactory when `create_examples=True`. |
| `use_handler_docstrings` | `bool = False` | Use route handler docstrings as the OpenAPI operation `description` when `description=` is not set explicitly on the decorator. |
| `operation_id_creator` | `OperationIDCreator = default_operation_id_creator` | Callable `(HTTPRouteHandler, HttpMethod, list[str \| PathParameterDefinition]) -> str` that generates unique `operationId` values. |
| `components` | `Components \| list[Components] = Components()` | Reusable OpenAPI components (`schemas`, `security_schemes`, `headers`, `parameters`, `responses`, `examples`). Lists are merged automatically. |
| `security` | `list[SecurityRequirement] \| None = None` | Global security requirements (`list[dict[str, list[str]]]`), e.g. `[{"BearerAuth": []}]`. |
| `servers` | `list[Server] = [Server(url="/")]` | Target server definitions (`from litestar.openapi.spec import Server`). |
| `tags` | `list[Tag] \| None = None` | Tag metadata (`from litestar.openapi.spec import Tag`). |
| `webhooks` | `dict[str, PathItem \| Reference] \| None = None` | OpenAPI 3.1 webhook definitions. |
| `summary` / `description` / `terms_of_service` | `str \| None = None` | Additional `info` fields. |
| `contact` / `license` / `external_docs` | `Contact \| License \| ExternalDocumentation \| None = None` | Structured `info` and documentation metadata (`from litestar.openapi.spec import Contact, License, ExternalDocumentation`). |

---

## Render Plugins (`litestar.openapi.plugins`)

Import render plugins from `litestar.openapi.plugins`:

```python
from litestar.openapi.plugins import (
    JsonRenderPlugin,
    RapidocRenderPlugin,
    RedocRenderPlugin,
    ScalarRenderPlugin,
    StoplightRenderPlugin,
    SwaggerRenderPlugin,
    YamlRenderPlugin,
)
```

| Plugin | Default Path(s) (relative to `OpenAPIConfig.path`) | Key Parameters | Notes |
| --- | --- | --- | --- |
| `ScalarRenderPlugin` | `"/scalar"` | `version="latest"`, `js_url=None`, `css_url=None`, `path="/scalar"`, `options: dict[str, Any] \| None = None` | Default interactive UI when `render_plugins` is omitted. |
| `SwaggerRenderPlugin` | `"/swagger"` | `version="5.18.2"`, `js_url=None`, `css_url=None`, `standalone_preset_js_url=None`, `init_oauth: dict[str, Any] \| None = None`, `oauth2_redirect_url: str \| None = None`, `path="/swagger"` | Also registers `/oauth2-redirect.html`. Automatically injects a CSRF header interceptor when `app.csrf_config` has `cookie_httponly=False`. |
| `RedocRenderPlugin` | `"/redoc"` | `version="latest"`, `js_url=None`, `google_fonts: bool = True`, `path="/redoc"` | Clean 3-pane documentation reader; set `google_fonts=False` in air-gapped environments. |
| `RapidocRenderPlugin` | `"/rapidoc"` | `version="9.3.4"`, `js_url=None`, `path="/rapidoc"` | Web-component OpenAPI explorer; automatically injects a CSRF header interceptor when `app.csrf_config` has `cookie_httponly=False`. |
| `StoplightRenderPlugin` | `"/elements"` | `version="7.7.18"`, `js_url=None`, `css_url=None`, `path="/elements"` | Stoplight Elements UI. |
| `JsonRenderPlugin` | `"/openapi.json"` | `path="/openapi.json"`, `media_type=OpenAPIMediaType.OPENAPI_JSON` | Automatically added by `OpenAPIPlugin` if no plugin in `render_plugins` serves `"/openapi.json"`. |
| `YamlRenderPlugin` | `("/openapi.yaml", "/openapi.yml")` | `path=("/openapi.yaml", "/openapi.yml")`, `media_type=OpenAPIMediaType.OPENAPI_YAML` | Serves YAML OpenAPI specs at both `.yaml` and `.yml`. |

All `OpenAPIRenderPlugin` subclasses also accept `favicon: str = ...` and `style: str = ...` to customize the rendered HTML page.

### Root UI Resolution & Custom `openapi_router`

- **Root path (`/schema` and `/schema/`)**: When `render_plugins` is non-empty, `OpenAPIPlugin` serves the first plugin configured with `path="/"` at the root path, or falls back to `render_plugins[0]`.
- **Protecting or customizing docs routes**: Pass `openapi_router=Router(path="/internal/docs", guards=[admin_guard])` to `OpenAPIConfig` instead of subclassing `OpenAPIController`.

```python
from litestar import Litestar, Router
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import (
    ScalarRenderPlugin,
    SwaggerRenderPlugin,
    YamlRenderPlugin,
)

docs_router = Router(path="/docs", include_in_schema=False)

app = Litestar(
    route_handlers=[],
    openapi_config=OpenAPIConfig(
        title="Platform API",
        version="2025.1",
        openapi_router=docs_router,
        use_handler_docstrings=True,
        render_plugins=[
            ScalarRenderPlugin(path="/"),
            SwaggerRenderPlugin(path="/swagger"),
            YamlRenderPlugin(),
        ],
    ),
)
```

### Deprecated `OpenAPIController` Options (Do Not Use)

`OpenAPIConfig.openapi_controller`, `OpenAPIConfig.root_schema_site`, `OpenAPIConfig.enabled_endpoints`, and `litestar.openapi.controller.OpenAPIController` were deprecated in Litestar `v2.8.0` and slated for removal in `v3.0`. Always use `render_plugins`, `path`, and `openapi_router`.

---

## Route-Level OpenAPI Metadata, `ResponseSpec`, and `Operation`

Every HTTP route decorator (`@get`, `@post`, `@put`, `@patch`, `@delete`, `@route`) accepts OpenAPI customization parameters:

| Decorator Parameter | Type | Purpose |
| --- | --- | --- |
| `tags` | `Sequence[str] \| None` | Group operations in OpenAPI UIs (can also be set on `Controller` or `Router`). |
| `summary` | `str \| None` | Short summary of the operation. |
| `description` | `str \| None` | Detailed operation description (falls back to handler docstring if `use_handler_docstrings=True`). |
| `operation_id` | `str \| OperationIDCreator \| None` | Explicit `operationId` string or per-route creator callable. |
| `operation_class` | `type[Operation] = Operation` | Custom `litestar.openapi.spec.Operation` subclass to inject vendor extensions or transform the generated operation object. |
| `deprecated` | `bool = False` | Mark the operation as deprecated in OpenAPI. |
| `include_in_schema` | `bool = True` | Set `False` to omit the route (or entire `Controller`/`Router`) from the generated OpenAPI schema. |
| `raises` | `Sequence[type[HTTPException]] \| None` | Document error responses automatically using each exception class's `status_code` and detail schema. |
| `response_description` | `str \| None` | Description for the primary success response. |
| `responses` | `Mapping[int, ResponseSpec] \| None` | Document additional status codes (`202`, `204`, `404`, `409`, etc.) with explicit `ResponseSpec` definitions. |
| `security` | `Sequence[SecurityRequirement] \| None` | Per-route security requirements merged with `Controller`/`Router`/`OpenAPIConfig` security. |

### `ResponseSpec` (`from litestar.openapi import ResponseSpec`)

```python
from litestar import get
from litestar.exceptions import NotAuthorizedException, NotFoundException
from litestar.openapi import ResponseSpec
from litestar.openapi.spec import Example
from litestar.params import FromPath
import msgspec


class ProblemBody(msgspec.Struct):
    detail: str
    status_code: int


class InvoiceRead(msgspec.Struct):
    id: str
    total_cents: int


@get(
    "/invoices/{invoice_id:str}",
    summary="Fetch an invoice",
    tags=["Invoices"],
    raises=[NotAuthorizedException, NotFoundException],
    responses={
        409: ResponseSpec(
            data_container=ProblemBody,
            description="Invoice is locked for settlement",
            generate_examples=False,
            examples=[
                Example(
                    summary="Locked invoice",
                    value={"detail": "Invoice is locked", "status_code": 409},
                )
            ],
        ),
        204: ResponseSpec(
            data_container=None,
            description="Invoice archived with no content",
        ),
    },
)
async def get_invoice(invoice_id: FromPath[str]) -> InvoiceRead:
    """Return a single invoice by identifier."""
    return InvoiceRead(id=invoice_id, total_cents=4500)
```

- Pass `data_container=None` when documenting a response with no body (e.g., `204 No Content` or `304 Not Modified`).
- `data_container` accepts any supported model or DTO (`msgspec.Struct`, dataclass, Pydantic model, TypedDict, `DTOData`, etc.).

---

## Parameter & Body Schema Customization (`*Parameter` / `Body`)

Use `PathParameter`, `QueryParameter`, `HeaderParameter`, `CookieParameter` (for path, query, header, or cookie parameters) and `Body` (for request payloads) from `litestar.params` to refine OpenAPI schemas without changing runtime types:

| Keyword | Applies To | Effect |
| --- | --- | --- |
| `title` / `description` | `*Parameter`, `Body` | Override the schema title and description. |
| `examples` | `*Parameter`, `Body` | `list[Example]` (`from litestar.openapi.spec import Example`) attached to the parameter or request body. |
| `schema_extra` | `*Parameter`, `Body` | `dict[str, Any]` merged directly into the generated `Schema` object (supports OpenAPI keywords like `"format"`, `"pattern"`, and vendor extensions like `"x-enum-varnames"`). Keys that match `Schema` attributes update the attribute; unknown keys are stored in `Schema.extra`. |
| `schema_component_key` | `*Parameter`, `Body` | Override the component name under `#/components/schemas/<key>` when reusable schemas are registered. |
| `include_in_schema` | `*Parameter` | Set `False` to hide an internal query/header/cookie parameter from OpenAPI while still parsing it at runtime. |

```python
from typing import Annotated

from litestar import post
from litestar.openapi.spec import Example
from litestar.params import Body, HeaderParameter
import msgspec


class SearchFilters(msgspec.Struct):
    query: str


@post("/search")
async def search_catalog(
    data: Annotated[
        SearchFilters,
        Body(
            title="Catalog Search Request",
            schema_component_key="CatalogSearchRequest",
            schema_extra={"x-rate-tier": "search"},
            examples=[Example(summary="Keyword search", value={"query": "shoes"})],
        ),
    ],
    tenant_id: Annotated[
        str,
        HeaderParameter(
            name="X-Tenant-ID",
            description="Tenant slug",
            schema_extra={"pattern": "^[a-z0-9-]+$"},
        ),
    ],
    internal_trace: Annotated[
        str | None,
        HeaderParameter(name="X-Internal-Trace", include_in_schema=False),
    ] = None,
) -> dict[str, str]:
    """Execute a tenant-scoped catalog search."""
    return {"tenant": tenant_id, "query": data.query, "trace": internal_trace or ""}
```

---

## Security Schemes (`Components` & `SecurityScheme`)

Define security schemes using `Components` and `SecurityScheme` from `litestar.openapi.spec` (or let `JWTAuth` / `JWTCookieAuth` / `SessionAuth` register them automatically via `openapi_security_scheme_name`).

```python
from litestar import Litestar, get
from litestar.openapi import OpenAPIConfig
from litestar.openapi.spec import (
    Components,
    OAuthFlow,
    OAuthFlows,
    SecurityScheme,
)

openapi_config = OpenAPIConfig(
    title="Secure Service API",
    version="1.0.0",
    components=Components(
        security_schemes={
            "BearerAuth": SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format="JWT",
                description="Paste a valid access JWT.",
            ),
            "ApiKeyHeader": SecurityScheme(
                type="apiKey",
                name="X-API-Key",
                security_scheme_in="header",
                description="Service-to-service API key.",
            ),
            "OAuth2Auth": SecurityScheme(
                type="oauth2",
                flows=OAuthFlows(
                    authorization_code=OAuthFlow(
                        authorization_url="https://auth.example.com/oauth/authorize",
                        token_url="https://auth.example.com/oauth/token",
                        scopes={"read:items": "Read items", "write:items": "Mutate items"},
                    )
                ),
            ),
        }
    ),
    security=[{"BearerAuth": []}],
)


@get("/public-ping", security=[])
async def public_ping() -> dict[str, bool]:
    """Override global security requirement for a public endpoint."""
    return {"ok": True}


@get("/items", security=[{"OAuth2Auth": ["read:items"]}, {"ApiKeyHeader": []}])
async def list_items() -> list[str]:
    """Require either OAuth2 `read:items` scope or `X-API-Key` header."""
    return ["item-1"]


app = Litestar(route_handlers=[public_ping, list_items], openapi_config=openapi_config)
```
