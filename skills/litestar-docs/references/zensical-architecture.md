# Zensical Documentation Architecture

Canonical configuration, plugins, markdown extensions, and companion tooling for **Zensical** (`zensical >= 0.1.1`, MIT open source) + **`mkdocstrings-python` (Griffe static AST)** across Litestar repositories.

## Dependency Group (`pyproject.toml`)

```toml
[dependency-groups]
doc = [
  "zensical>=0.1.1",
  "mkdocstrings-python>=2.0.10",
  "pymdown-extensions>=13.0",
  "ruff>=0.17.5",
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

[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  { name = "mermaid", class = "mermaid", format = "pymdownx.superfences.fence_code_format" },
]

[project.markdown_extensions.pymdownx.tabbed]
alternate_style = true

[project.markdown_extensions.pymdownx.highlight]
anchor_linenums = true
line_spans = "__span"
pygments_lang_class = true

[project.plugins.mkdocstrings]
default_handler = "python"
enable_inventory = true
custom_templates = "tools/docs/templates"

[project.plugins.mkdocstrings.handlers.python]
paths = ["."]
inventories = [
  "https://docs.python.org/3/objects.inv",
  "https://docs.litestar.dev/latest/objects.inv",
  "https://msgspec.dev/objects.inv",
]

[project.plugins.mkdocstrings.handlers.python.options]
docstring_style = "google"
heading_level = 3
inherited_members = false
show_if_no_docstring = true
show_root_heading = true
show_root_full_path = false
show_source = false
show_bases = true
show_symbol_type_heading = true
show_symbol_type_toc = false
summary = true

[project.extra]
generator = false
```

## Plugin & Extension Ecosystem

### 1. Built-in Plugins

