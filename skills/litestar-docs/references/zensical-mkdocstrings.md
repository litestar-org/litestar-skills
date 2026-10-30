# Zensical & mkdocstrings Configuration

Canonical configuration for **Zensical Free** (`zensical >= 0.0.71`, MIT) + **`mkdocstrings-python` (Griffe static AST)** across `litestar-org` and `cofin` repositories.

## Dependency Group (`pyproject.toml`)

```toml
[dependency-groups]
doc = [
  "zensical>=0.0.71",
  "mkdocstrings-python>=2.0.1",
  "pymdown-extensions>=10.16",
  "ruff>=0.15.0",
]
```

## Canonical `zensical.toml`

```toml
[project]
site_name = "SQLSpec"
site_description = "Typed SQL query runner, statement compiler, and multi-database adapter layer for Python."
site_url = "https://sqlspec.dev/"
repo_url = "https://github.com/litestar-org/sqlspec"
repo_name = "litestar-org/sqlspec"
docs_dir = "docs"
site_dir = "site"
use_directory_urls = true
extra_css = ["stylesheets/extra.css"]
exclude_docs = """
examples/**
_tapes/**
"""

[project.theme]
variant = "modern"
custom_dir = "tools/docs/templates/theme"
favicon = "assets/images/favicon.svg"
features = [
  "navigation.tabs",
  "navigation.sections",
  "navigation.top",
  "navigation.footer",
  "navigation.indexes",
  "navigation.instant",
  "navigation.tracking",
  "search.highlight",
  "search.share",
  "search.suggest",
  "toc.follow",
  "content.code.copy",
  "content.code.annotate",
  "content.tabs.link",
]

[[project.theme.palette]]
media = "(prefers-color-scheme: light)"
scheme = "default"
primary = "custom"
accent = "custom"
toggle.icon = "lucide/sun"
toggle.name = "Switch to dark mode"

[[project.theme.palette]]
media = "(prefers-color-scheme: dark)"
scheme = "slate"
primary = "custom"
accent = "custom"
toggle.icon = "lucide/moon"
toggle.name = "Switch to light mode"

[project.markdown_extensions.toc]
permalink = true
toc_depth = "2-3"

[project.markdown_extensions.pymdownx.snippets]
base_path = ["."]
check_paths = true
dedent_subsections = true

[project.plugins.mkdocstrings]
default_handler = "python"
custom_templates = "tools/docs/templates"

[project.plugins.mkdocstrings.handlers.python]
paths = ["."]
inventories = [
  "https://docs.python.org/3/objects.inv",
  "https://docs.litestar.dev/latest/objects.inv",
]

[project.plugins.mkdocstrings.handlers.python.options]
docstring_style = "google"
inherited_members = false
show_if_no_docstring = true
show_root_heading = true
show_root_full_path = false
show_source = false
show_bases = true
show_symbol_type_heading = true
show_symbol_type_toc = false
heading_level = 3
members_order = "source"
group_by_category = true
show_Category_heading = false
separate_signature = true
show_signature_annotations = true
signature_crossrefs = true
line_length = 80
format_signature = true
merge_init_into_class = true
docstring_section_style = "table"
summary = true
enable_inventory = true
filters = ["!^_"]
```

## Theme-Aware Brand Header (`tools/docs/templates/theme/partials/logo.html`)

Zensical's default `partials/logo.html` renders a single `project.theme.logo` image across both light and dark modes. Override `tools/docs/templates/theme/partials/logo.html` so light mode renders the dark-ink wordmark (`#only-light`) and dark mode renders the light-ink wordmark (`#only-dark`) from `litestar-org/branding`:

```html
<img class="sqlspec-brand-logo sqlspec-brand-logo--light" src="{{ 'assets/images/banner-inline-light.svg' | url }}" alt="{{ config.site_name }}" />
<img class="sqlspec-brand-logo sqlspec-brand-logo--dark" src="{{ 'assets/images/banner-inline-dark.svg' | url }}" alt="{{ config.site_name }}" />
```

Pair with CSS visibility rules in `docs/stylesheets/extra.css`:

```css
[data-md-color-scheme="default"] .sqlspec-brand-logo--dark {
  display: none !important;
}

[data-md-color-scheme="slate"] .sqlspec-brand-logo--light {
  display: none !important;
}
```

## Brand-Compatible Design System & Color Palette (60-30-10 Rule)

Never copy legacy Shibuya color overrides (e.g. pure `#202235` background canvas with amber accents and un-underlined gray `#475569` links). Direct Shibuya copying causes three critical UX and accessibility failures:

