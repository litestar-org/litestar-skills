---
name: litestar-inertia
description: "Auto-activate for `@inertiajs/react`, `@inertiajs/vue3`, `@inertiajs/svelte`, `createInertiaApp`, `useForm`, `usePage`, `Link`, `router` from inertiajs, `InertiaPlugin`/`InertiaConfig` from `litestar_vite.inertia`, `@inertia` decorator, `resources/js/pages/` layout. Four-library integration: `litestar` (routes + Guards + DI) + `litestar-vite` (Inertia plugin, asset pipeline, TypeGen) + `vite` (build + HMR) + `inertia` (client adapter, forms, navigation). Produces Inertia page components, `@inertia`-decorated handlers, `InertiaPlugin` wiring, `shared_props` for auth/CSRF/flash, `useForm` with Litestar validation errors, partial reloads, lazy props, `back()` redirects, SSR. Use when: building a Python-backed SPA, converting a Litestar HTML app into an SPA, wiring React/Vue/Svelte with server-driven routing, mapping Litestar validation to form errors, or setting up Inertia SSR. Not for JSON-API-only SPAs, HTMX apps, or non-Litestar backends."
---

# Litestar + Inertia.js Integration

`litestar-inertia` is the four-library story:

| Layer | Library | Role |
|---|---|---|
| Client SPA | [`@inertiajs/react`](https://inertiajs.com) / `@inertiajs/vue3` / `@inertiajs/svelte` | Page resolution, forms, navigation, shared data access |
| Frontend build | [`vite`](https://vitejs.dev) | Bundling, HMR, dev server, production build |
| Python bridge | [`litestar-vite`](../litestar-vite/SKILL.md) | `InertiaPlugin`, asset manifest, type generation, page-props codec |
| Server framework | [`litestar`](../litestar/SKILL.md) | Routes, Controllers, Guards, DI, DTOs — returning Inertia responses |

You can't skip any of these. Using Inertia with Litestar requires all four, and the skills form a chain: Litestar routes produce page data → `InertiaPlugin` serializes it into an Inertia response → Vite-served client bundle mounts the page component → Inertia client takes over for subsequent navigations.

This skill covers that integration end-to-end. For anything that's purely about one layer (e.g., Vite config internals) see the corresponding sibling skill.

## When this skill activates

- Python files importing `litestar_vite.inertia` or using `InertiaPlugin`
- `*.tsx` / `*.vue` / `*.svelte` files importing from `@inertiajs/*`
- `createInertiaApp({ resolve, setup })` in a frontend entrypoint
- A `resources/` or `resources/js/pages/` directory alongside a `src/py/` — classic litestar-vite + Inertia layout
- `inertia.config.ts` or an `InertiaConfig` invocation in `vite.config.ts`
- User asks about "building an SPA with a Python backend", "server-driven React/Vue", "form validation errors from Python", "shared auth data across pages"

## Code Style Rules

- **PEP 604 unions, `from __future__ import annotations`** in consumer Python modules — standard Litestar rules apply
- **TypeScript typed pages** — generate page-props types via `litestar-vite`'s TypeGen, never hand-roll
- **Forms via `useForm`** — never a plain `<form onSubmit>`. `useForm` handles CSRF, errors, submission state, and navigation in one call
- **Shared data for auth + flash**, never page-specific. User identity, CSRF token, flash messages go in `InertiaConfig.shared_props`
- **camelCase on the wire** — Python msgspec Structs use `Meta(rename="camel")`, JS consumes `camelCase` directly
- **Partial reloads** over full-page reloads when only a subset of props changes (`router.reload({ only: ['notifications'] })`)
- **Lazy props** for expensive-to-compute page data the user may not need on first paint

## Quick Reference

### Backend — Python route returning an Inertia page

```python
from __future__ import annotations

from litestar import Controller, get
from litestar_vite.inertia import inertia

from app.domain.accounts.guards import requires_active_user
from app.domain.dashboard.schemas import Dashboard


class DashboardController(Controller):
    path = "/dashboard"
    guards = [requires_active_user]

    @get("/")
    @inertia("dashboard/Index")       # component name — resolved client-side
    async def index(self, dashboard_service) -> Dashboard:
        return await dashboard_service.get_for_current_user()
```

→ See [references/litestar_integration.md](references/litestar_integration.md)

### Client — page component (React)

```tsx
// resources/js/pages/dashboard/Index.tsx
import { usePage, Head } from "@inertiajs/react";
import type { Dashboard } from "@/types/generated";   // TypeGen output

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

### App wiring — four plugins working together

```python
from __future__ import annotations

from litestar import Litestar
from litestar_granian import GranianPlugin
from litestar_vite import VitePlugin, ViteConfig
from litestar_vite.inertia import InertiaPlugin, InertiaConfig

from app.lib.settings import get_settings
from app.server.shared_props import shared_props


settings = get_settings()

app = Litestar(
    route_handlers=[DashboardController, ...],
    plugins=[
        GranianPlugin(),
        VitePlugin(config=ViteConfig(
            dev_mode=settings.debug,
            bundle_dir="public",
            resource_dir="resources",
            template_dir="resources",
            hot_file="public/hot",
            root_dir="resources/js",
            is_react=True,
        )),
        InertiaPlugin(config=InertiaConfig(
            root_template="index.html",
            shared_props=shared_props,       # async callable: user, csrf, flash
            route_handler_name="spa_routes",
        )),
    ],
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

On the Python side, raising a `ValidationException` with a `dict` of field errors auto-maps into `errors` on the client — no manual serialization.

### Partial reloads — only re-fetch what changed

```tsx
import { router } from "@inertiajs/react";

// After a background task finishes, reload only notifications:
router.reload({ only: ["notifications"] });
```

### Lazy props — defer expensive data

```python
from litestar_vite.inertia import lazy

@inertia("reports/Index")
async def reports_page(self, reports_service) -> dict:
    return {
        "summary": await reports_service.summary(),            # eager
        "fullExport": lazy(lambda: reports_service.export()),  # deferred
    }
```

Client fetches `fullExport` only on `router.reload({ only: ["fullExport"] })`.

## Workflow

### Step 1 — Wire the four plugins

Register `GranianPlugin`, `VitePlugin` (with `is_react=True` / `is_vue=True` / `is_svelte=True`), and `InertiaPlugin` on the app. `VitePlugin` must precede `InertiaPlugin` — Inertia relies on Vite's manifest resolution.

### Step 2 — Define shared props

Create an async `shared_props(request) -> dict` in `app/server/shared_props.py` that returns: current user (or `None`), CSRF token, flash messages, feature flags. These are available on **every** page via `usePage().props` without having to thread them through handlers.

### Step 3 — Set up the client entrypoint

`resources/js/app.tsx` (React) or equivalent: `createInertiaApp({ resolve: (name) => resolvePageComponent(name, ...), setup: ({ el, App, props }) => createRoot(el).render(<App {...props} />) })`.

### Step 4 — Build page components

One `.tsx` / `.vue` / `.svelte` file per route, keyed by name. `@inertia("path/Name")` on the Python handler maps to `resources/js/pages/path/Name.tsx`.

### Step 5 — Generate types

`litestar assets generate-types` (from `litestar-vite`) reads your Python msgspec/DTO schemas and emits TypeScript types the page components consume directly.

### Step 6 — Validate

- `/` returns `text/html` (full initial render) on first visit
- Subsequent navigations return `application/json` with Inertia envelope (`X-Inertia: true`)
- DevTools Network tab shows `X-Inertia-*` response headers
- `useForm().post()` with invalid data returns 422 + `errors` populated

## Guardrails

- **Don't mix Inertia and plain JSON API routes in the same app surface** — pick one per domain. Mixing confuses auth, CSRF, and response shape expectations. If you need both, use separate route prefixes (`/api/*` for JSON, `/dashboard/*` for Inertia).
- **CSRF is enabled by default in Litestar-Vite's Inertia integration** — don't disable unless you know what you're breaking. `useForm` handles the token transparently.
- **`shared_props` must be cheap** — it runs on *every* request. Cache user lookup; don't hit the DB for feature flags; use Redis for session state.
- **Version strings matter** — Inertia tracks an asset version; mismatched versions force a full page reload. Let `litestar-vite` generate the version hash; don't hand-roll.
- **No mixed-framework pages** — React + Vue in the same app breaks Inertia's resolver. Pick one adapter per project.
- **Deep-link routes need real URLs** — every Inertia page should have a Litestar route returning it. SPA-only client routes (React Router inside an Inertia page) exist but are an escape hatch.
- **Don't forget the root template** — `InertiaConfig.root_template` points at the Jinja2 template that mounts the SPA. Default is `index.html`; if you want authenticated/public templates, pass different `root_template` per page via the handler decorator.

## Validation Checkpoint

Before shipping an Inertia-integrated Litestar app:

- [ ] `VitePlugin` configured with correct framework flag (`is_react` / `is_vue` / `is_svelte`)
- [ ] `InertiaPlugin` registered after `VitePlugin`
- [ ] `shared_props` defined and returns consistent shape across handlers
- [ ] Page components resolve via the resolver function (one place of truth for path→component mapping)
- [ ] TypeScript page-props types generated via `litestar assets generate-types`
- [ ] Forms use `useForm`, not bare `<form>`
- [ ] 422 responses from Litestar include `errors` that the client reads
- [ ] CSRF token is in `shared_props` and `useForm` picks it up automatically
- [ ] `dev_mode` toggles correctly between dev (Vite HMR) and prod (manifest-resolved assets)
- [ ] Production build (`litestar assets build`) emits `public/manifest.json` + hashed bundles

## Example — Authenticated dashboard with forms + partial reload

```python
# app/domain/projects/controllers.py
from __future__ import annotations

from litestar import Controller, get, post
from litestar.exceptions import ValidationException
from litestar_vite.inertia import inertia, back

from app.domain.accounts.guards import requires_active_user
from app.domain.projects.schemas import Project, ProjectCreate
from app.domain.projects.services import ProjectService


class ProjectsController(Controller):
    path = "/projects"
    guards = [requires_active_user]

    @get("/")
    @inertia("projects/Index")
    async def index(self, projects_service: ProjectService, request) -> dict:
        return {
            "projects": await projects_service.list_for_user(request.user.id),
        }

    @post("/")
    async def create(
        self, data: ProjectCreate, projects_service: ProjectService, request,
    ) -> None:
        # Validation
        if await projects_service.exists(name=data.name, owner_id=request.user.id):
            raise ValidationException(extra={"name": "You already have a project with this name."})

        await projects_service.create(data.to_dict(), owner_id=request.user.id)
        # `back()` redirects Inertia back to the previous page with flash data intact
        return back()
```

```tsx
// resources/js/pages/projects/Index.tsx
import { useForm, usePage, router } from "@inertiajs/react";
import type { Project } from "@/types/generated";

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

## References Index

- **[Inertia Protocol & Client](references/protocol.md)** — Protocol v2, request/response shape, React/Vue/Svelte adapter setup, `useForm`, `usePage`, `router`, partial reloads, lazy props, SSR
- **[Litestar Backend Integration](references/litestar_integration.md)** — `InertiaPlugin` config, `@inertia` decorator, `shared_props`, `back()`, validation errors, type generation, SSR server

## Cross-Skill References

- **[`../litestar-vite/SKILL.md`](../litestar-vite/SKILL.md)** — Vite plugin config, `VitePlugin`, asset manifest, TypeGen pipeline, HMR (the backbone Inertia sits on)
- **[`../litestar/SKILL.md`](../litestar/SKILL.md)** — Controllers, Guards, DI, DTO patterns (the request handling layer)
- **[`../advanced-alchemy/SKILL.md`](../advanced-alchemy/SKILL.md)** — Data services that produce page props
- **[`../msgspec/SKILL.md`](../msgspec/SKILL.md)** — Struct definitions that TypeGen consumes

## Canonical Reference Implementation

The canonical Litestar + Inertia stack lives at [`litestar-fullstack-inertia`](https://github.com/litestar-org/litestar-fullstack-inertia). When in doubt about wiring or file layout, mirror it.

## Official References

- Inertia.js v2 docs: <https://inertiajs.com/docs/v2>
- Upgrade guide v1 → v2: <https://inertiajs.com/docs/v2/getting-started/upgrade-guide>
- Client-side setup: <https://inertiajs.com/docs/v2/installation/client-side-setup>
- Release notes: <https://github.com/inertiajs/inertia/releases>
- `litestar-vite` Inertia docs: <https://litestar-org.github.io/litestar-vite/inertia/>
- `InertiaPlugin` API: <https://litestar-org.github.io/litestar-vite/reference/inertia/plugin.html>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [TypeScript](../litestar-styleguide/references/typescript.md)
- [Litestar](../litestar-styleguide/references/litestar.md)

Keep this skill focused on the Litestar ↔ Vite ↔ Inertia integration surface. Framework-agnostic React/Vue/Svelte patterns belong in the respective framework skills (if we ever port them) or `inertiajs.com` docs.