- **`search`**: Fast offline-capable search engine supporting query highlighting, shared deep-link query URLs, and live suggestions. Built into core Zensical.
- **`redirects`**: Configured via `[project.plugins.redirects.redirect_maps]`. Maps historical slugs to current locations. *Guardrail*: Never map `"path/foo.md" = "path/foo/index.md"` when `use_directory_urls = true`, as both resolve to `site/path/foo/index.html` and trigger a self-redirect loop.
- **`tags`**: Native page classification via frontmatter tags (`tags: [postgresql, async]`). Generates tag search pills and index listings.
- **`blog`**: Optional subsystem generating chronological posts, author bios, categories, archives, and RSS/Atom feeds.
- **`offline`**: Bundles all CSS/JS assets and rewrites URLs for air-gapped `file://` distribution.
- **`llmstxt`**: Native built-in replacement for `mkdocs-llmstxt`. Configured via `[project.plugins.llmstxt]` (`enabled = true`, `sections`, `markdown_description`) to emit `site/llms.txt` and Markdown page copies for AI agents. (Note: Material's legacy `projects` plugin is deprecated and not supported by Zensical.)

### 2. Markdown Extensions

- **`pymdownx.snippets`**: Embeds standalone testable code files (`--8<-- "docs/examples/..."`) with tag slicing. Enforces `check_paths = true` so dead links fail the build immediately.
- **`pymdownx.tabbed`**: Paired with `content.tabs.link` to synchronize package manager selection (`uv`, `pip`, `pdm`, `poetry`) across all pages.
- **`pymdownx.superfences`**: Renders Mermaid diagrams natively within ```` ```mermaid ```` code blocks.
- **`pymdownx.highlight` / `inlinehilite`**: Syntax highlighting with line numbering and focal line highlighting (`hl_lines="1 3-5"`).
- **`pymdownx.details`**: Collapsible admonitions (`??? note` collapsed, `???+ note` expanded).
- **`pymdownx.magiclink`**: Auto-links GitHub issues, pull requests, commit hashes, and URLs.
- **`pymdownx.arithmatex`**: MathJax / KaTeX LaTeX equation rendering.
- **`pymdownx.tasklist`**: Renders interactive or static task lists.
- **`markdown.extensions.admonition`**: Standard callout blocks (`!!! note`, `!!! warning`, `!!! tip`).

### 3. API Handlers & Griffe

- **`mkdocstrings-python`**: Parses Python source code statically using Griffe without executing library modules.
  - Set `enable_inventory = true` at the top-level `[project.plugins.mkdocstrings]` table to emit `site/objects.inv`.
  - Set `inherited_members = false` and `show_bases = true` on leaf classes so inherited base methods are documented once on the base class reference page.
- **`mkdocstrings-typescript`**: Optional handler extracting TypeScript/JavaScript APIs from TypeDoc JSON ASTs into the same search index.

### 4. Developer Tools & IDE Support

- **Zensical Studio**: Companion extension for VS Code, Cursor, Zed, and JetBrains IDEs. Provides configuration validation, live in-editor preview, syntax checking, and link repair.

## First-Party Companion Tooling

Maintain documentation quality and compact asset budgets using the following companion scripts:

1. **`tools/docs/generate_cli_docs.py`**:
   - Introspects Click command groups lazily via PEP 562 `__getattr__("cli")`.
   - Replaces dormant `mkdocs-click` (which fails on Click 8.3+ `Sentinel.UNSET`).
   - Strips Rich markup console tags and generates clean Markdown tables for arguments and options.
2. **`tools/docs/postbuild.py`**:
   - Compacts non-`<pre>` and non-`<textarea>` HTML indentation, saving ~40 KB per page.
   - Generates `site/llms-full.txt` (or supplements Zensical's native `[project.plugins.llmstxt]` `site/llms.txt` output) for AI agent discovery.
   - Emits flat `site/<path>.html` redirect stubs to prevent 404s on legacy `.html` links without directory collision.
3. **`tools/docs/verify_docs_artifacts.py`**:
   - Automated CI gate verifying:
     - `site/objects.inv` exists and is non-empty.
     - Reference HTML pages are `<= 120 KB`.
     - Right-hand secondary TOC contains `<= 14` items.
     - Zero internal compiler leaks (`mypyc`, `PyCapsule`, `Sentinel.UNSET`, PEP 604 `types.UnionType.__doc__`).
4. **`tools/docs/scan_public_docstrings.py`**:
   - Pre-build AST scanner ensuring every public `TypedDict` and `msgspec.Struct` field has an inline PEP 257 docstring and zero `@overload` stub docstrings.

## Theme CSS Invariants (`docs/stylesheets/extra.css`)

```css
/* 1. Wide 86rem grid with compact left & right sidebars */
.md-grid {
  max-width: 86rem;
}

@media screen and (min-width: 76.25em) {
  .md-sidebar--primary {
    width: 11rem;
  }

  /* Hide left sidebar automatically on single-page tab sections (e.g. Home) */
  .md-sidebar--primary:has(
      > .md-sidebar__scrollwrap
        > .md-sidebar__inner
        > .md-nav--primary
        > .md-nav__list
        > .md-nav__item--active.md-nav__item--section
        > .md-nav
        > .md-nav__list
        > .md-nav__item:only-child:not(.md-nav__item--nested)
    ) {
    display: none;
  }

  .md-sidebar--secondary {
    width: 10.5rem;
  }

  .md-sidebar--secondary:not([hidden]) {
    display: block;
  }
}

/* 2. Suppress redundant H1 above the Home hero banner & switch light/dark banners via [data-md-color-scheme] */
.md-typeset:has(.lv-home-hero) > h1:first-of-type {
  display: none;
}

:root:not([data-md-color-scheme="slate"]) .lv-hero-banner--dark,
[data-md-color-scheme="default"] .lv-hero-banner--dark {
  display: none !important;
}

[data-md-color-scheme="slate"] .lv-hero-banner--light {
  display: none !important;
}

/* 3. Subtle borderless non-link inline code vs. accented pill on clickable code links */
.md-typeset :not(pre) > code {
  background-color: var(--lv-inline-code-bg);
  color: var(--lv-inline-code-fg);
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 0.08em 0.32em;
}

.md-typeset a > code,
.md-typeset :not(pre) > code:has(> a:only-child) {
  background-color: var(--lv-link-code-bg);
  color: var(--lv-link-code-fg);
  border-color: var(--lv-link-code-border);
}

/* 4. High-contrast link affordance */
.md-typeset a:not(.md-button):not(.headerlink):not(:has(> code:only-child)):not(code a) {
  color: #1d4ed8;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

[data-md-color-scheme="slate"] .md-typeset a:not(.md-button):not(.headerlink):not(:has(> code:only-child)):not(code a) {
  color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

/* 5. Match top header bar with main background */
.md-header,
.md-tabs {
  background-color: var(--md-default-bg-color);
}
```

## Animated Terminal Blocks (`docs/javascripts/termynal.js` + `.lv-termynal`) & Interactive SVG Diagrams

1. **Theme-Aware Termynal Plugin (`docs/javascripts/termynal.js`)**:
   - Because arbitrary third-party MkDocs plugins (such as `termynal`) do not run natively in Zensical, register `extra_javascript = ["javascripts/termynal.js"]` in `zensical.toml` and style `.lv-termynal` in `docs/stylesheets/extra.css` using `--md-*` variables and `[data-md-color-scheme="slate"]`.
   - Place `<!-- termynal -->` immediately before any ```` ```console ```` or ```` ```bash ```` fence. The script animates command lines, comments, progress bars, and output lines on scroll via `IntersectionObserver` (respecting reduced motion preferences), provides replay and copy buttons, and rebinds on page navigation.
2. **Interactive SVG Architecture Diagrams (`tools/docs/includes/diagram-*.html`)**:
   - Store reusable SVG/CSS diagrams in `tools/docs/includes/diagram-*.html` and embed them via `--8<--`.
   - Keep node labels unnumbered and concise (at most 3 short lines per box), and keep mode/tab switcher strips on a single horizontal row (`flex-wrap: nowrap; white-space: nowrap`) without redundant `(mode="...")` parentheticals.

## Building and Verification Commands

```bash
# Clean production build with strict link/reference checks
uv run zensical build --clean --strict

# Run post-build compaction and artifact verification
uv run python -m tools.docs.postbuild
uv run python -m tools.docs.verify_docs_artifacts

# Local authoring development server (supports --dev-addr and --open)
uv run zensical serve
```
