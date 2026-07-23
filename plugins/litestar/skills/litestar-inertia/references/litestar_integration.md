# Litestar-Vite Integration (Comprehensive)

For full litestar-vite reference, see `../../litestar-vite/SKILL.md`.

## Python Backend Setup

```python
from litestar import Litestar, get
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar_vite import PathConfig, TypeGenConfig, ViteConfig, VitePlugin
from litestar_vite.inertia import InertiaConfig
from litestar_vite.inertia import InertiaRedirect, InertiaResponse

session_backend = CookieBackendConfig(secret=b"development-only-secret-32-chars")

vite = VitePlugin(
    config=ViteConfig(
        mode="hybrid",                                      # Inertia mode
        paths=PathConfig(resource_dir="resources"),
        inertia=InertiaConfig(root_template="base.html"),
        types=TypeGenConfig(
            generate_page_props=True,                       # Inertia page props
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
    defer,
    error,
    share,
)

@get("/users", component="Users/Index")
async def users_page() -> InertiaResponse:
    return InertiaResponse(
        content={
            "users": await fetch_users(),
            "stats": defer("stats", fetch_stats),
        },
    )

@get("/dashboard", component="Dashboard")
async def dashboard(request: Request) -> InertiaResponse:
    share(request, "auth", {"user": request.user})
    return InertiaResponse(content={"summary": await load_summary()})

@post("/users")
async def create_user(request: Request, data: UserCreate) -> InertiaBack:
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
import react from "@vitejs/plugin-react"   // or vue, svelte
import litestar from "litestar-vite-plugin"

export default defineConfig({
  plugins: [
    react(),
    litestar({
      input: ["resources/app.tsx"],
      ssr: "resources/ssr.tsx",   // optional SSR entry
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
  const { auth, flash } = usePage().props   // fully typed
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

## Inertia Features

```python
# Precognition (form validation preview)
from litestar import Request, get, post
from litestar_vite.inertia import InertiaRedirect, precognition

@post("/users")
@precognition
async def create_user(request: Request, data: CreateUserDTO) -> InertiaRedirect:
    user = await save_user(data)
    return InertiaRedirect(request, "/users")

# History encryption
inertia_config = InertiaConfig(encrypt_history=True)

# Clear history on sensitive pages
@get("/login", component="Auth/Login")
async def login_page() -> InertiaResponse:
    return InertiaResponse(content={}, clear_history=True)
```

## CLI

```bash
litestar assets install
litestar assets serve
litestar assets build
litestar assets generate-types
```
