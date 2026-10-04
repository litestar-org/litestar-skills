# Litestar Exceptions, Problem Details & Data-Layer Error Handling Reference

Deep-dive patterns for Litestar's built-in `LitestarException` and `HTTPException` hierarchy, `ExceptionResponseContent` response builders, custom domain exception handlers, RFC 9457 `ProblemDetailsPlugin`, and `advanced_alchemy` / `sqlspec` repository error translation.

Related references:

- [`SKILL.md`](../SKILL.md) — workflow, guardrails, validation, and complete end-to-end example
- [`openapi.md`](openapi.md) — documenting error responses with `raises=[...]` and `ResponseSpec`
- [`services-and-repos.md`](services-and-repos.md) — repository service error propagation
- [`../../litestar-styleguide/SKILL.md`](../../litestar-styleguide/SKILL.md) — shared styleguide baseline

---

## Built-In `LitestarException` & `HTTPException` Hierarchy

Import framework and HTTP exceptions from `litestar.exceptions`:

```text
LitestarException (litestar.exceptions)
├── MissingDependencyException          (also inherits ImportError)
├── SerializationException
├── DTOFactoryException
│   └── InvalidAnnotationException
├── WebSocketException                  (code = 4500)
│   └── WebSocketDisconnect             (code = 1000)
└── HTTPException                       (status_code = 500)
    ├── ImproperlyConfiguredException   (status_code = 500; also inherits ValueError)
    ├── ClientException                 (status_code = 400)
    │   ├── ValidationException         (status_code = 400; also inherits ValueError)
    │   ├── NotAuthorizedException      (status_code = 401)
    │   ├── PermissionDeniedException   (status_code = 403)
    │   ├── NotFoundException           (status_code = 404; also inherits ValueError)
    │   ├── MethodNotAllowedException   (status_code = 405)
    │   ├── RequestEntityTooLarge       (status_code = 413; in litestar.exceptions.http_exceptions)
    │   └── TooManyRequestsException    (status_code = 429)
    └── InternalServerException         (status_code = 500)
        ├── ServiceUnavailableException (status_code = 503)
        ├── NoRouteMatchFoundException  (status_code = 500)
        └── TemplateNotFoundException   (status_code = 500)
```

### `HTTPException` Signature & Fields

```python
from litestar.exceptions import HTTPException

raise HTTPException(
    detail="Email address is already registered.",
    status_code=409,
    headers={"X-Retry-After": "60"},
    extra={"code": "email_conflict", "field": "email"},
)
```

| Attribute | Type | Behavior |
| --- | --- | --- |
| `status_code` | `int` | Defaults to class `status_code` (`500` on `HTTPException`, `400` on `ClientException`, etc.). |
| `detail` | `str` | Defaults to the first positional string argument, or `HTTPStatus(self.status_code).phrase` if omitted. |
| `headers` | `dict[str, str] \| None` | Optional HTTP response headers attached when serialized to a `Response`. |
| `extra` | `dict[str, Any] \| list[Any] \| None` | Optional structured metadata (e.g., field-level validation errors or machine-readable error codes). |

---

## Native Exception Responses (`litestar.exceptions.responses`)

Litestar's default HTTP exception response is a content-negotiated envelope built with `ExceptionResponseContent`, `create_exception_response`, and `create_debug_response` (`from litestar.exceptions.responses import ...`):

```json
{
  "status_code": 409,
  "detail": "Email address is already registered.",
  "extra": {
    "code": "email_conflict",
    "field": "email"
  }
}
```

- `ExceptionResponseContent(status_code: int, detail: str, media_type: MediaType | str, headers: dict[str, str] | None = None, extra: dict[str, Any] | list[Any] | None = None)`:
  - Call `.to_response(request=request)` to construct a Litestar `Response`.
  - `headers` and `media_type` configure the `Response` envelope and are excluded from the serialized body; `extra` is omitted from the JSON body when `None`.
