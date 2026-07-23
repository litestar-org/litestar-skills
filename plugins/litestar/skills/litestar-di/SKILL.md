---
name: litestar-di
description: "Auto-activate for Provide, NamedDependency, SkipValidation, Dependency(skip_validation=True), dependencies=, litestar.di, Dishka FromDishka, Inject, or providers. Not for plain parameters."
---

# Litestar Dependency Injection

Use this skill for `Provide`, `NamedDependency` / `SkipValidation`, dependency
maps, provider factories, request-scoped resources, and Dishka integration.

## Code Style Rules

- Mark every name-based injected parameter with `NamedDependency[T]`. Use
  `NamedDependency[SkipValidation[T]]` only for trusted provider output that
  must bypass validation.
- Wrap providers in `Provide`. For synchronous providers, set
  `sync_to_thread=True` for blocking work or `False` for trivial non-blocking
  work; leaving it unspecified emits a warning.
- Use Litestar dependency maps for simple and medium apps.
- Use Dishka when the project needs explicit scopes and provider modules.
- Keep provider names stable and descriptive.
- Do not open request-scoped resources at import time.

## Quick Reference

- DI patterns: [di.md](references/di.md)
- Pair with [litestar-data-services](../litestar-data-services/SKILL.md) for service providers.
- Pair with [litestar-settings](../litestar-settings/SKILL.md) for settings injection.
- Pair with [litestar-autowire](../litestar-autowire/SKILL.md) when discovered
  controllers need the optional Dishka router integration.

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
- Do not mutate dependencies on a constructed app in tests. Build a fresh app
  or test client with the replacement dependency map.

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
- <https://github.com/litestar-org/litestar/tree/v2.24.0> - Audited Litestar 2.24.0 source

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
