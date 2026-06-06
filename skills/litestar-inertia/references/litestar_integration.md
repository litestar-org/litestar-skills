# Litestar-Vite Integration (Comprehensive)

For full litestar-vite reference, see `../../litestar-vite/SKILL.md`.

## Python Backend Setup

```python
from litestar import Litestar, get
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar_vite import PathConfig, TypeGenConfig, ViteConfig, VitePlugin
from litestar_vite.inertia import InertiaConfig
from litestar_vite.inertia import InertiaResponse

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
from litestar_vite.inertia import (
    InertiaResponse,
    share, lazy, defer, merge, flash, error,
    only, except_, clear_history, scroll_props,
)

@get("/users")
async def users_page() -> InertiaResponse:
    return InertiaResponse(
        "Users/Index",
        props={
            "users": await fetch_users(),
            "stats": defer(lambda: fetch_stats()),
        },
    )

@get("/dashboard")
async def dashboard(request: Request) -> InertiaResponse:
    share(request, "auth", {"user": request.user})
    return InertiaResponse("Dashboard", props={...})
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

createInertiaApp({
  resolve: (name) => resolvePageComponent(
    name,
    import.meta.glob("./pages/**/*.tsx"),
  ),
  setup({ el, App, props }) {
    const cleanProps = unwrapPageProps(props)
    if (el.hasChildNodes()) {
      hydrateRoot(el, <App {...props} />)
    } else {
      createRoot(el).render(<App {...props} />)
    }
  },
})
```

## Generated Page-Props Types

```ts
// resources/generated/inertia-pages.d.ts (auto-generated)
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

## Inertia v2 Features

```python
# Precognition (form validation preview)
from litestar_vite.inertia import precognition

@post("/users")
@precognition
async def create_user(data: CreateUserDTO) -> InertiaResponse:
    user = await save_user(data)
    return InertiaResponse.redirect("/users")

# History encryption
inertia_config = InertiaConfig(encrypt_history=True)

# Clear history on sensitive pages
@get("/login")
async def login_page() -> InertiaResponse:
    return InertiaResponse("Auth/Login", clear_history=True)
```

## CLI

```bash
litestar assets install
litestar assets serve
litestar assets build
litestar assets generate-types
```
