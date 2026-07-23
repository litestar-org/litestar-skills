---
name: litestar-inertia
description: "Auto-activate for litestar_vite.inertia, InertiaConfig, component=, @inertia, @inertiajs/*, createInertiaApp, useForm, usePage, Link, router, or pages/. Not for HTMX."
---

# Litestar + Inertia.js Integration

`litestar-inertia` is the four-library story:

| Layer | Library | Role |
| --- | --- | --- |
| Client SPA | [`@inertiajs/react`](https://inertiajs.com) / `@inertiajs/vue3` / `@inertiajs/svelte` | Page resolution, forms, navigation, shared data access; generated templates target Inertia v3 |
| Frontend build | [`vite`](https://vitejs.dev) | Bundling, HMR, dev server, production build |
| Python bridge | [`litestar-vite`](../litestar-vite/SKILL.md) | `VitePlugin` + `InertiaConfig`, asset manifest, type generation, page-props codec |
| Server framework | [`litestar`](../litestar/SKILL.md) | Routes, Controllers, Guards, DI, DTOs — returning Inertia responses |

You can't skip any of these. Using Inertia with Litestar requires all four, and the skills form a chain: Litestar routes produce page data → `ViteConfig.inertia` configures the Inertia response layer → Vite-served client bundle mounts the page component → Inertia client takes over for subsequent navigations.

This skill covers that integration end-to-end. For anything that's purely about one layer (e.g., Vite config internals) see the corresponding sibling skill.

## When this skill activates

- Python files importing `litestar_vite.inertia`, `InertiaConfig`, or route handlers with `component=`
- `*.tsx` / `*.vue` / `*.svelte` files importing from `@inertiajs/*`
- `createInertiaApp({ resolve, setup })` in a frontend entrypoint
- A `resources/` or `resources/js/pages/` directory alongside a `src/py/` — classic litestar-vite + Inertia layout
- `inertia.config.ts` or an `InertiaConfig` invocation in `vite.config.ts`
- User asks about "building an SPA with a Python backend", "server-driven React/Vue", "form validation errors from Python", "shared auth data across pages"

## Code Style Rules

- **PEP 604 unions** in consumer Python modules; use
  `from __future__ import annotations` only when the application benefits from it
- **TypeScript typed pages** — generate page-props types via `litestar-vite`'s TypeGen, never hand-roll
- **Forms via `useForm`** — use the adapter form helper for errors, submission
  state, and navigation
- **CSRF via Litestar state** — configure Litestar `CSRFConfig` and wire
  `csrfHeaders()` into global Inertia visit options; generated scaffolds already
  do this, including with `cookie_httponly=True`
- **Shared data for auth + flash**, never page-specific. Static page props go in `InertiaConfig.extra_static_page_props`; session-backed props go in `extra_session_page_props`; request-time flashes use `share(request, ...)`.
- **camelCase on the wire** — define msgspec structs with
  `class Example(msgspec.Struct, rename="camel")`; generated TypeScript consumes
  the serialized names
- **Partial reloads** over full-page reloads when only a subset of props changes (`router.reload({ only: ['notifications'] })`)
- **Lazy props** for expensive-to-compute page data the user may not need on first paint

## Quick Reference

### Backend — Python route returning an Inertia page

```python
from __future__ import annotations

from litestar import Controller, get

from app.domain.accounts.guards import requires_active_user
from app.domain.dashboard.schemas import Dashboard


class DashboardController(Controller):
    path = "/dashboard"
    guards = [requires_active_user]

    @get("/", component="dashboard/Index")
    async def index(self, dashboard_service) -> Dashboard:
        return await dashboard_service.get_for_current_user()
```

→ See [references/litestar_integration.md](references/litestar_integration.md)

### Client — page component (React)

```tsx
// resources/js/pages/dashboard/Index.tsx
import { usePage, Head } from "@inertiajs/react";
import type { Dashboard } from "@/generated/api";

export default function DashboardIndex() {
  const { dashboard } = usePage<{ dashboard: Dashboard }>().props;

  return (
    <>
      <Head title="Dashboard" />
      <h1>Welcome, {dashboard.user.name}</h1>
      <p>Your workspace has {dashboard.workspaceCount} projects.</p>
    </>
  );
}
```

→ See [references/protocol.md](references/protocol.md)

### App wiring — VitePlugin owns the Inertia bridge

```python
from __future__ import annotations

from litestar import Litestar
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar_granian import GranianPlugin
from litestar_vite import PathConfig, TypeGenConfig, ViteConfig, VitePlugin
from litestar_vite.inertia import InertiaConfig

from app.domain.accounts.schemas import CurrentUser
from app.lib.settings import get_settings


settings = get_settings()
session_backend = CookieBackendConfig(secret=settings.secret_key.encode("utf-8"))
vite = VitePlugin(
    config=ViteConfig(
        mode="hybrid",
        dev_mode=settings.debug,
        paths=PathConfig(
            root=settings.base_dir,
            resource_dir="resources",
            bundle_dir="public",
        ),
        inertia=InertiaConfig(
            root_template="index.html",
            extra_static_page_props={"appName": settings.app_name},
            extra_session_page_props={"currentUser": CurrentUser},
        ),
        types=TypeGenConfig(output="resources/generated"),
    )
)

app = Litestar(
    route_handlers=[DashboardController, ...],
    plugins=[GranianPlugin(), vite],
    middleware=[session_backend.middleware],
)
```

→ See [references/litestar_integration.md](references/litestar_integration.md) for full wiring

### Forms — `useForm` with Litestar validation errors

```tsx
import { useForm } from "@inertiajs/react";

export default function CreateProject() {
  const { data, setData, post, processing, errors } = useForm({
    name: "",
    description: "",
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); post("/projects"); }}>
      <input value={data.name} onChange={(e) => setData("name", e.target.value)} />
      {errors.name && <div className="error">{errors.name}</div>}

      <textarea value={data.description} onChange={(e) => setData("description", e.target.value)} />
      {errors.description && <div className="error">{errors.description}</div>}

      <button type="submit" disabled={processing}>Create</button>
    </form>
  );
}
```

Inertia validation follows redirect-with-session semantics. Use `error(request,
field, message)` and return `InertiaBack(request)`, or install an exception
handler that performs that mapping. A raw `422` response does not populate the
next page's `errors` prop automatically.

### Partial reloads — only re-fetch what changed

```tsx
import { router } from "@inertiajs/react";

// After a background task finishes, reload only notifications:
router.reload({ only: ["notifications"] });
```

### Lazy props — defer expensive data

```python
from litestar import get
from litestar_vite.inertia import lazy

@get("/reports", component="reports/Index")
async def reports_page(self, reports_service) -> dict:
    return {
        "summary": await reports_service.summary(),            # eager
        "fullExport": lazy("fullExport", reports_service.export),
    }
```

Client fetches `fullExport` only on `router.reload({ only: ["fullExport"] })`.
Pass the callable, not its result.

<workflow>

## Workflow

### Step 1 — Wire the bridge

Register `GranianPlugin` and one `VitePlugin(config=ViteConfig(inertia=InertiaConfig(...)))`. Add session middleware. Do not register a second Inertia plugin in normal app scaffolds; `VitePlugin` reads `ViteConfig.inertia` and configures the Inertia bridge.

### Step 2 — Define shared props

Put static values in `InertiaConfig.extra_static_page_props`. Put session-backed values in `extra_session_page_props` so the integration pulls them from `request.session`. For request-time flash/auth additions, call `share(request, key, value)` before returning an Inertia response. These are available on every page via `usePage().props` without threading them through each handler.

### Step 3 — Set up the client entrypoint

`resources/js/app.tsx` (React) or equivalent: call `createInertiaApp()` with
`resolvePageComponent()`, render setup, and global visit options:

```ts
defaults: {
  visitOptions: (_href, options) => ({
    headers: csrfHeaders(options.headers ?? {}),
  }),
}
```

Import `csrfHeaders` from `litestar-vite-plugin/helpers`.

### Step 4 — Build page components

One `.tsx` / `.vue` / `.svelte` file per route, keyed by name. `@get(..., component="path/Name")` on the Python handler maps to `resources/js/pages/path/Name.tsx`.

### Step 5 — Generate types

`litestar assets generate-types` (from `litestar-vite`) reads your Python msgspec/DTO schemas and emits TypeScript types the page components consume directly.

### Step 6 — Validate

- `/` returns `text/html` (full initial render) on first visit
- Subsequent navigations return `application/json` with Inertia envelope (`X-Inertia: true`)
- DevTools Network tab shows `X-Inertia-*` response headers
- Invalid form input stores errors and redirects back; the next page response
  exposes `errors`
- Stale asset-version `GET` requests return `409` plus
  `X-Inertia-Location`; non-`GET` requests continue to the handler
- Partial responses omit `deferredProps`

</workflow>

<guardrails>

## Guardrails

- **Don't mix Inertia and plain JSON API routes in the same app surface** — pick one per domain. Mixing confuses auth, CSRF, and response shape expectations. If you need both, use separate route prefixes (`/api/*` for JSON, `/dashboard/*` for Inertia).
- **Do not assume `useForm` adds CSRF headers** — wire `csrfHeaders()` through
  `createInertiaApp({ defaults: { visitOptions } })`; the shipped scaffolds do
  this.
- **Shared props must be cheap** — session props are read on every page request. Cache user lookup; don't hit the DB for feature flags; use Redis for session state.
- **Version strings matter** — Inertia tracks an asset version; mismatched versions force a full page reload. Let `litestar-vite` generate the version hash; don't hand-roll.
- **No mixed-framework pages** — React + Vue in the same app breaks Inertia's resolver. Pick one adapter per project.
- **Deep-link routes need real URLs** — every Inertia page should have a Litestar route returning it. SPA-only client routes (React Router inside an Inertia page) exist but are an escape hatch.
- **Don't forget the root template** — `InertiaConfig.root_template` points at the template that mounts the SPA. Default is `index.html`; Jinja-backed Inertia apps set a Litestar `TemplateConfig` as well.

</guardrails>

<validation>

## Validation Checkpoint

Before shipping an Inertia-integrated Litestar app:

- [ ] `ViteConfig.inertia` configured with `InertiaConfig(...)`
- [ ] One `VitePlugin` registered for Vite + Inertia
- [ ] Session middleware registered
- [ ] Static/session/request-time shared props have consistent shape across handlers
- [ ] Page components resolve via the resolver function (one place of truth for path→component mapping)
- [ ] TypeScript page-props types generated via `litestar assets generate-types`
- [ ] Forms use `useForm`
- [ ] Validation failures call `error()` and redirect back, or an exception
      handler performs the same mapping
- [ ] `csrfHeaders()` is wired into global visit options
- [ ] `dev_mode` toggles correctly between dev (Vite HMR) and prod (manifest-resolved assets)
- [ ] Production build emits a configured or `.vite/` fallback manifest plus
      hashed bundles

</validation>

<example>

## Example — Authenticated dashboard with forms + partial reload

```python
# app/domain/projects/controllers.py
from __future__ import annotations

from litestar import Controller, Request, get, post
from litestar_vite.inertia import InertiaBack, error

from app.domain.accounts.guards import requires_active_user
from app.domain.projects.schemas import Project, ProjectCreate
from app.domain.projects.services import ProjectService


class ProjectsController(Controller):
    path = "/projects"
    guards = [requires_active_user]

    @get("/", component="projects/Index")
    async def index(
        self, projects_service: ProjectService, request: Request
    ) -> dict[str, list[Project]]:
        return {
            "projects": await projects_service.list_for_user(request.user.id),
        }

    @post("/")
    async def create(
        self, data: ProjectCreate, projects_service: ProjectService, request: Request,
    ) -> InertiaBack:
        if await projects_service.exists(name=data.name, owner_id=request.user.id):
            error(request, "name", "You already have a project with this name.")
            return InertiaBack(request)

        await projects_service.create(data.to_dict(), owner_id=request.user.id)
        return InertiaBack(request)
```

```tsx
// resources/js/pages/projects/Index.tsx
import { useForm, usePage, router } from "@inertiajs/react";
import type { Project } from "@/generated/api";

export default function ProjectsIndex() {
  const { projects, flash } = usePage<{ projects: Project[]; flash: { success?: string } }>().props;

  const { data, setData, post, processing, errors, reset } = useForm({ name: "", description: "" });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    post("/projects", { onSuccess: () => reset() });
  };

  return (
    <>
      {flash.success && <div className="flash">{flash.success}</div>}

      <form onSubmit={onSubmit}>
        <input value={data.name} onChange={(e) => setData("name", e.target.value)} placeholder="Project name" />
        {errors.name && <div className="error">{errors.name}</div>}
        <textarea value={data.description} onChange={(e) => setData("description", e.target.value)} />
        <button disabled={processing}>Create</button>
      </form>

      <button onClick={() => router.reload({ only: ["projects"] })}>Refresh</button>

      <ul>
        {projects.map((p) => <li key={p.id}>{p.name}</li>)}
      </ul>
    </>
  );
}
```

</example>

## References Index

- **[Inertia Protocol & Client](references/protocol.md)** — Protocol v3, request/response shape, React/Vue/Svelte adapter setup, `useForm`, `usePage`, `router`, partial reloads, lazy props, SSR
- **[Litestar Backend Integration](references/litestar_integration.md)** — `InertiaConfig`, `component=` route handlers, shared props, redirect responses, validation errors, type generation, SSR server

## Cross-Skill References

- **[`../litestar-vite/SKILL.md`](../litestar-vite/SKILL.md)** — Vite plugin config, `VitePlugin`, asset manifest, TypeGen pipeline, HMR (the backbone Inertia sits on)
- **[`../litestar/SKILL.md`](../litestar/SKILL.md)** — Controllers, Guards, DI, DTO patterns (the request handling layer)
- **[`../advanced-alchemy/SKILL.md`](../advanced-alchemy/SKILL.md)** — Data services that produce page props
- **[`../msgspec/SKILL.md`](../msgspec/SKILL.md)** — Struct definitions that TypeGen consumes

## Official References

- Inertia.js v3 docs: <https://inertiajs.com/docs/v3>
- Tagged Litestar-Vite Inertia docs: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/docs/frameworks/inertia>
- Client-side setup: <https://inertiajs.com/docs/v3/installation/client-side-setup>
- Release notes: <https://github.com/inertiajs/inertia/releases>
- Tagged `litestar-vite` Inertia source: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/litestar_vite/inertia>
- Tagged Inertia tests: <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/src/py/tests/unit/inertia>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [TypeScript](../litestar-styleguide/references/typescript.md)
- [Litestar](../litestar-styleguide/references/litestar.md)

Keep this skill focused on the Litestar ↔ Vite ↔ Inertia integration surface. Framework-agnostic React/Vue/Svelte patterns belong in the respective framework skills (if we ever port them) or `inertiajs.com` docs.
