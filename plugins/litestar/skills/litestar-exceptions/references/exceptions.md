# Custom Exception Hierarchy

Build a project-local exception hierarchy that rolls up to a single `ApplicationError` base, register handlers on the app, and let exceptions bubble. Handlers never catch — the app-level handler maps cleanly to HTTP.

Litestar's native HTTP exception response is a JSON object with
`status_code`, `detail`, and optional `extra`. It is not an RFC 9457 Problem
Details response. Register `ProblemDetailsPlugin` when the API contract
requires `application/problem+json`.

## Hierarchy

```text
HTTPException                          (litestar.exceptions)
└── ApplicationError                   (your base; project-wide)
    ├── ApplicationClientError         (4xx parent)
    │   ├── ValidationError            (400)
    │   ├── NotFoundError              (404)
    │   ├── ConflictError              (409)
    │   └── PermissionError            (403)
    └── ApplicationServerError         (5xx parent)
        └── DependencyError            (502 / 503)
```

Subclasses set `status_code` and a default `detail`; callers may override `detail`.

## Definitions (`app/lib/exceptions.py`)

```python
from __future__ import annotations

from litestar import Request, Response
from litestar.exceptions import HTTPException


class ApplicationError(HTTPException):
    """Base class for all application-level exceptions."""


class ApplicationClientError(ApplicationError):
    status_code = 400


class ValidationError(ApplicationClientError):
    status_code = 400


class NotFoundError(ApplicationClientError):
    status_code = 404


class ConflictError(ApplicationClientError):
    status_code = 409


def application_exception_handler(request: Request, exc: ApplicationError) -> Response:
    return Response(
        content={"detail": exc.detail, "status_code": exc.status_code},
        status_code=exc.status_code,
    )
```

## Response Shape

The handler controls the wire format. Consumer apps typically return:

```json
{ "detail": "Task not found", "status_code": 404 }
```

For richer error responses (error code, field-level validation errors), extend the handler:

```python
def application_exception_handler(request: Request, exc: ApplicationError) -> Response:
    body = {"detail": exc.detail, "statusCode": exc.status_code}
    if isinstance(exc, ValidationError) and getattr(exc, "errors", None):
        body["errors"] = exc.errors
    return Response(content=body, status_code=exc.status_code)
```

Native Litestar exceptions keep extension data under `extra`:

```python
from litestar.exceptions import HTTPException


raise HTTPException(
    status_code=409,
    detail="Email address is already registered.",
    extra={"code": "email_conflict"},
)
```

This produces Litestar's JSON error envelope, not Problem Details.

## RFC 9457 Problem Details

Register the plugin and raise `ProblemDetailsException`:

```python
from litestar import Litestar, get
from litestar.params import FromPath
from litestar.plugins.problem_details import (
    ProblemDetailsException,
    ProblemDetailsPlugin,
)


@get("/orders/{order_id:int}")
async def get_order(order_id: FromPath[int]) -> None:
    raise ProblemDetailsException(
        status_code=404,
        type_="https://example.com/problems/order-not-found",
        title="Order not found",
        detail=f"No order exists with identifier {order_id}.",
        extra={"code": "order_not_found"},
    )


app = Litestar(
    route_handlers=[get_order],
    plugins=[ProblemDetailsPlugin()],
)
```

The response uses `application/problem+json`. A mapping passed as `extra` is
merged into the top-level Problem Details object; a list is emitted under the
`extra` member.

The plugin does not convert every `HTTPException` by default. Enable conversion
explicitly when the whole API uses Problem Details:

```python
from litestar.plugins.problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsPlugin,
)


problem_details = ProblemDetailsPlugin(
    ProblemDetailsConfig(enable_for_all_http_exceptions=True),
)
```

Use `exception_to_problem_detail_map` for domain exceptions that need a custom
`type`, `title`, `detail`, or extension members.

## Registration

```python
from app.lib.exceptions import ApplicationError, application_exception_handler

app = Litestar(
    route_handlers=[...],
    exception_handlers={ApplicationError: application_exception_handler},
)
```

You may register multiple handlers for different bases. Litestar dispatches to the most specific match — register `ApplicationError` last as the catch-all.

## Anti-patterns

- Inline `try` / `except` in handler bodies. Let exceptions bubble.
- Mixing Litestar's `{status_code, detail, extra}` envelope with Problem
  Details in neighboring routes without an explicit compatibility boundary.
- Mixing transport-layer concerns (HTTP status) into service code. Services raise domain exceptions; the handler maps to status.

## Cross-references

- Repository services raise `NotFoundError` from `get` / `get_one`: [services.md](../../litestar-data-services/references/services.md)
- Validation errors from msgspec DTOs flow through Litestar's built-in handler unless you override: [dto.md](../../litestar-dto-openapi/references/dto.md)

## Tagged source

- [2.24 Problem Details implementation](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/plugins/problem_details.py)
- [2.24 Problem Details tests](https://github.com/litestar-org/litestar/blob/v2.24.0/tests/unit/test_plugins/test_problem_details.py)
- [2.24 native exception response](https://github.com/litestar-org/litestar/blob/v2.24.0/litestar/exceptions/responses/__init__.py)
