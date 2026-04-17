# litestar-vite — Modes & Supported Frameworks

`litestar-vite` supports **five modes** covering every mainstream frontend stack. Pick a mode per project — switching mid-project is painful because it rewires the asset pipeline, template helpers, and TypeGen output paths.

## Decision Matrix

| Question | Answer ⇒ Mode |
|---|---|
| Full client-side routing + SPA (JSON API backend) | **spa** |
| Server-rendered HTML with Vite-bundled JS/CSS sprinkles | **template** |
| HTMX hypermedia with Vite-bundled assets | **htmx** (template mode + HTMX patterns) |
| Server routes returning JS page components (Inertia.js) | **hybrid** |
| Already using Nuxt / SvelteKit / Astro / other JS SSR framework | **framework** |

---

## Supported Frameworks Matrix

Each row is a **tested, shipping example** in the canonical [`litestar-vite/examples/`](https://github.com/litestar-org/litestar-vite/tree/main/examples) directory. Copy one of these as your starting scaffold.

| Framework | Mode | Example dir | Vite plugin(s) | Notes |
|---|---|---|---|---|
| **React** | spa | [`react/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/react) | `@vitejs/plugin-react` | Standard React SPA. |
| **React + TanStack Router** | spa | [`react-tanstack/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/react-tanstack) | `@vitejs/plugin-react`, `@tanstack/router-plugin/vite` | Auto code-splitting, file-based routing, end-to-end typed. |
| **Vue 3** | spa | [`vue/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/vue) | `@vitejs/plugin-vue` | Composition API + `<script setup>`. |
| **Svelte** | spa | [`svelte/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/svelte) | `@sveltejs/vite-plugin-svelte` | Svelte 5 runes. |
| **Angular** | spa | [`angular/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/angular) | `@analogjs/vite-plugin-angular` | Requires `resolve.mainFields: ["module"]`; Angular plugin must be first in `plugins` array. See `angular-cli/` for Angular-CLI workflow. |
| **Nuxt (Vue SSR)** | framework | [`nuxt/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/nuxt) | Nuxt's own Vite setup | Litestar proxies API; Nuxt owns rendering. Type output → `./app/generated`. |
| **SvelteKit** | framework | [`sveltekit/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/sveltekit) | SvelteKit's own Vite setup | Framework owns rendering; Litestar is the API. |
| **Astro** | framework | [`astro/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/astro) | **`litestar-vite-plugin/astro`** (different import!) | Uses Astro's own `astro.config.mjs`; `apiProxy` points at Litestar. No `vite.config.ts` needed. |
| **Inertia + React** | hybrid | [`react-inertia/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/react-inertia) | `@vitejs/plugin-react` | Server routing via `@inertia` decorator. See [`../../litestar-inertia/SKILL.md`](../../litestar-inertia/SKILL.md). |
| **Inertia + React + Jinja** | hybrid | [`react-inertia-jinja/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/react-inertia-jinja) | `@vitejs/plugin-react` | Inertia with Jinja root template (useful for auth-guarded vs public shells). |
| **Inertia + Vue** | hybrid | [`vue-inertia/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/vue-inertia) | `@vitejs/plugin-vue` | Server routing + Vue page components. |
| **Inertia + Vue + Jinja** | hybrid | [`vue-inertia-jinja/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/vue-inertia-jinja) | `@vitejs/plugin-vue` | Inertia + Jinja root template. |
| **HTMX + Jinja** | htmx | [`jinja-htmx/`](https://github.com/litestar-org/litestar-vite/tree/main/examples/jinja-htmx) | (none framework-specific) | HTMX hypermedia + Litestar `HTMXPlugin` + client-side `ls-*` JSON templating. See HTMX section below. |

### Not in canonical examples (but Vite-compatible)

- **Solid / SolidStart** — works via `@solidjs/start` in framework mode; patterns mirror SvelteKit
- **Preact** — works via `@preact/preset-vite` in spa mode; shape is identical to the React example
- **Qwik / Qwik City** — framework mode candidate; not canonically tested
- **Remix / React Router v7** — framework mode candidate; not canonically tested

Vite is framework-agnostic at its core — **anything Vite supports will build through `litestar-vite-plugin`**. The examples above are the *blessed and tested* set; niche frameworks work but you're on your own for integration tuning.

---

## SPA Mode

- Client-side router owns navigation (TanStack Router, React Router, Vue Router, Svelte router)
- Litestar exposes a JSON API; frontend is fully decoupled at runtime
- TypeGen recommended for end-to-end type safety — `@hey-api/openapi-ts` reads Litestar's OpenAPI schema and emits a typed client
- Manifest-based asset resolution in prod (Vite writes `public/manifest.json`; Litestar reads it to resolve hashed filenames)

```python
from pathlib import Path
from litestar_vite import ViteConfig, VitePlugin, PathConfig, TypeGenConfig

here = Path(__file__).parent

vite = VitePlugin(config=ViteConfig(
    mode="spa",
    dev_mode=DEV_MODE,
    paths=PathConfig(root=here),
    types=TypeGenConfig(output=Path("src/generated")),
))
```

TypeGen output path convention: **`./src/generated`** for SPAs.

---

## Template Mode

- Server-rendered Jinja2 / Mako templates — Litestar returns HTML
- Vite bundles JS/CSS sprinkles that progressively enhance pages
- Template helpers inject Vite asset URLs + HMR client

Template helpers (available when `template_config` is set + `VitePlugin` is registered):

| Helper | Purpose |
|---|---|
| `{{ vite('resources/main.js') }}` | Emit `<script type="module" src="...">` for the input file; handles dev vs manifest |
| `{{ vite_hmr() }}` | Inject Vite HMR client `<script>` during `dev_mode=True`; no-op in prod |
| `{{ vite_react_refresh() }}` | Inject React Fast Refresh preamble — must come **before** React app code |
| `{{ vite_css('resources/styles.css') }}` | Emit `<link rel="stylesheet" ...>` |
| `{{ vite_hmr_client() }}` | Alias for `vite_hmr()` |
| `{{ vite_is_running() }}` | Boolean — is the dev server live? |

```python
from litestar_vite import ViteConfig, VitePlugin, PathConfig
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig

vite = VitePlugin(config=ViteConfig(
    mode="template",
    dev_mode=DEV_MODE,
    paths=PathConfig(root=here, resource_dir="resources"),
))
templates = TemplateConfig(directory=here / "templates", engine=JinjaTemplateEngine)

app = Litestar(plugins=[vite], template_config=templates)
```

Base template layout:

```html
<!DOCTYPE html>
<html>
<head>
  {{ vite_hmr() }}
  {{ vite('resources/main.js') }}
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

---

## HTMX Mode

HTMX mode is **template mode + HTMX patterns** — it's a combination, not a separate `mode` string:

- `ViteConfig(mode="template", ...)`
- `HTMXPlugin()` registered alongside `VitePlugin`
- Templates use `hx-*` attributes for server-driven interactivity

Key building blocks:

### The `hx-ext="litestar"` extension

Add `hx-ext="litestar"` to `<body>` (or any enclosing element) to enable Litestar's client-side JSON templating extension:

```html
<body hx-ext="litestar">
```

This activates the `ls-*` attributes on `<template>` tags below.

### Client-side JSON templating with `ls-*`

When an HTMX swap returns JSON (`hx-swap="json"`), the `litestar` extension renders `<template>` blocks against the JSON payload:

| Attribute | Purpose |
|---|---|
| `ls-for="item in $data"` | Iterate over the JSON response array |
| `ls-key="item.id"` | Stable key for list reconciliation |
| `ls-if="condition"` | Render only when truthy |
| `ls-else` | Fallback block for `ls-if` |
| `${expression}` | Interpolate JS expression into text |
| `:attr="expression"` | Dynamic attribute binding |
| `$data` | The raw JSON response body |

Example — button fetches `/api/books`, renders items via a template:

```html
<button hx-get="/api/books" hx-target="#books" hx-swap="json">Load</button>

<div id="books">
  <template ls-for="book in $data" ls-key="book.id">
    <article :id="`book-${book.id}`">
      <h3>${book.title}</h3>
      <p>${book.author} • ${book.year}</p>
    </article>
  </template>
</div>
```

Single-item variant (properties accessible directly via prototype inheritance):

```html
<div hx-get="/api/books/1" hx-target="#book" hx-swap="json">
  <template ls-if="id">
    <h3>${title}</h3>
    <p>${author} • ${year}</p>
  </template>
  <template ls-else>
    <p>Click to load…</p>
  </template>
</div>
```

### Server-side HTMX partials

```python
from litestar_htmx.response import HTMXTemplate

@get("/fragments/book/{book_id:int}")
async def book_fragment(self, book_id: int) -> Template:
    return HTMXTemplate(
        template_name="partials/book_card.html.j2",
        context={"book": _get_book(book_id)},
        re_target="#book-detail",
        re_swap="innerHTML",
        push_url=False,
    )
```

`HTMXTemplate` gives you per-response `HX-Retarget`, `HX-Reswap`, `HX-Push-Url`, `HX-Trigger` headers without setting them manually.

### HTMX boost

`hx-boost="true"` on a container makes normal `<a>` links behave like HTMX AJAX swaps — preserving SPA-feel without building a SPA:

```html
<main hx-boost="true">
  <a href="/books/42">Book 42</a>  <!-- intercepted; server returns partial; URL updated -->
</main>
```

### Vite config for HTMX

The jinja-htmx example:

```ts
import tailwindcss from "@tailwindcss/vite"
import litestar from "litestar-vite-plugin"
import { defineConfig, version } from "vite"

// Vite 7 uses rollupOptions; Vite 8 uses rolldownOptions. Handle both.
const bundlerKey = Number(version.split(".")[0]) >= 8 ? "rolldownOptions" : "rollupOptions"

export default defineConfig({
  plugins: [
    tailwindcss(),
    litestar({ input: ["resources/main.js"] }),
  ],
  build: {
    [bundlerKey]: {
      onwarn(warning, warn) {
        // HTMX uses runtime expression evaluation — suppress the build warning
        if (warning.code === "EVAL" && warning.id?.includes("htmx")) return
        warn(warning)
      },
    },
  },
})
```

See [`../../litestar-htmx/SKILL.md`](../../litestar-htmx/SKILL.md) for the full HTMX server-side surface (`HTMXRequest`, `HTMXResponse`, all `HX-*` headers).

---

## Hybrid (Inertia) Mode

- Server routes return Inertia responses via `@inertia("component/name")` decorator
- Page components live in `resources/js/pages/<component>/<name>.tsx`
- Pair `VitePlugin` with `litestar_vite.inertia.InertiaPlugin`
- Page-prop type generation via `TypeGenConfig` + Inertia's schema

```python
from litestar_vite import VitePlugin, ViteConfig
from litestar_vite.inertia import InertiaPlugin, InertiaConfig

app = Litestar(plugins=[
    VitePlugin(config=ViteConfig(mode="hybrid", is_react=True, ...)),
    InertiaPlugin(config=InertiaConfig(root_template="index.html")),
])
```

TypeGen output path convention: **`./resources/generated`** for Inertia.

See [`../../litestar-inertia/SKILL.md`](../../litestar-inertia/SKILL.md) for the full four-library integration.

---

## Framework Mode

For JS-side SSR frameworks that own rendering end-to-end:

- **Nuxt** — Vue SSR
- **SvelteKit** — Svelte SSR
- **Astro** — content-first with islands architecture
- **Remix / React Router v7** — not canonically tested but same shape

Litestar defers asset handling to the framework and proxies only API calls:

```python
ViteConfig(mode="framework", ...)
```

TypeGen output path convention: **`./app/generated`** for Nuxt; follows framework convention otherwise.

### Astro-specific (different plugin import)

Astro uses its own config (`astro.config.mjs`) — no `vite.config.ts`. Import the Astro-flavored plugin entry:

```js
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "astro/config"
import litestar from "litestar-vite-plugin/astro"   // ← different entry point!

const LITESTAR_PORT = process.env.LITESTAR_PORT ?? "8000"

export default defineConfig({
  integrations: [
    litestar({
      apiProxy: `http://127.0.0.1:${LITESTAR_PORT}`,
      apiPrefix: "/api",
      types: true,
    }),
  ],
  vite: { plugins: [tailwindcss()] },
})
```

### Angular-specific (plugin ordering + mainFields)

Angular needs `@analogjs/vite-plugin-angular` **first** in the plugins array and `resolve.mainFields: ["module"]`:

```ts
import angular from "@analogjs/vite-plugin-angular"
import tailwindcss from "@tailwindcss/vite"
import litestar from "litestar-vite-plugin"
import { defineConfig } from "vite"

export default defineConfig({
  resolve: { mainFields: ["module"] },
  plugins: [
    angular(),          // MUST be first
    tailwindcss(),
    litestar({ input: ["src/main.ts", "src/styles.css"] }),
  ],
})
```

---

## Shared Conventions Across All Modes

- **Tailwind v4** is the canonical styling layer — every example uses `@tailwindcss/vite`
- **OpenAPI client generation** via `@hey-api/openapi-ts`; default client is `@hey-api/client-fetch` (use `@hey-api/client-axios` only when you need Axios-specific behavior)
- **Zod is off by default** in TypeGen; opt in via `schemas.type = "zod"` in `hey-api.config.ts`
- **TypeGen output path** varies by mode: `./src/generated` (SPA), `./resources/generated` (Inertia), `./app/generated` (Nuxt)
- **Template helpers** work across template, htmx, and hybrid modes (anywhere you render server-side HTML)
- **Canonical scripts** in `package.json`: `dev`, `build`, `preview`/`serve`, `generate-types`

---

## Reference Apps

| App | Stack | Link |
|---|---|---|
| `litestar-fullstack-spa` | React + TanStack + advanced-alchemy + SAQ | <https://github.com/litestar-org/litestar-fullstack-spa> |
| `litestar-fullstack-inertia` | Inertia + React + advanced-alchemy | <https://github.com/litestar-org/litestar-fullstack-inertia> |

When adopting a framework, start from the canonical example, not a blank slate.
