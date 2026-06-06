# Custom Exception Hierarchy

Build a project-local exception hierarchy that rolls up to a single `ApplicationError` base, register handlers on the app, and let exceptions bubble. Handlers never catch — the app-level handler maps cleanly to HTTP.

Litestar's native HTTP exception responses follow Problem Details semantics (RFC 9457). Keep a custom envelope only when the project has an explicit API contract that differs from Problem Details.

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

If the project wants standard Problem Details, raise Litestar `HTTPException` subclasses directly at framework boundaries and put extension members in `extra`:

```python
from litestar.exceptions import HTTPException


raise HTTPException(
    status_code=409,
    detail="Email address is already registered.",
    extra={"code": "email_conflict"},
)
```

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
- Mixing a custom `{detail, statusCode}` envelope with Problem Details in neighboring routes.
- Mixing transport-layer concerns (HTTP status) into service code. Services raise domain exceptions; the handler maps to status.

## Cross-references

- Repository services raise `NotFoundError` from `get` / `get_one`: [services.md](../../litestar-data-services/references/services.md)
- Validation errors from msgspec DTOs flow through Litestar's built-in handler unless you override: [dto.md](../../litestar-dto-openapi/references/dto.md)
