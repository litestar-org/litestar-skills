---
name: litestar-di
description: "Auto-activate for Provide, NamedDependency, SkipValidation, Dependency(skip_validation=True), dependencies=, litestar.di, Dishka FromDishka, Inject, or providers. Not for plain parameters."
---

# Litestar Dependency Injection

Use this skill for `Provide`, `NamedDependency` / `SkipValidation` (Litestar ≥ 2.23), dependency maps, provider factories, request-scoped resources, and Dishka integration.

## Code Style Rules

- Prefer `NamedDependency[T]` and `NamedDependency[SkipValidation[T]]` (≥ 2.24) over implicit DI / `Annotated[T, Dependency()]` / `Dependency(skip_validation=True)`; `params.Dependency` and implicit dependency injection are deprecated (removed in 3.0).
- Use Litestar dependency maps for simple and medium apps.
- Use Dishka when the project needs explicit scopes and provider modules.
- Keep provider names stable and descriptive.
- Do not open request-scoped resources at import time.

## Quick Reference

- DI patterns: [di.md](references/di.md)
- Pair with [litestar-data-services](../litestar-data-services/SKILL.md) for service providers.
- Pair with [litestar-settings](../litestar-settings/SKILL.md) for settings injection.

<workflow>

## Workflow

1. Identify whether the dependency is app, request, transaction, or function scoped.
2. Choose built-in dependency maps or the existing DI framework.
3. Register providers at the narrowest useful scope.
4. Inject dependencies by name or type according to the chosen stack.

</workflow>

<guardrails>

## Guardrails

- Do not introduce Dishka for one or two simple providers.
- Do not mix dependency naming conventions in one app.
- Do not keep database sessions or clients as global mutable state.
- Do not hide business logic inside providers.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Dependency scope is explicit.
- [ ] Providers are async when they manage async resources.
- [ ] Tests can override providers cleanly.
- [ ] Provider wiring matches the app's existing DI style.

</validation>

<example>

## Example

```python
from litestar.di import NamedDependency, Provide

async def provide_user_service(db_session: NamedDependency[AsyncSession]) -> UserService:
    return UserService(session=db_session)

dependencies = {"users_service": Provide(provide_user_service)}
```

</example>

## References Index

- [di.md](references/di.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
