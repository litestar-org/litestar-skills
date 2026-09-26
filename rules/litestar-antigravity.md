---
trigger: model_decision
description: Litestar ecosystem routing and first-party skill activation rules evaluated when working with Litestar, SQLSpec, Advanced Alchemy, msgspec, Granian, SAQ, Queues, Vite, HTMX, MCP, or Google ADK.
---

# Litestar Operational Rule

When a workspace uses Litestar or its first-party ecosystem, activate the matching skill before writing, refactoring, or reviewing code:

- Core framework (app setup, routing, Controllers/Routers, DTOs/OpenAPI, guards/auth, DI/Dishka, data services/pagination, settings, exceptions/RFC 9457, middleware, plugins, WebSockets/SSE/Channels): `litestar`
- First-party plugins & runtime: `litestar-security`, `litestar-autowire`, `litestar-ai`, `litestar-granian`, `litestar-saq`, `litestar-queues`, `litestar-vite`, `litestar-htmx`, `litestar-mcp`, `litestar-email`
- Data & serialization: `sqlspec`, `advanced-alchemy`, `msgspec`
- Testing, build, deployment & style: `litestar-testing`, `pytest-databases`, `polyfactory`, `litestar-build`, `litestar-deployment`, `litestar-styleguide`
- Workflow skills: `configure`, `new-app`, `new-domain`, `review`

## Defaults

- Prefer `msgspec.Struct` + `MsgspecDTO` unless the project already standardizes on Pydantic.
- Prefer `sqlspec` or `advanced-alchemy` matching the project's existing data layer.
- Keep all route handlers, guards, dependencies, and I/O async; enforce PEP 604 unions (`T | None`).
- When working inside an upstream library repository itself (`[project] name` in `pyproject.toml` matches `sqlspec`, `litestar`, `advanced-alchemy`, `litestar-queues`, `litestar-security`, `litestar-vite`, `litestar-mcp`, `litestar-saq`, `litestar-granian`, `litestar-email`, `litestar-htmx`, `litestar-autowire`, `pytest-databases`, `polyfactory`, or `msgspec`), do NOT rely on the corresponding `litestar:<skill>` consumer skill over the repository's own source code — treat the repository source as the source of truth (and note when changes require a follow-up update to `litestar-skills`).
