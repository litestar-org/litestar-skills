# litestar-vite — Inertia.js Integration Reference

`litestar-vite` provides first-party [Inertia.js](https://inertiajs.com) support in `hybrid` mode (`mode="hybrid"`, alias `mode="inertia"`):

| Layer | Library | Role |
| --- | --- | --- |
| Client SPA | [`@inertiajs/react`](https://inertiajs.com) / `@inertiajs/vue3` / `@inertiajs/svelte` | Page resolution, forms, navigation, shared data access; generated templates target Inertia v3 |
| Frontend build | [`vite`](https://vite.dev) | Bundling, HMR, dev server, production build |
| Python bridge | `litestar-vite` (`litestar_vite.inertia`) | `VitePlugin` + `InertiaConfig`, asset manifest, type generation, page-props codec |
| Server framework | [`litestar`](../../litestar/SKILL.md) | Routes, Controllers, Guards, DI, DTOs — returning Inertia responses |

For deferred/lazy/merge props and pagination, see [Deferred, Partial & Merge Props](inertia-deferred-and-merge-props.md). For Precognition, exception handling, history encryption, `InertiaRequest`, and SSR circuit breakers, see [Advanced Inertia Patterns](inertia-advanced-patterns.md).

## Inertia Protocol & Page Envelope

Inertia bridges server-side routing with client-side rendering:

1. **Initial Request**: Server returns full `text/html`. When `InertiaConfig(use_script_element=True)` (default), the page payload is embedded inside `<script type="application/json" id="app_page" data-page="app">` with `<div id="app"></div>` as the mount root (~37% smaller than HTML-escaped `data-page` attributes). When `use_script_element=False`, the JSON is HTML-escaped inside `<div id="app" data-page="..."></div>`.
2. **Subsequent Requests**: Client sends XHR/fetch with `X-Inertia: true` and `X-Inertia-Version: <version>`, and server returns `application/json` with `X-Inertia: true`.
3. **Page Envelope (`PageProps` / `PageObjectData`)**:

```json
{
  "component": "Projects/Index",
  "props": {
    "errors": {},
    "auth": { "user": { "id": 1, "name": "Alice" } },
    "projects": []
  },
  "url": "/projects",
  "version": "a1b2c3d4",
  "flash": { "success": ["Project created."] },
  "encryptHistory": false,
  "clearHistory": false,
  "deferredProps": { "analytics": ["stats"] },
  "onceProps": { "settings": { "prop": "settings" } },
  "mergeProps": ["items"],
  "prependProps": [],
  "deepMergeProps": [],
  "matchPropsOn": ["items.id"],
  "scrollProps": {
    "posts": { "pageName": "page", "currentPage": 1, "previousPage": null, "nextPage": 2 }
  }
}
```

- `flash` is always emitted as a top-level dictionary (`{}` when empty) so flash messages do not persist in browser history state.
- `deferredProps` is emitted only on initial renders and omitted on partial reloads.

## Python Backend Setup

`ViteConfig(inertia=True)` enables `InertiaConfig()` with defaults. Pass an `InertiaConfig` instance to customize shared props, redirects, script-element bootstrap, Precognition, TypeGen, or SSR. Register one `VitePlugin` — do not register a standalone `InertiaPlugin` alongside `VitePlugin`.

```python
from litestar import Litestar
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar_vite import (
    InertiaConfig,
    InertiaSSRConfig,
    PathConfig,
    TypeGenConfig,
    ViteConfig,
    VitePlugin,
)
from litestar_vite.config import InertiaTypeGenConfig

session_backend = CookieBackendConfig(secret=b"development-only-secret-32-chars")

vite = VitePlugin(
    config=ViteConfig(
        mode="hybrid",
        paths=PathConfig(resource_dir="resources"),
        inertia=InertiaConfig(
            root_template="base.html",
            component_opt_keys=("component", "page"),
            redirect_unauthorized_to="/login",
            redirect_404="/404",
            extra_static_page_props={"appName": "Acme"},
            extra_session_page_props={"currentUser": CurrentUser},
            shared_page_prop_types={
                "auth": AuthContext,
                "permissions": Permissions | None,
            },
            encrypt_history=False,
            use_script_element=True,
            precognition=True,
            type_gen=InertiaTypeGenConfig(
                include_default_auth=True,
                include_default_flash=True,
            ),
            ssr=InertiaSSRConfig(
                enabled=True,
                timeout=2.0,
                target_selector="#app",
            ),
        ),
        types=TypeGenConfig(
            generate_page_props=True,
            output="resources/generated",
        ),
    )
)

app = Litestar(
    plugins=[vite],
    middleware=[session_backend.middleware],
)
```

### `InertiaConfig` Options

| Option | Type | Default | Purpose |
| --- | --- | --- | --- |
| `root_template` | `str` | `"index.html"` | Root HTML or Jinja template rendered on initial full-page visits |
| `component_opt_keys` | `tuple[str, ...]` | `("component", "page")` | Route `opt` keys inspected for the Inertia component name (`@get("/", component="Home")`) |
| `redirect_unauthorized_to` | `str \| None` | `None` | Redirect target when `NotAuthorizedException` or `PermissionDeniedException` is raised |
| `redirect_404` | `str \| None` | `None` | Redirect target when `NotFoundException` (404/405) is raised |
| `extra_static_page_props` | `dict[str, Any]` | `{}` | Static key/value props injected into every Inertia response |
| `extra_session_page_props` | `set[str] \| dict[str, type]` | `set()` | Session keys copied into shared props on every request; use `dict[str, type]` so TypeGen emits exact TypeScript types (`set[str]` types as `unknown`) |
| `shared_page_prop_types` | `dict[str, Any] \| None` | `None` | Python type annotations/models/unions for props pushed dynamically via `share(request, key, value)` in guards or middleware |
| `encrypt_history` | `bool` | `False` | Sets `encryptHistory: true` globally so the client encrypts browser history state via Web Crypto API |
| `use_script_element` | `bool` | `True` | Emits initial page JSON inside `<script type="application/json" id="app_page" data-page="app">` (~37% smaller payload than HTML-escaped `data-page` attributes) |
| `precognition` | `bool` | `False` | Enables Laravel Precognition protocol handling for `@precognition` routes |
| `type_gen` | `InertiaTypeGenConfig \| None` | `InertiaTypeGenConfig()` | Controls default `auth` and `flash` ambient TypeGen definitions (`include_default_auth`, `include_default_flash`) |
| `ssr` | `InertiaSSRConfig \| bool \| None` | `None` | Enables server-side rendering (`ssr=True` normalizes to `InertiaSSRConfig()`) |

### Session Middleware Optionality (`InertiaTransientState`)

- **Direct `InertiaResponse` renders** work without session middleware: `share()`, `flash()`, `error()`, and `clear_history()` stage data in request-local ASGI scope (`InertiaTransientState`).
- **Redirects (`InertiaRedirect`, `InertiaBack`, `InertiaExternalRedirect`)** and `extra_session_page_props` require a writable Litestar session (`CookieBackendConfig` or `ServerSideSessionConfig`) to persist staged flashes, errors, shared props, or `clear_history` across the redirect boundary.
- When `redirect_unauthorized_to` is configured without a writable session, unauthorized redirects fall back to appending `?error=<detail>` on the redirect target URL.

## Route Handlers & Structured Prop-Bag Returns

Route handlers with `component=` (or `page=`) can return:

- `dict[str, Any]`
- `msgspec.Struct` (encodes via `msgspec.to_builtins()`, preserving `rename="camel"` and `msgspec.field(name=...)` aliases as top-level page props)
- `@dataclass` instance
- Pydantic `BaseModel`
- Pagination containers (`OffsetPagination`, `ClassicPagination`, `ScrollPagination`)
- `InertiaResponse`

Top-level fields of structs, dataclasses, and Pydantic models are extracted shallowly into page props so nested `StaticProp` / `DeferredProp` wrappers (`defer`, `lazy`, `optional`, `once`, `always`, `merge`) remain intact. Non-mapping scalar returns are placed under `props["content"]`.

```python
from __future__ import annotations

import msgspec
from litestar import Controller, get
from litestar_vite.inertia import defer
from litestar_vite.inertia.helpers import DeferredProp

from app.domain.accounts.guards import requires_active_user
from app.domain.dashboard.schemas import Dashboard


class DashboardPageProps(msgspec.Struct, rename="camel"):
    """Props for the dashboard index page."""

    dashboard: Dashboard
    analytics: DeferredProp[dict[str, int]]
    can_export: bool = False


class DashboardController(Controller):
    """Controller for user dashboard."""

    path = "/dashboard"
    guards = [requires_active_user]

    @get("/", component="dashboard/Index")
    async def index(self, dashboard_service) -> DashboardPageProps:
        """Render dashboard page."""
        return DashboardPageProps(
            dashboard=await dashboard_service.get_for_current_user(),
            analytics=defer("analytics", dashboard_service.compute_analytics),
            can_export=True,
        )
```

## Shared Props & Flash Messages

TypeGen combines `extra_static_page_props`, `extra_session_page_props`, and `shared_page_prop_types` into `resources/generated/page-props.ts` and `resources/generated/inertia.d.ts`:

- **Shared props** (`auth`, `currentUser`, `appName`, `errors`) live on `usePage().props`.
- **Flash messages** live on top-level `usePage().flash` (`dict[str, list[str]]` on Python, `{ [category: string]: string[] }` in TypeScript), **never** `usePage().props.flash`.

```python
from litestar import Request, get, post
from litestar_vite.inertia import InertiaBack, InertiaResponse, error, flash, only, share


@get("/dashboard", component="Dashboard")
async def dashboard(request: Request) -> InertiaResponse:
    """Share request-scoped props and render dashboard."""
    share(request, "auth", {"user": request.user})
    return InertiaResponse(
        content={"summary": await load_summary()},
        prop_filter=only("summary"),
    )


@post("/users")
async def create_user(request: Request, data: UserCreate) -> InertiaBack:
    """Validate and create a user, flashing errors or success notifications."""
    if await email_exists(data.email):
        error(request, "email", "Email already exists")
        return InertiaBack(request)
    await save_user(data)
    flash(request, "User created successfully.", category="success")
    return InertiaBack(request)
```

Generated TypeScript definitions and client usage:

```ts
// resources/generated/page-props.ts (auto-generated)
export interface FlashMessages {
  [category: string]: string[]
}

export interface GeneratedSharedProps {
  errors?: Record<string, string | string[]>
  auth?: AuthContext
  currentUser?: CurrentUser
  permissions?: Permissions | null
  appName: string
}
```

```tsx
import { Link, usePage } from "@inertiajs/react"

export default function Layout({ children }: { children: React.ReactNode }) {
  const {
    props: { auth, currentUser, appName },
    flash,
  } = usePage()

  return (
    <div>
      {flash.success?.map((msg, i) => <div key={i} className="alert-success">{msg}</div>)}
      {flash.error?.map((msg, i) => <div key={i} className="alert-error">{msg}</div>)}
      <span>{appName}: {currentUser?.email ?? auth?.user?.name}</span>
      {!auth?.user && <Link href="/login">Login</Link>}
      {children}
    </div>
  )
}
```

## Redirects

| Class | Behavior |
| --- | --- |
| `InertiaRedirect(request, redirect_to)` | Validates that `redirect_to` is same-origin (falls back to `request.base_url` to prevent open redirects). Uses `307 Temporary Redirect` for `GET` and `303 See Other` for `POST`/`PUT`/`PATCH`/`DELETE`. If `redirect_to` contains a `#fragment` on an Inertia request, returns `409 Conflict` with `X-Inertia-Redirect`. Persists staged `share`/`flash`/`error`/`clear_history` state to session. |
| `InertiaBack(request)` | Subclass of `InertiaRedirect` that redirects to the validated same-origin `Referer` header (or `request.base_url` if absent or cross-origin). |
| `InertiaExternalRedirect(request, redirect_to)` | Redirects to cross-origin URLs (OAuth providers, Stripe Checkout, external docs) without same-origin restriction. Returns `409 Conflict` with `X-Inertia-Location: <url>` on Inertia requests (`X-Inertia: true`), or `307`/`303` with `Location` on non-Inertia requests. |

## Client Adapter Setup (React, Vue 3, Svelte 5)

Use `litestar-vite-plugin` in `vite.config.ts` (do not add `@inertiajs/vite` to generated Litestar scaffolds by default):

```ts
// vite.config.ts
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import litestar from "litestar-vite-plugin"

export default defineConfig({
  plugins: [
    react(),
    litestar({
      input: ["resources/app.tsx"],
      ssr: "resources/ssr.tsx",
    }),
  ],
})
```

### React Adapter

`resolvePageComponent` automatically wraps resolved components with `unwrapPageProps` (memoized via `WeakMap` to preserve component identity across partial reloads).

```tsx
// resources/app.tsx
import { createInertiaApp } from "@inertiajs/react"
import { createRoot, hydrateRoot } from "react-dom/client"
import { csrfHeaders } from "litestar-vite-plugin/helpers"
import { resolvePageComponent } from "litestar-vite-plugin/inertia-helpers"

createInertiaApp({
  resolve: (name) => resolvePageComponent(
    `./pages/${name}.tsx`,
    import.meta.glob("./pages/**/*.tsx"),
  ),
  defaults: {
    visitOptions: (_href, options) => ({
      headers: csrfHeaders(options.headers ?? {}),
    }),
  },
  setup({ el, App, props }) {
    if (el.hasChildNodes()) {
      hydrateRoot(el, <App {...props} />)
    } else {
      createRoot(el).render(<App {...props} />)
    }
  },
})
```

> **Note for Inertia v2 clients**: Inertia v3 reads the `<script type="application/json" data-page="app">` element automatically. On `@inertiajs/*` v2, either add `future: { useScriptElementForInitialPage: true }` under `defaults` in `createInertiaApp` (both client and SSR entrypoints) or set `InertiaConfig(use_script_element=False)`.

### Vue 3 Adapter

```ts
// resources/app.ts
import { createApp, h, type DefineComponent } from "vue"
import { createInertiaApp } from "@inertiajs/vue3"
import { csrfHeaders } from "litestar-vite-plugin/helpers"
import { resolvePageComponent } from "litestar-vite-plugin/inertia-helpers"

createInertiaApp({
  resolve: (name) => resolvePageComponent(
    `./pages/${name}.vue`,
    import.meta.glob<DefineComponent>("./pages/**/*.vue"),
  ),
  defaults: {
    visitOptions: (_href, options) => ({
      headers: csrfHeaders(options.headers ?? {}),
    }),
  },
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) }).use(plugin).mount(el)
  },
})
```

### Svelte 5 Adapter

`@inertiajs/svelte` expects the page resolver to return the module namespace `{ default: Component }`. `resolvePageComponent` automatically preserves the module wrapper for `.svelte` paths, or you can call `resolvePageModule` explicitly:

```ts
// resources/app.ts
import { createInertiaApp } from "@inertiajs/svelte"
import { mount } from "svelte"
import { csrfHeaders } from "litestar-vite-plugin/helpers"
import { resolvePageModule } from "litestar-vite-plugin/inertia-helpers"

createInertiaApp({
  resolve: (name) => resolvePageModule(
    `./pages/${name}.svelte`,
    import.meta.glob("./pages/**/*.svelte"),
  ),
  defaults: {
    visitOptions: (_href, options) => ({
      headers: csrfHeaders(options.headers ?? {}),
    }),
  },
  setup({ el, App, props }) {
    mount(App, { target: el, props })
  },
})
```

### SSR Entrypoint

```tsx
// resources/ssr.tsx
import { createInertiaApp } from "@inertiajs/react"
import createServer from "@inertiajs/react/server"
import { renderToString } from "react-dom/server"
import { resolvePageComponent } from "litestar-vite-plugin/inertia-helpers"

const pages = import.meta.glob("./pages/**/*.tsx")

createServer(async (page) => createInertiaApp({
  page,
  render: renderToString,
  resolve: (name) => resolvePageComponent(`./pages/${name}.tsx`, pages),
  setup: ({ App, props }) => <App {...props} />,
}))
```

## Forms, Scoped Error Bags & Validation

```tsx
import { useForm } from "@inertiajs/react"

export default function CreateProject() {
  const { data, setData, post, processing, errors } = useForm({
    name: "",
    description: "",
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    post("/projects", { errorBag: "createProject" })
  }

  return (
    <form onSubmit={submit}>
      <input value={data.name} onChange={(e) => setData("name", e.target.value)} />
      {errors.name && <span className="error">{errors.name}</span>}

      <textarea value={data.description} onChange={(e) => setData("description", e.target.value)} />
      {errors.description && <span className="error">{errors.description}</span>}

      <button type="submit" disabled={processing}>Create</button>
    </form>
  )
}
```

When `errorBag` is passed, the client sends `X-Inertia-Error-Bag: createProject` and the server scopes validation errors under `props.errors.createProject`. Raising `ValidationException` (422), `HTTP_400_BAD_REQUEST`, or `PermissionDeniedException` on an Inertia route automatically extracts field errors via `error(request, field, message)`, flashes the detail, and returns `InertiaBack(request)`.
