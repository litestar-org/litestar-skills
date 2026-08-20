# Litestar-Vite Integration (Comprehensive)

For full litestar-vite reference, see `../../litestar-vite/SKILL.md`.

## Python Backend Setup

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

session_backend = CookieBackendConfig(secret=b"development-only-secret-32-chars")

vite = VitePlugin(
    config=ViteConfig(
        mode="hybrid",
        paths=PathConfig(resource_dir="resources"),
        inertia=InertiaConfig(
            root_template="base.html",
            precognition=True,
            ssr=InertiaSSRConfig(
                enabled=True,
                url="http://127.0.0.1:13714/render",
                command=["node", "resources/ssr.js"],
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

## Inertia Response Helpers

```python
from litestar import Request, get, post
from litestar_vite.inertia import (
    InertiaBack,
    InertiaResponse,
    always,
    defer,
    error,
    lazy,
    merge,
    once,
    optional,
    share,
)


@get("/users", component="Users/Index")
async def users_page() -> InertiaResponse:
    """Render users page with deferred, lazy, and merge props."""
    return InertiaResponse(
        content={
            "users": await fetch_users(),
            "auth": always("auth", {"canCreate": True}),
            "settings": once("settings", fetch_settings),
            "comments": optional("comments", fetch_comments),
            "stats": defer("stats", fetch_stats),
            "feed": merge("feed", await fetch_feed(), strategy="append"),
        },
    )


@get("/dashboard", component="Dashboard")
async def dashboard(request: Request) -> InertiaResponse:
    """Render dashboard page and share authentication state."""
    share(request, "auth", {"user": request.user})
    return InertiaResponse(content={"summary": await load_summary()})


@post("/users")
async def create_user(request: Request, data: UserCreate) -> InertiaBack:
    """Validate and create a user, flashing errors on conflict."""
    if await email_exists(data.email):
        error(request, "email", "Email already exists")
        return InertiaBack(request)
    await save_user(data)
    return InertiaBack(request)
```

## Vite Config

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

## Frontend Setup (React)

```tsx
// resources/app.tsx
import { createInertiaApp } from "@inertiajs/react"
import { createRoot, hydrateRoot } from "react-dom/client"
import {
  resolvePageComponent,
  unwrapPageProps,
} from "litestar-vite-plugin/inertia-helpers"
import { csrfHeaders } from "litestar-vite-plugin/helpers"

createInertiaApp({
  defaults: {
    visitOptions: (_href, options) => ({
      headers: csrfHeaders(options.headers ?? {}),
    }),
  },
  resolve: (name) => resolvePageComponent(
    `./pages/${name}.tsx`,
    import.meta.glob("./pages/**/*.tsx"),
  ),
  setup({ el, App, props }) {
    const cleanProps = unwrapPageProps(props)
    if (el.hasChildNodes()) {
      hydrateRoot(el, <App {...cleanProps} />)
    } else {
      createRoot(el).render(<App {...cleanProps} />)
    }
  },
})
```

## Generated Page-Props Types

```ts
// resources/generated/page-props.ts (auto-generated)
declare module "@inertiajs/react" {
  interface PageProps {
    auth: { user: User | null }
    flash: { success?: string; error?: string }
  }
}
```

```tsx
import { usePage } from "@inertiajs/react"

export default function Dashboard() {
  const { auth, flash } = usePage().props
}
```

## Partial Reload and Version Contract

- A request is partial only when `X-Inertia-Partial-Component` matches the
  route component and partial data or partial except is present.
- Partial data includes requested keys. Partial except excludes keys and wins
  on overlap.
- Initial responses advertise deferred groups. Partial responses omit
  `deferredProps`.
- A stale asset-version `GET` receives `409` and `X-Inertia-Location`.
  Non-`GET` submissions continue to their handlers.
- Infinite-scroll metadata is `scrollProps.<propName>`, not one flat object.

## Precognition & History Encryption

```python
from litestar import Request, get, post
from litestar_vite.inertia import InertiaConfig, InertiaRedirect, InertiaResponse, precognition

inertia_config = InertiaConfig(encrypt_history=True, precognition=True)


@post("/users")
@precognition
async def create_user_precognition(request: Request, data: CreateUserDTO) -> InertiaRedirect:
    """Create a user for a non-Precognition submission."""
    user = await save_user(data)
    return InertiaRedirect(request, f"/users/{user.id}")


@get("/login", component="Auth/Login")
async def login_page() -> InertiaResponse:
    """Start a page with a new browser history-encryption key."""
    return InertiaResponse(content={}, clear_history=True)
```

`@precognition` returns `204 No Content` only for a request with
`Precognition: true` after DTO validation succeeds. `InertiaConfig(precognition=True)`
installs the matching validation-error handler.

## CLI

```bash
litestar assets install
litestar assets serve
litestar assets build
litestar assets generate-types
litestar assets doctor
```
