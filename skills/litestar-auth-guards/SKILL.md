---
name: litestar-auth-guards
description: "Auto-activate for guards=, Guard, ASGIConnection, BaseRouteHandler, connection.user, PermissionDeniedException, JWT auth, OAuth2, role checks, tenant checks, or WebSocket auth. Use when implementing Litestar authentication, authorization, Guards, or permission boundaries. Not for business validation or frontend route protection."
---

# Litestar Auth and Guards

Use this skill for authentication boundaries, authorization checks, guard composition, and user context.

## Code Style Rules

- Put auth and permission checks in Guards or middleware, not handler bodies.
- Prefer Controller-level guards when a whole domain shares a policy.
- Raise Litestar HTTP exceptions or domain exceptions consistently.
- Keep tenant isolation explicit in guard logic and service filters.

## Quick Reference

- Guard patterns: [guards.md](references/guards.md)
- Middleware user loading: [litestar-middleware](../litestar-middleware/SKILL.md)
- Realtime auth: [litestar-realtime](../litestar-realtime/SKILL.md)

<workflow>

## Workflow

1. Determine where identity is loaded.
2. Add Guards at app, Controller, or route scope.
3. Keep permission checks reusable and testable.
4. Verify denial paths and authenticated success paths.

</workflow>

<guardrails>

## Guardrails

- Do not inline auth checks in handlers.
- Do not make Guards perform database work repeatedly when middleware can load the user once.
- Do not trust client-supplied tenant IDs without server-side scoping.
- Do not use HTTP-only assumptions for WebSocket auth.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Guard scope matches the policy scope.
- [ ] Denial paths return the expected status.
- [ ] Handlers contain no duplicated auth branching.
- [ ] WebSocket routes use an explicit browser-compatible auth path.

</validation>

<example>

## Example

```python
from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers import BaseRouteHandler

async def requires_active_user(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    if not connection.user or not connection.user.is_active:
        raise PermissionDeniedException("Authentication required")
```

</example>

## References Index

- [guards.md](references/guards.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