1. **Unusable Link Affordance**: Styling links as plain gray (`#475569`) without underlines prevents readers from distinguishing interactive links from body copy without hovering.
2. **WCAG Contrast Failure**: Litestar Gold (`#EDB641`) on white (`#ffffff`) or light slate has a contrast ratio of only **1.88:1** (vastly failing the WCAG AA minimum of **4.5:1**). Using brand gold for body links or light-mode prose renders text unreadable.
3. **Muddy Dark Surfaces**: Flooring the entire dark canvas to saturated `#202235` with flat `#2a2d40` card surfaces degrades border separation and causes visual fatigue across dense tables and API signatures.

### Modern 60-30-10 Palette Architecture

Adhere to a modern developer documentation design system (compatible with Tailwind, Radix, and Material) that honors the Litestar brand:

- **60% Neutral Canvas**:
  - *Light Mode*: Crisp `#ffffff` canvas with `#f8fafc` secondary surfaces, subtle `#e2e8f0` borders, and high-contrast `#0f172a` deep slate text (16.5:1 contrast).
  - *Dark Mode*: Deep dark slate-navy `#0f172a` canvas (`#0b1120` code background) with elevated `#1e293b` surfaces and `#f1f5f9` text, staying in the cool navy-slate color family that is 100% harmonious with Litestar Navy (`#202235`).
- **30% Structural Chrome & Syntax**:
  - High-contrast links: Sapphire blue `#1d4ed8` in light mode and sky blue `#60a5fa` in dark mode (both 7:1+ AAA contrast) with persistent underlines.
  - Subtle borders (`#e2e8f0` / `#1e293b`) and structured JetBrains Mono code blocks.
- **10% Intentional Litestar Gold Touchpoints (`#EDB641`)**:
  - Reserved strictly for high-impact brand moments where it creates delight without hurting legibility:
    - Official logo badges (`badge-light.svg` / `badge-dark.svg`).
    - Header brand identity and logo lockup.
    - Interactive action buttons (e.g. Playground "Run" button).
    - Active tab bottom indicator lines and focus rings.
    - Code block syntax highlights for Python classes and types (`--sqlspec-hl-class-color: #b45309` light / `#fbbf24` dark, both accessible warm amber-golds with >7:1 contrast).

### Typography Hierarchy

- **Body & Headings**: **Inter** (Regular 400, Medium 500, SemiBold 600, Bold 700). High x-height, clean geometry, and optimal readability across screen densities.
- **Brand Header**: **Inter** Bold 700 uppercase with `0.14em` letter-spacing, using Litestar Navy (`#202235`) in light mode and off-white (`#f8fafc`) in dark mode.
- **Code & API Signatures**: **JetBrains Mono** with tabular numerals, clear operator distinction, and clean vertical rhythm.

## Post-Build Compaction, `llms.txt`, and Legacy Redirects (`tools/docs/postbuild.py`)

Run `tools/docs/postbuild.py` immediately after `zensical build --clean`:

1. **Non-`<pre>` HTML Indentation Compaction (`compact_site_html`)**: When a site has 60+ Reference pages in `project.nav`, Zensical renders the primary `<nav class="md-nav md-nav--primary">` inside every built HTML file (`~70 KB` of chrome including `~40 KB` of leading Jinja whitespace). Stripping leading indentation whitespace outside `<pre>...</pre>` blocks reduces every built HTML page by `~38–43 KB` while preserving code block formatting.
2. **AI Context Endpoints (`site/llms.txt` and `site/llms-full.txt`)**: Emit a structured index (`llms.txt`) and concatenated Markdown corpus (`llms-full.txt`) ordered by `project.nav`.
3. **Dual Directory + Flat `.html` Redirects (`emit_legacy_html_redirects`)**: When migrating from Sphinx (`use_directory_urls = true`), Zensical's `[project.plugins.redirects.redirect_maps]` emits `site/<old>/index.html`. `postbuild.py` emits matching flat `site/<old>.html` files (plus `site/<rel_dir>.html -> /<rel_dir>/` stubs for directory index pages like `reference/driver/index.html`) that preserve `window.location.hash`.

## Automated Build Gate (`tools/docs/verify_docs_artifacts.py`)

Fail `make docs` on any of the following conditions:

- Missing or empty `site/objects.inv`, `site/llms.txt`, or `site/llms-full.txt`
- Any `site/reference/**/*.html` file exceeding `120,000` bytes (or non-Reference HTML exceeding `160,000` bytes)
- Any page (outside `changelog`) exceeding `14` items in the right-hand `"On this page"` outline (`.md-nav--secondary`)
- Any leaked `Represent a PEP 604 union type`, `Sentinel.UNSET`, or mypyc/C-extension compiler phrase in `site/reference/**/*.html`
- Any broken internal `#anchor` link across `site/**/*.html`
