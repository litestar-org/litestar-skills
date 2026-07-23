# Litestar Vite Integration

Use Litestar Vite alongside `litestar-htmx` when an HTMX application needs
bundled assets, HMR, generated routes, automatic CSRF header injection, or
client-side JSON templating.

Keep the layers distinct:

| Layer | Package | Responsibility |
| --- | --- | --- |
| Server | `litestar-htmx` / `litestar_htmx` | `HTMXRequest`, `HTMXTemplate`, `HTMXPlugin`, and `HX-*` response helpers |
| Assets | `litestar-vite` / `litestar_vite` | Vite lifecycle, manifest assets, HMR, and template helpers |
| Browser | `litestar-vite-plugin/helpers` | Registers `hx-ext="litestar"` for CSRF injection and JSON templating |

The server integration works without Litestar Vite. The browser extension is
not part of `litestar-htmx` and is not enabled by `HTMXPlugin()`.

## Server Setup

Use Litestar Vite's canonical `template` mode for Jinja-rendered HTMX pages:

```python
from pathlib import Path

from litestar import Litestar
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar_htmx import HTMXPlugin
from litestar_vite import PathConfig, ViteConfig, VitePlugin

here = Path(__file__).parent

vite = VitePlugin(
    config=ViteConfig(
        mode="template",
        paths=PathConfig(root=here, resource_dir="resources"),
    )
)
templates = TemplateConfig(
    directory=here / "templates",
    engine=JinjaTemplateEngine,
)

app = Litestar(
    route_handlers=[...],
    plugins=[vite, HTMXPlugin()],
    template_config=templates,
)
```

`VitePlugin` owns assets and template helpers. `HTMXPlugin` owns the HTMX
request class and response signature types.

## Browser Extension

Register the Litestar Vite extension explicitly in the Vite entry point:

```javascript
import htmx from "htmx.org"
import { registerHtmxExtension } from "litestar-vite-plugin/helpers"
import "./styles.css"

window.htmx = htmx
registerHtmxExtension()
htmx.process(document.body)
```

Activate that extension in the page:

```html
<head>
  <meta name="csrf-token" content="{{ csrf_token | default('') }}">
  {{ vite_hmr() }}
  {{ vite('resources/main.js') }}
</head>
<body hx-ext="litestar">
  {% block content %}{% endblock %}
</body>
```

`registerHtmxExtension()` takes no arguments in Litestar Vite 0.27.0. It
registers the extension named `litestar`, injects the CSRF token from the meta
tag into HTMX requests, and enables `hx-swap="json"` templating.

## Choose the Rendering Path

| Requirement | Use |
| --- | --- |
| Server-rendered fragment | `HTMXTemplate` from `litestar_htmx` |
| `HX-*` response behavior | A `litestar_htmx` response helper |
| Bundled CSS/JavaScript or HMR | `VitePlugin(mode="template")` |
| JSON response rendered through `ls-*` templates | `hx-ext="litestar"` from `litestar-vite-plugin/helpers` |

Do not require the Litestar Vite browser extension for ordinary HTML fragment
swaps. Do not describe its `ls-*` directives as features of `litestar-htmx`.

## Official References

- <https://github.com/litestar-org/litestar-htmx/tree/v0.5.0>
- <https://github.com/litestar-org/litestar-vite/blob/v0.27.0/docs/frameworks/htmx.rst>
- <https://github.com/litestar-org/litestar-vite/blob/v0.27.0/src/js/src/helpers/htmx.ts>
- <https://github.com/litestar-org/litestar-vite/tree/v0.27.0/examples/jinja-htmx>
