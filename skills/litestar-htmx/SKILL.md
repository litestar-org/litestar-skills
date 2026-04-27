---
name: litestar-htmx
description: "Auto-activate for litestar_htmx imports, HTMXPlugin, HTMXRequest, HTMXTemplate, TriggerEvent, PushUrl, HXLocation, hx-* attributes in Litestar templates, or partial HTML responses. Use when building HTMX-powered Litestar handlers, templates, and server-triggered client events. Not for full SPA routing or non-Litestar HTMX apps."
---

# litestar-htmx

Litestar has first-party HTMX support in `litestar_htmx`. It exposes `HTMXPlugin`, `HTMXRequest` (request-side helpers), `HTMXTemplate` (template response with HTMX headers), and HTMX-specific response objects (`TriggerEvent`, `Reswap`, `Retarget`, `PushUrl`, `HXLocation`, `ClientRedirect`, `ClientRefresh`).

This skill is **Litestar-specific**. For generic HTMX `hx-*` attributes and patterns that aren't Litestar-bound, refer directly to <https://htmx.org/docs/>.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O — handlers are `async def`
- Return partial HTML, not full pages, from HTMX-targeted endpoints
- Use Jinja2 (or Mako) templates for partials; do not string-concat HTML

## Quick Reference

### HTMXRequest

`HTMXRequest` is a `Request` subclass with HTMX-aware properties:

```python
from litestar import get
from litestar_htmx import HTMXRequest

@get("/items")
async def list_items(request: HTMXRequest) -> ...:
    if request.htmx:                  # True if HX-Request header present
        ...                           # return partial
    else:
        ...                           # full page

    # Other helpers
    request.htmx.target               # HX-Target header (str | None)
    request.htmx.trigger              # HX-Trigger header
    request.htmx.trigger_name         # HX-Trigger-Name header
    request.htmx.boosted              # HX-Boosted (bool)
    request.htmx.current_url          # HX-Current-URL
    request.htmx.history_restore_request
    request.htmx.prompt               # HX-Prompt (user input from hx-prompt)
```

Wire it into the app:

```python
from litestar import Litestar
from litestar_htmx import HTMXPlugin

app = Litestar(route_handlers=[...], plugins=[HTMXPlugin()])
```

### HTMXTemplate + Partial HTML

Return Jinja partials from handlers:

```python
from litestar import get
from litestar.response import Template

@get("/items")
async def list_items() -> Template:
    items = await item_service.list()
    return Template(template_name="partials/item_list.html", context={"items": items})
```

For HTMX-targeted endpoints, the template is a fragment (no `<html>` / `<body>`), e.g.:

```html
<!-- partials/item_list.html -->
<ul id="item-list">
  {% for item in items %}
    <li>{{ item.name }}</li>
  {% endfor %}
</ul>
```

### Server-driven HTMX Responses

| Response Object | Purpose |
| --- | --- |
| `TriggerEvent(name, after="receive", params={...})` | Sets `HX-Trigger` / `HX-Trigger-After-Swap` / `HX-Trigger-After-Settle` |
| `ClientRedirect(redirect_to=...)` | Sets `HX-Redirect` — client-side hard redirect |
| `ClientRefresh()` | Sets `HX-Refresh: true` |
| `PushUrl(push_url=...)` | Sets `HX-Push-Url` — adds entry to browser history |
| `Reswap(method="outerHTML")` | Sets `HX-Reswap` — overrides client `hx-swap` |
| `Retarget(target="#new")` | Sets `HX-Retarget` — overrides client `hx-target` |
| `HXLocation(redirect_to=...)` | Sets `HX-Location` — client-side soft navigation |
| `HXStopPolling()` | Returns 286 — HTMX stops polling on this element |

Example: trigger a custom event after a successful save:

```python
from litestar_htmx import TriggerEvent

@post("/items")
async def create_item(data: ItemCreate) -> TriggerEvent:
    item = await item_service.create(data)
    return TriggerEvent(
        name="itemCreated",
        params={"id": item.id, "name": item.name},
        after="receive",
    )
```

### OOB (Out-of-Band) Swaps

For a single response that updates multiple regions, render multiple fragments and use `hx-swap-oob`:

```html
<!-- main response -->
<div id="form-result">Saved!</div>

<!-- OOB updates -->
<div id="notification" hx-swap-oob="true">New notification!</div>
<div id="counter" hx-swap-oob="innerHTML">42</div>
```

Return the combined HTML as a `Template` or `HTMXTemplate`.

### CSRF

Use Litestar's CSRF middleware; expose the token to templates as a `<meta>` tag and forward it via HTMX:

