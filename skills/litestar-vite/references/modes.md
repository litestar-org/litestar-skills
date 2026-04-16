# litestar-vite — Modes Reference

`litestar-vite` supports five modes. Pick one before writing code; switching mid-project is painful.

## Decision Matrix

| Question | Answer ⇒ Mode |
|---|---|
| Need full client-side routing + SPA | **spa** |
| Server-rendered HTML with Vite-bundled JS sprinkles | **template** |
| HTMX-driven hypermedia with Vite assets | **htmx** |
| Server routes returning JS page components (Inertia.js) | **hybrid** |
| Already using Nuxt / SvelteKit / SSR framework | **framework** |

## SPA Mode

- Client-side router (TanStack Router, React Router, Vue Router)
- Litestar exposes a JSON API; frontend is fully decoupled at runtime
- TypeGen recommended for end-to-end typing
- Manifest-based asset resolution in prod

```python
ViteConfig(mode="spa", ...)
```

## Template Mode

- Server-rendered Jinja2 / Mako templates
- Vite bundles JS/CSS sprinkles
- Use `{{ vite_asset() }}`, `{{ vite_css() }}`, `{{ vite_hmr_client() }}` in templates
- No client-side routing; each page is server-rendered

```python
ViteConfig(mode="template", ...)
```

## HTMX Mode

- HTMX hypermedia: server returns partial HTML with `hx-*` attributes
- Vite bundles HTMX extensions, custom JS, CSS
- HMR works for CSS and JS; HTMX swaps re-bind handlers automatically
- See `../litestar-htmx/SKILL.md`

```python
ViteConfig(mode="htmx", ...)
```

## Hybrid (Inertia) Mode

- Inertia.js — server routes return Inertia responses, client renders JS components
- Pair `VitePlugin` with `litestar_vite.inertia.InertiaPlugin`
- Page-prop type generation via `TypeGenConfig.generate_page_props=True`
- See `../inertia/SKILL.md`

```python
from litestar_vite import VitePlugin, ViteConfig
from litestar_vite.inertia import InertiaPlugin, InertiaConfig

app = Litestar(plugins=[
    VitePlugin(config=ViteConfig(mode="hybrid", ...)),
    InertiaPlugin(config=InertiaConfig(root_template="base.html")),
])
```

## Framework Mode

- For JS-side SSR frameworks (Nuxt, SvelteKit, Astro)
- Plugin defers asset handling to the framework's own dev server
- Litestar coordinates port and proxies API calls
- Use only if the JS framework owns rendering end-to-end

```python
ViteConfig(mode="framework", ...)
```