- `create_exception_response(request: Request, exc: Exception) -> Response`:
  - Negotiates `MediaType.JSON`, `MediaType.HTML`, or `MediaType.TEXT` from the request's `Accept` header (defaulting to JSON).
  - Security guardrail: if `exc` is **not** a `LitestarException` or its `status_code == 500`, `detail` is automatically masked as `"Internal Server Error"` so internal exception messages are never leaked to clients.
- `create_debug_response(request: Request, exc: Exception) -> Response`:
  - Renders an interactive HTML or plain-text stack trace when `request.app.debug` is `True`.

---

## Custom Domain Hierarchy & `exception_handlers`

Keep domain services decoupled from HTTP by raising pure Python `Exception` subclasses in services and translating them in `exception_handlers`:

```python
from litestar import Litestar, Request, Response
from litestar.exceptions.responses import (
    ExceptionResponseContent,
    create_debug_response,
)
from litestar.enums import MediaType
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)


class ApplicationError(Exception):
    """Base class for transport-independent domain errors."""

    code: str = "application_error"

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code
        self.extra = extra


class ResourceNotFoundError(ApplicationError):
    code = "resource_not_found"


class ResourceConflictError(ApplicationError):
    code = "resource_conflict"


class ForbiddenActionError(ApplicationError):
    code = "forbidden_action"


class DomainValidationError(ApplicationError):
    code = "domain_validation_error"


_DOMAIN_STATUS_MAP: dict[type[ApplicationError], int] = {
    DomainValidationError: HTTP_400_BAD_REQUEST,
    ForbiddenActionError: HTTP_403_FORBIDDEN,
    ResourceNotFoundError: HTTP_404_NOT_FOUND,
    ResourceConflictError: HTTP_409_CONFLICT,
}


def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> Response:
    """Translate domain errors into Litestar's native exception envelope."""
    status_code = _DOMAIN_STATUS_MAP.get(type(exc), HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code == HTTP_500_INTERNAL_SERVER_ERROR and request.app.debug:
        return create_debug_response(request, exc)
    extra: dict[str, object] = {"code": exc.code}
    if exc.extra:
        extra.update(exc.extra)
    return ExceptionResponseContent(
        status_code=status_code,
        detail=exc.detail,
        media_type=MediaType.JSON,
        extra=extra,
    ).to_response(request=request)


app = Litestar(
    route_handlers=[],
    exception_handlers={ApplicationError: application_error_handler},
)
```

### Handler Resolution Order

- `exception_handlers` can be configured on `Litestar`, `Router`, `Controller`, or individual route handlers (`@get(..., exception_handlers={...})`). More specific layers override outer layers.
- Keys in `exception_handlers` may be either exception classes (`type[Exception]`) or HTTP status codes (`int`, e.g., `500` or `404`).
- For exception classes, Litestar inspects `type(exc).__mro__` in order and dispatches to the first registered base class match.

---

## RFC 9457 Problem Details (`ProblemDetailsPlugin`)

Native `HTTPException` responses are **not** RFC 9457 Problem Details. When your API contract requires `application/problem+json`, register `ProblemDetailsPlugin` from `litestar.plugins.problem_details`:

