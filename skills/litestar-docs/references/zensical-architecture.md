# Zensical Documentation Architecture

Canonical configuration, plugins, markdown extensions, and companion tooling for **Zensical Free** (`zensical >= 0.0.71`, MIT open source) + **`mkdocstrings-python` (Griffe static AST)** across Litestar repositories.

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
- **`projects`**: Workspace composition for multi-project repositories or multi-package monorepos.

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
   - Generates `site/llms.txt` and `site/llms-full.txt` for AI agent discovery.
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
/* 1. Cap reading width at 46rem (68-75ch) */
.md-content__inner {
  max-width: 46rem;
}

/* 2. Persistent left & right sidebars */
.md-sidebar {
  display: block !important;
}

/* 3. High-contrast link affordance */
.md-typeset a:not(.md-button):not(.headerlink) {
  color: #1d4ed8;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

[data-md-color-scheme="slate"] .md-typeset a:not(.md-button):not(.headerlink) {
  color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

/* 4. Match top header bar with main background */
.md-header,
.md-tabs {
  background-color: var(--md-default-bg-color);
}
```

## Building and Verification Commands

```bash
# Clean production build
uv run zensical build --clean

# Run post-build compaction and artifact verification
uv run python -m tools.docs.postbuild
uv run python -m tools.docs.verify_docs_artifacts

# Local authoring development server
uv run zensical serve
```
