---
name: litestar
description: "Auto-activate for litestar.toml, [tool.litestar], pyproject.toml with a litestar dependency, or app creation with Litestar(). Use when orienting a Litestar project, choosing the right Litestar subskill, or scaffolding app-level structure. Not for focused routing, DTO, auth, DI, data, settings, exceptions, middleware, plugin, realtime, AI, deployment, or testing work - use the narrower skill."
---

# Litestar Routing Hub

Use this skill to choose the right focused Litestar skill and keep app-level choices coherent. For implementation details, open the narrow skill that matches the task.

## Code Style Rules

- Prefer first-party Litestar ecosystem packages and patterns.
- Match the project's existing stack for data access, serialization, DI, settings, background jobs, and deployment.
- Keep app setup thin: compose routes, plugins, dependencies, middleware, exception handlers, and settings from domain modules.
- Use async I/O for request handlers, service methods, background integration, and external clients.

## Quick Reference

| Task | Skill |
| --- | --- |
| Controllers, route decorators, Routers, domain folders | [litestar-routing](../litestar-routing/SKILL.md) |
| DTOs, request bodies, response schemas, OpenAPI | [litestar-dto-openapi](../litestar-dto-openapi/SKILL.md) |
| Authentication, authorization, Guards | [litestar-auth-guards](../litestar-auth-guards/SKILL.md) |
| Provide, dependency maps, Dishka wiring | [litestar-di](../litestar-di/SKILL.md) |
| Repositories, services, filters, pagination | [litestar-data-services](../litestar-data-services/SKILL.md) |
| Settings, env loading, app state | [litestar-settings](../litestar-settings/SKILL.md) |
| Domain exceptions and exception handlers | [litestar-exceptions](../litestar-exceptions/SKILL.md) |
| Built-in or custom middleware | [litestar-middleware](../litestar-middleware/SKILL.md) |
| Plugin protocols and app plugin composition | [litestar-plugins](../litestar-plugins/SKILL.md) |
| WebSockets, SSE, Channels | [litestar-realtime](../litestar-realtime/SKILL.md) |
| Google ADK / agent HTTP serving | [litestar-ai-serving](../litestar-ai-serving/SKILL.md) |
| Tests | [litestar-testing](../litestar-testing/SKILL.md) |
| Build artifacts | [litestar-build](../litestar-build/SKILL.md) |
| Deployment targets | [litestar-deployment](../litestar-deployment/SKILL.md) |

<workflow>

## Workflow

1. Inspect the project for concrete signals: route decorators, DTO classes, guards, dependency maps, service classes, settings modules, plugin lists, realtime handlers, tests, build files, or deploy files.
2. Select the narrow skill from the table above. Use the hub only while routing the task or composing app-level architecture.
3. If the task crosses boundaries, combine the minimum needed skills. Example: route plus service plus DTO means routing, data-services, and DTO/OpenAPI.
4. Keep the selected stack consistent across the app. Do not mix two persistence or DI patterns in one feature unless the existing code already does.

</workflow>

<guardrails>

## Guardrails

- Do not use this hub as a substitute for a focused skill when the task has a clear owner.
- Do not infer a new stack from examples. Match the current project first.
- Do not move auth checks, data queries, settings parsing, or background work into route handlers.
- Do not add generic ASGI guidance when Litestar has a first-party pattern.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] The focused skill selection matches the files being edited.
- [ ] Cross-cutting work names every involved skill explicitly.
- [ ] The app setup stays compositional: controllers, plugins, middleware, DI, settings, and handlers remain separated.
- [ ] Validation commands use Make targets from this repo when editing skills.

</validation>

<example>

## Example

User asks: "Add a users endpoint backed by the existing service and return an OpenAPI schema."

Use:

- [litestar-routing](../litestar-routing/SKILL.md) for Controller shape.
- [litestar-data-services](../litestar-data-services/SKILL.md) for service injection and filters.
- [litestar-dto-openapi](../litestar-dto-openapi/SKILL.md) for request and response DTOs.

</example>

## References Index

This hub has no deep references. Open the focused skill that owns the topic.

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
