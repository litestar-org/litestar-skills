# Canonical reference apps

Every skill in this collection cites one or more of the four apps below as the canonical implementation of the patterns it documents. When a skill says "adapted from `litestar-sqlstack`" or links to `litestar-fullstack-inertia`, this is the authoritative URL list.

| App | URL | What it demonstrates |
| --- | --- | --- |
| **litestar-fullstack-inertia** | <https://github.com/litestar-org/litestar-fullstack-inertia> | Monolithic `app/` layout, Inertia.js + React 19, `force-include` bundling, `hatch build --target binary` for 4-platform PyApp, advanced-alchemy + Dishka + SAQ. |
| **litestar-fullstack** | <https://github.com/litestar-org/litestar-fullstack> | Nested `src/py/app/` + `src/js/web/` layout, React + TanStack Router SPA, `ignore-vcs = true` bundling, React Email templates, advanced-alchemy + SAQ. |
| **litestar-sqlstack** | <https://github.com/cofin/litestar-sqlstack> | sqlspec service-pattern reference: `SQLSpecAsyncService` subclasses, three-provider Dishka integration, paginated repository services, Alembic migration pipeline. |
| **oracledb-vertexai-demo** | <https://github.com/cofin/oracledb-vertexai-demo> | Oracle + AI/ADK reference: `VECTOR_DISTANCE(..., COSINE)` similarity search, Vertex AI integration, `LlmAgent` + `Runner` + `SQLSpecSessionService` patterns. |

## How to cite these in a skill

When introducing a pattern that comes from one of these apps, link the app name on the **first mention in the file**:

```markdown
The session-table pattern is adapted from [litestar-sqlstack](https://github.com/cofin/litestar-sqlstack).
Subsequent mentions of `litestar-sqlstack` in this file can be bare.
```

When citing a specific source location, prefer a permalink to a tagged commit over a `path:Lstart-Lend` form (line numbers drift):

```markdown
See <https://github.com/cofin/litestar-sqlstack/blob/main/src/sqlstack/lib/service.py> for the `paginate` implementation.
```

Provenance citations to non-public codebases are forbidden — the validator at `tools/validate-skills.py` (`check_forbidden_vocab`) enforces this on every shipped file via `make validate-skills`.

## Framework coverage

Each app's primary web framework is **Litestar**. Cross-framework integration guides for `advanced-alchemy` and `sqlspec` (FastAPI, Flask, Sanic, Starlette) live in their respective skills' `references/<framework>-integration.md` files — read those instead of the Litestar-centric SKILL.md if you are working in a non-Litestar codebase.