```html
<meta name="csrf-token" content="{{ request.scope['csrf_token'] }}">
<script>
  document.body.addEventListener('htmx:configRequest', (e) => {
    e.detail.headers['X-CSRF-Token'] =
      document.querySelector('meta[name="csrf-token"]').content;
  });
</script>
```

### Pairing with `litestar-vite` (template mode)

For HTMX projects with bundled JS/CSS and HMR, use `litestar-vite` in `template` mode. Vite bundles HTMX + extensions + CSS; Litestar returns partials. See `../litestar-vite/SKILL.md` and [`../litestar-vite/references/modes.md`](../litestar-vite/references/modes.md#htmx--template-mode).

```html
<!-- base.html.j2 -->
<!DOCTYPE html>
<html>
<head>
  {{ vite_hmr() }}
  {{ vite('resources/main.js') }}
</head>
<body hx-ext="litestar">          <!-- enables the Litestar client extension -->
  {% block content %}{% endblock %}
</body>
</html>
```

### The `hx-ext="litestar"` client-side templating extension

Activating `hx-ext="litestar"` (on `<body>` or any enclosing element) unlocks **client-side JSON rendering** via `<template>` tags. When an HTMX swap uses `hx-swap="json"`, the response body is parsed as JSON and matched against `ls-*` attributes on descendant `<template>` tags.

This lets you render JSON API responses as HTML **without** server-side templates — complementary to the partial-HTML pattern.

| Attribute | Purpose |
| --- | --- |
| `ls-for="item in $data"` | Iterate over the JSON response array |
| `ls-key="item.id"` | Stable key for list reconciliation |
| `ls-if="condition"` | Render only when truthy |
| `ls-else` | Fallback block for `ls-if` |
| `${expression}` | Interpolate JS expression into text content |
| `:attr="expression"` | Dynamic attribute binding |
| `$data` | The raw JSON response body |

Array rendering:

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

Single-item rendering (properties on `$data` accessible directly via prototype inheritance):

```html
<div hx-get="/api/books/1" hx-target="#book" hx-swap="json">
  <template ls-if="id">
    <h3>${title}</h3>
    <p>${author} • ${year}</p>
    <div>
      <template ls-for="tag in tags">
        <span>${tag}</span>
      </template>
    </div>
  </template>
  <template ls-else>
    <p>Click to load…</p>
  </template>
</div>
```

**When to use this vs server-side partials:**

| Case | Approach |
| --- | --- |
| Data shape simple, rendering trivial, already have JSON endpoint | Client `ls-*` templating (no `HTMXTemplate`) |
| Complex conditionals, auth-sensitive fields, heavy formatting | Server partials via `HTMXTemplate` |
| Same endpoint serving both JSON (for JS clients) and HTML (for HTMX clients) | Branch on `request.htmx`; return JSON always and let `ls-*` render it for HTMX consumers |

Both coexist in one page. The canonical `jinja-htmx` example in `litestar-vite/examples/jinja-htmx/` demonstrates both side by side.

### Common HTMX Attributes (quick refresher)

```html
<!-- Trigger types -->
<button hx-get="/items" hx-target="#item-list">Load</button>
<button hx-post="/items" hx-vals='{"name":"x"}'>Create</button>
<button hx-delete="/items/1" hx-confirm="Are you sure?">Delete</button>

<!-- Triggers -->
<input hx-get="/search" hx-trigger="keyup changed delay:500ms">
<div hx-get="/updates" hx-trigger="every 5s">Polling</div>

<!-- Swaps -->
<div hx-get="/x" hx-swap="outerHTML">Replace element</div>
<div hx-get="/x" hx-swap="beforeend">Append</div>

<!-- Boost -->
<a hx-boost="true" href="/page">Boost</a>
<a hx-get="/page" hx-push-url="true">Navigate with history</a>
```

For full HTMX attribute reference, see <https://htmx.org/reference/>.

<workflow>

## Workflow

### Step 1: Wire HTMXRequest

Pass `request_class=HTMXRequest` to `Litestar(...)`. All handlers can now type-annotate `request: HTMXRequest`.

### Step 2: Decide Page vs Partial Boundaries

For each route, decide:

- **Page route** — returns full layout (one `Template` rendering `base.html`)
- **Partial route** — returns a fragment used by `hx-get`/`hx-post`

Cluster partial routes under a sub-path like `/htmx/...` or differentiate by `request.htmx`.

### Step 3: Templates for Partials

Build Jinja2 partials as fragments — no `<html>`, no `<body>`. Mount your full-page templates separately.

### Step 4: Server-driven Behavior

Use `TriggerEvent`, `Refresh`, `Reswap`, `Retarget` to push behavior from the server. Avoid putting business logic in the client.

### Step 5: Pair with `litestar-vite` (optional)

If the app needs bundled CSS/JS or HMR for non-HTMX assets, add `litestar-vite` in `template` or `htmx` mode. See `../litestar-vite/SKILL.md`.

### Step 6: CSRF + Auth

Apply Litestar Guards / middleware as usual. Include CSRF token via `htmx:configRequest`.

### Step 7: Test

Use `litestar.testing.AsyncTestClient` with the `HX-Request: true` header to exercise partial responses. See `../litestar-testing/SKILL.md`.

```python
resp = await client.get("/items", headers={"HX-Request": "true", "HX-Target": "#item-list"})
assert "<ul" in resp.text
```

</workflow>

<guardrails>

## Guardrails

- **Use `litestar_htmx`**, not generic ASGI patterns — the plugin integrates with Litestar's lifecycle, OpenAPI, and DI.
- **Register `HTMXPlugin()`** at the app level — handlers shouldn't construct `HTMXRequest` ad-hoc.
- **Return partial HTML for HTMX-targeted routes** — never return a full layout to an `hx-get` target.
- **Use `Template` (Litestar response) — never string-concat HTML** — XSS risk and template caching benefits.
- **CSRF protection applies to HTMX too** — non-GET HTMX requests must include the CSRF token (header preferred).
- **Use server-driven response objects** (`TriggerEvent`, `Reswap`, `Retarget`) rather than ad-hoc JS — keeps logic on the server.
- **Pair with `litestar-vite` only when you need bundled assets / HMR** — pure HTMX with a CDN htmx.min.js works fine without Vite.
- **Don't return JSON to HTMX endpoints** — HTMX expects HTML; JSON breaks `hx-swap` semantics.
- **Test with `HX-Request: true`** to exercise the HTMX path.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering Litestar + HTMX code, verify:

- [ ] `HTMXPlugin()` is registered on the `Litestar(...)` constructor
- [ ] HTMX-targeted routes return Jinja2 fragments (no `<html>` / `<body>`)
- [ ] `Template` response object used (not raw HTML strings)
- [ ] CSRF middleware enabled; token forwarded via `htmx:configRequest`
- [ ] Server-driven behavior uses `TriggerEvent` / `Reswap` / `Retarget` (not ad-hoc JS)
- [ ] Tests assert against partial HTML with `HX-Request: true` header
- [ ] If using `litestar-vite`, mode is `template`

</validation>

<example>

## Example

**Task:** Items page with an HTMX-driven create form, OOB notification, and server-triggered refresh event.

```python
# app/domain/items/controllers.py
from litestar import Controller, get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, TriggerEvent


class ItemController(Controller):
    path = "/items"

    @get("/")
    async def index(self) -> Template:
        items = await item_service.list()
        return Template("pages/items.html", context={"items": items})

    @get("/list")
    async def list_partial(self, request: HTMXRequest) -> Template:
        """Partial used by hx-get on initial load and after create."""
        items = await item_service.list()
        return Template("partials/item_list.html", context={"items": items})

    @post("/")
    async def create(self, data: ItemCreate) -> TriggerEvent:
        item = await item_service.create(data)
        return TriggerEvent(
            name="itemCreated",
            params={"id": item.id, "name": item.name},
            after="receive",
        )
```

```html
<!-- pages/items.html -->
{% extends "base.html" %}

{% block content %}
  <form
    hx-post="/items/"
    hx-target="#item-list"
    hx-swap="outerHTML"
    hx-on::after-request="this.reset()"
  >
    <input name="name" required>
    <button type="submit">Add</button>
  </form>

  <div hx-get="/items/list" hx-trigger="itemCreated from:body" hx-swap="outerHTML">
    {% include "partials/item_list.html" %}
  </div>
{% endblock %}
```

```html
<!-- partials/item_list.html -->
<ul id="item-list">
  {% for item in items %}
    <li>{{ item.name }}</li>
  {% endfor %}
</ul>
```

```python
# tests/test_items.py
async def test_create_item_triggers_event(client):
    resp = await client.post(
        "/items/",
        json={"name": "Widget"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 201
    assert "itemCreated" in resp.headers["HX-Trigger"]
```

</example>

---

## References Index

- **[litestar-vite Integration](references/litestar_vite.md)** — Bundling HTMX + custom JS/CSS with `litestar-vite` in template mode.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar fundamentals (Templates, Controllers, Guards, middleware).
- **[litestar-vite](../litestar-vite/SKILL.md)** — HTMX + Jinja with Vite-bundled assets.

## Official References

- <https://docs.litestar.dev/2/usage/htmx.html>
- <https://htmx.org/docs/>
- <https://htmx.org/reference/>
- <https://htmx.org/migration-guide-htmx-1/>
- <https://extensions.htmx.org/>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