```python
from litestar import Litestar, get
from litestar.params import FromPath
from litestar.plugins.problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsException,
    ProblemDetailsPlugin,
)


class InsufficientFundsError(Exception):
    def __init__(self, account_id: str, shortfall_cents: int) -> None:
        super().__init__(f"Account {account_id} is short by {shortfall_cents} cents.")
        self.account_id = account_id
        self.shortfall_cents = shortfall_cents


def insufficient_funds_to_problem(
    exc: InsufficientFundsError,
) -> ProblemDetailsException:
    """Convert a domain exception into an RFC 9457 ProblemDetailsException."""
    return ProblemDetailsException(
        status_code=422,
        type_="https://api.example.com/problems/insufficient-funds",
        title="Insufficient funds",
        detail=str(exc),
        instance=f"/accounts/{exc.account_id}",
        extra={"shortfall_cents": exc.shortfall_cents},
    )


@get("/orders/{order_id:int}")
async def get_order(order_id: FromPath[int]) -> dict[str, int]:
    """Raise a ProblemDetailsException directly or let mapped domain errors bubble."""
    if order_id < 0:
        raise ProblemDetailsException(
            status_code=404,
            type_="https://api.example.com/problems/order-not-found",
            title="Order not found",
            detail=f"No order exists with identifier {order_id}.",
            extra={"code": "order_not_found"},
        )
    return {"id": order_id}


app = Litestar(
    route_handlers=[get_order],
    plugins=[
        ProblemDetailsPlugin(
            ProblemDetailsConfig(
                enable_for_all_http_exceptions=True,
                exception_to_problem_detail_map={
                    InsufficientFundsError: insufficient_funds_to_problem,
                },
            )
        )
    ],
)
```

### `ProblemDetailsPlugin` Behavior

- `ProblemDetailsException` subclasses `HTTPException` and adds `type_: str | None = None`, `title: str | None = None`, and `instance: str | None = None`.
- When serialized by the default handler, the response media type is `application/problem+json` (`ProblemDetailsException._PROBLEM_DETAILS_MEDIA_TYPE = "application/problem+json"`):
  - If `extra` is a `Mapping`, its keys are merged into the top-level Problem Details JSON object as RFC 9457 extension members.
  - If `extra` is a `list`, it is emitted under the `"extra"` key.
- `enable_for_all_http_exceptions=True` registers a conversion map for `HTTPException` so built-in `ValidationException`, `NotFoundException`, `PermissionDeniedException`, etc., are also returned as `application/problem+json`.
- `exception_to_problem_detail_map` maps custom exception classes (`type[ExceptionT]`) to callables `(ExceptionT) -> ProblemDetailsException`.

---

## Data-Layer Exception Handling (Match Your Stack)

### Option A: Advanced Alchemy (`advanced_alchemy`)

Advanced Alchemy wraps SQLAlchemy and driver errors inside `wrap_sqlalchemy_exception` into a structured hierarchy under `advanced_alchemy.exceptions`:

| Exception (`advanced_alchemy.exceptions`) | Base Class | Mapped HTTP Exception (`exception_to_http_response`) | Status |
| --- | --- | --- | --- |
| `NotFoundError` | `RepositoryError` | `NotFoundException` (`litestar.exceptions`) | `404 Not Found` |
| `DuplicateKeyError` | `IntegrityError` -> `RepositoryError` | `ConflictError` (`advanced_alchemy.extensions.litestar.exception_handler`) | `409 Conflict` |
| `ForeignKeyError` | `IntegrityError` -> `RepositoryError` | `ConflictError` (`advanced_alchemy.extensions.litestar.exception_handler`) | `409 Conflict` |
| `IntegrityError` | `RepositoryError` | `ConflictError` (`advanced_alchemy.extensions.litestar.exception_handler`) | `409 Conflict` |
| `MultipleResultsFoundError` | `RepositoryError` | `InternalServerException` (`litestar.exceptions`) | `500 Internal Server Error` |
| `InvalidRequestError` | `RepositoryError` | `InternalServerException` (`litestar.exceptions`) | `500 Internal Server Error` |
| `RepositoryError` (fallback) | `AdvancedAlchemyError` | `InternalServerException` (`litestar.exceptions`) | `500 Internal Server Error` |

Other non-repository exceptions in `advanced_alchemy.exceptions`: `ImproperConfigurationError`, `SerializationError`, `MissingDependencyError`.

#### Auto-Registration Gotcha in `SQLAlchemyInitPlugin`

`SQLAlchemyInitPlugin` (and `SQLAlchemyPlugin`) enables `set_default_exception_handler=True` by default, which registers `RepositoryError: exception_to_http_response` **only when** `app_config.exception_handlers` contains **no** `int` status-code keys and **no** `RepositoryError` subclasses:

