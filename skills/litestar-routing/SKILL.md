---
name: litestar-routing
description: "Auto-activate for Controller, Router, @get/@post/@put/@patch/@delete, route_handler, path params, app/domain modules, or Autowire layout. Not for frontend routers."
---

# Litestar Routing

Use this skill for route handlers, Controllers, Routers, domain clustering, and endpoint module layout.

## Code Style Rules

- Cluster Controllers by domain, not HTTP method.
- Keep handlers thin: parse request data, call a service, return a DTO or response object.
- Put shared path, dependencies, guards, and tags on the Controller class.
- Use `FromPath[T]`, `FromQuery[T]`, `FromHeader[T]`, and `FromCookie[T]` for
  unconstrained request parameters.
- Use `Annotated[T, PathParameter(...)]`, `QueryParameter(...)`,
  `HeaderParameter(...)`, or `CookieParameter(...)` when the parameter needs
  constraints, metadata, or a wire name. Do not use implicit parameters or the
  deprecated `field: T = Parameter(...)` form.
- Use typed path parameters and explicit return annotations.

## Quick Reference

- Controller and route patterns: [routing.md](references/routing.md)
- Domain folder layout: [domains.md](references/domains.md)
- End-to-end vertical slice: [example.md](references/example.md)
- Automatic domain-package registration: [litestar-autowire](../litestar-autowire/SKILL.md)

<workflow>

## Workflow

1. Identify the domain boundary and URL prefix.
2. Pick a Controller when routes share path, guards, dependencies, or tags.
3. Keep data access in services and validation in DTOs.
4. Wire the Controller into the app explicitly or through Litestar Autowire.

</workflow>

<guardrails>

## Guardrails

- Do not group Controllers by HTTP method.
- Do not put authorization logic in handlers; use Guards.
- Do not hand-roll query parameter pagination; use the data-services skill.
- Do not put app-wide plugin setup in route modules.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Routes are domain-clustered.
- [ ] Handlers are async when they perform I/O.
- [ ] Shared guards and dependencies live on the Controller.
- [ ] DTO and service concerns link to their owning skills.

</validation>

<example>

## Example

```python
from litestar import Controller, get
from litestar.di import NamedDependency

class UserController(Controller):
    path = "/users"

    @get("/")
    async def list_users(
        self,
        users_service: NamedDependency[UserService],
    ) -> list[UserRead]:
        return await users_service.list_users()
```

</example>

## References Index

- [routing.md](references/routing.md)
- [domains.md](references/domains.md)
- [example.md](references/example.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference
- <https://github.com/litestar-org/litestar/tree/v2.24.0> - Audited Litestar 2.24.0 source

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
