---
name: litestar-exceptions
description: "Auto-activate for exception_handlers, HTTPException, ApplicationError, NotFoundError, ConflictError, ValidationException, PermissionDeniedException, RFC 7807 responses, or domain-to-HTTP error mapping. Use when designing Litestar exception hierarchies, handlers, or error responses. Not for client-side errors or generic Python exception cleanup."
---

# Litestar Exceptions

Use this skill for domain exception hierarchies, handler registration, and HTTP error response shape.

## Code Style Rules

- Centralize domain-to-HTTP translation in exception handlers.
- Keep route handlers free of repetitive try/except blocks.
- Use domain exception classes when services need stable error contracts.
- Keep validation errors aligned with DTO and OpenAPI behavior.

## Quick Reference

- Exception patterns: [exceptions.md](references/exceptions.md)
- Pair with [litestar-auth-guards](../litestar-auth-guards/SKILL.md) for permission failures.
- Pair with [litestar-data-services](../litestar-data-services/SKILL.md) for not-found and conflict behavior.

<workflow>

## Workflow

1. Define a small domain exception hierarchy.
2. Register handlers at app config.
3. Raise domain exceptions from services or Litestar exceptions from framework boundaries.
4. Test response status and payload shape.

</workflow>

<guardrails>

## Guardrails

- Do not catch exceptions in every handler.
- Do not leak database exception messages to API clients.
- Do not return inconsistent error payloads from neighboring routes.
- Do not replace Litestar validation behavior without a clear API reason.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Exceptions have stable status mapping.
- [ ] App-level handlers are registered.
- [ ] Services do not return sentinel error values.
- [ ] Tests cover representative failure responses.

</validation>

<example>

## Example

```python
class ApplicationError(HTTPException):
    status_code = 500

class ConflictError(ApplicationError):
    status_code = 409
```

</example>

## References Index

- [exceptions.md](references/exceptions.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