```python
from advanced_alchemy.exceptions import RepositoryError
from advanced_alchemy.extensions.litestar.exception_handler import (
    ConflictError,
    exception_to_http_response,
)
from litestar import Litestar, Request, Response
from litestar.exceptions.responses import create_exception_response


def custom_500_handler(request: Request, exc: Exception) -> Response:
    """Custom 500 handler registered by integer status code.

    When any integer status-code key (such as 500) is present in
    ``exception_handlers``, ``RepositoryError: exception_to_http_response``
    must be registered explicitly alongside it.
    """
    return create_exception_response(request, exc)


app = Litestar(
    route_handlers=[],
    exception_handlers={
        500: custom_500_handler,
        RepositoryError: exception_to_http_response,
    },
)
```

Use `ConflictError` (`from advanced_alchemy.extensions.litestar.exception_handler import ConflictError`) in route decorator `raises=[ConflictError, ...]` lists so OpenAPI documents `409 Conflict` responses accurately.

### Option B: SQLSpec (`sqlspec`)

SQLSpec raises driver-normalized exceptions from `sqlspec.exceptions`:

- `SQLSpecError` (root base)
  - `RepositoryError`
  - `NotFoundError`
  - `MultipleResultsFoundError`
  - `IntegrityError` -> `UniqueViolationError`, `ForeignKeyViolationError`, `CheckViolationError`, `NotNullViolationError`
  - `SerializationConflictError`, `DeadlockError`, `QueryTimeoutError`

When `SQLSpecPlugin` (`from sqlspec.extensions.litestar import SQLSpecPlugin`) is registered on the Litestar app, it automatically registers handlers via `setdefault`:

- `NotFoundError` -> `404 Not Found` (`{"detail": ..., "status_code": 404}`)
- `IntegrityError` (including `UniqueViolationError`, `ForeignKeyViolationError`, `CheckViolationError`, `NotNullViolationError`) -> `409 Conflict` (`{"detail": ..., "status_code": 409}`)

You can override either handler by passing your own `NotFoundError` or `IntegrityError` entry in `Litestar(exception_handlers={...})`.

---

## Anti-Patterns to Avoid

- **Catching repository or validation errors in every controller method** just to re-raise `HTTPException`. Let `RepositoryError`, `SQLSpecError`, or domain exceptions bubble to `exception_handlers`.
- **Leaking raw driver messages on `500` responses** by returning `Response(content={"detail": str(exc)}, status_code=500)` directly instead of delegating to `create_exception_response(request, exc)`.
- **Registering an integer status-code handler (`500: ...` or `404: ...`) with Advanced Alchemy without also registering `RepositoryError: exception_to_http_response`** — this silently disables `SQLAlchemyInitPlugin`'s default `RepositoryError` handler.
- **Mixing Litestar's `{"status_code", "detail", "extra"}` envelope with RFC 9457 Problem Details** across routes without setting `ProblemDetailsConfig(enable_for_all_http_exceptions=True)`.

---

## Audited Upstream Source Links

- [`litestar/exceptions/base_exceptions.py` (v2.24.0)](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/exceptions/base_exceptions.py)
- [`litestar/exceptions/http_exceptions.py` (v2.24.0)](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/exceptions/http_exceptions.py)
- [`litestar/exceptions/responses/__init__.py` (v2.24.0)](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/exceptions/responses/__init__.py)
- [`litestar/plugins/problem_details.py` (v2.24.0)](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/plugins/problem_details.py)
- [`advanced_alchemy/exceptions.py`](https://github.com/litestar-org/advanced-alchemy/blob/main/advanced_alchemy/exceptions.py)
- [`advanced_alchemy/extensions/litestar/exception_handler.py`](https://github.com/litestar-org/advanced-alchemy/blob/main/advanced_alchemy/extensions/litestar/exception_handler.py)
