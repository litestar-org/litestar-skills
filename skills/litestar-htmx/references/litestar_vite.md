# litestar-vite Integration (HTMX + Jinja)

For full litestar-vite reference see `../../litestar-vite/SKILL.md`.

## Setup with VitePlugin (template mode)

```python
from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar_htmx import HTMXPlugin
from litestar_vite import ViteConfig, VitePlugin, PathConfig

vite_config = ViteConfig(
    mode="template",
    paths=PathConfig(resource_dir="resources"),
)
templates = TemplateConfig(directory="templates", engine=JinjaTemplateEngine)

app = Litestar(
    plugins=[VitePlugin(config=vite_config), HTMXPlugin()],
    template_config=templates,
)
```

## HTMX Helpers from `litestar-vite-plugin` (npm)

```typescript
import {
  addDirective,
  registerHtmxExtension,
  setHtmxDebug,
  swapJson,
} from "litestar-vite-plugin/helpers/htmx"

// Register custom extension
registerHtmxExtension("my-ext", {
  onEvent: (name, evt) => { /* ... */ },
})

// Enable debug
setHtmxDebug(true)

// Add custom directive
addDirective("confirm", (element, value) => {
  element.setAttribute("hx-confirm", value)
})

// Swap JSON response into DOM
swapJson(targetEl, jsonData, "innerHTML")
```

## Server-Side HTMX Responses

```python
from litestar import get
from litestar.response import Template

@get("/partials/items")
async def get_items_partial() -> Template:
    items = await fetch_items()
    return Template("partials/items.html", context={"items": items})
```

## CLI

```bash
litestar assets install    # Install JS deps
litestar assets serve      # Dev server with HMR
litestar assets build      # Production build
```
