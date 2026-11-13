# Sphinx Documentation Architecture

Canonical configuration, theme integration, extensions, and guardrails for Sphinx documentation projects in the Litestar ecosystem utilizing `shibuya` or `litestar-sphinx-theme`.

## Dependency Group (`pyproject.toml`)

```toml
[dependency-groups]
doc = [
  "sphinx>=9.2.0",
  "shibuya>=2026.7.12",
  "sphinx-design>=0.7.0",
  "sphinx-copybutton>=0.5.2",
  "sphinx-click>=6.2.0",
  "sphinxcontrib-mermaid>=2.1.1",
  "auto-pytabs[sphinx]>=0.5.0",
  "myst-parser>=5.2.0",
]
```

When using Litestar's branded theme package (which extends `pydata-sphinx-theme` and is distributed via GitHub rather than PyPI), replace `shibuya` with a Git dependency:

```toml
[dependency-groups]
doc = [
  "sphinx>=9.2.0",
  "litestar-sphinx-theme @ git+https://github.com/litestar-org/litestar-sphinx-theme.git",
  "sphinx-design>=0.7.0",
  "sphinx-copybutton>=0.5.2",
  "sphinx-click>=6.2.0",
  "sphinxcontrib-mermaid>=2.1.1",
  "auto-pytabs[sphinx]>=0.5.0",
  "myst-parser>=5.2.0",
]
```

## Canonical `docs/conf.py`

```python
"""Sphinx documentation configuration."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path for autodoc imports
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

project = "SQLSpec"
copyright = f"{datetime.now().year}, Litestar Organization"
author = "Litestar Organization"

# Core Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_click",
    "sphinxcontrib.mermaid",
    "auto_pytabs.sphinx_ext",
    "myst_parser",
]

# Source parser settings
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Theme Configuration (Shibuya options shown; pydata-sphinx-theme / litestar-sphinx-theme use different html_theme_options)
html_theme = "shibuya"
html_title = "SQLSpec Documentation"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "nav_links": [
        {"title": "Learn", "url": "learn/index"},
        {"title": "Databases", "url": "databases/index"},
        {"title": "Integrations", "url": "integrations/index"},
        {"title": "Reference", "url": "reference/index"},
    ],
    "github_url": "https://github.com/litestar-org/sqlspec",
    "accent_color": "amber",
}

# Autodoc & Napoleon Configuration
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}
autodoc_class_signature = "separated"
autodoc_typehints = "description"
autodoc_typehints_format = "short"

python_maximum_signature_line_length = 68
python_use_unqualified_type_names = True
python_display_short_literal_types = True

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True

# CopyButton Settings
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True
copybutton_line_continuation_character = "\\"

# Auto-pytabs Settings
auto_pytabs_min_version = (3, 10)
auto_pytabs_max_version = (3, 13)

# InterSphinx Mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "litestar": ("https://docs.litestar.dev/latest", None),
    "msgspec": ("https://msgspec.dev", None),
}

# Nitpicky Target Whitelist
nitpick_ignore = [
    ("py:class", "typing_extensions.Self"),
]
```

## Critical Sphinx & Autodoc Gotchas

### 1. Extension Conflict Resolution

Never load `numpydoc` or `sphinx_autodoc_typehints` alongside `sphinx.ext.napoleon`:

- Loading `napoleon` and `sphinx_autodoc_typehints` together causes double-parsed docstring parameter blocks and duplicates union types in both signatures and parameter lists.
- Rely on native `sphinx.ext.autodoc` + `sphinx.ext.napoleon` (`napoleon_numpy_docstring = False`, `napoleon_use_ivar = True`) with `python_maximum_signature_line_length = 68`, `python_use_unqualified_type_names = True`, and `python_display_short_literal_types = True`.

### 2. PEP 604 `types.UnionType.__doc__` Leak in `.. autodata::`

In modules without `from __future__ import annotations`, type aliases like `Alias = A | B` evaluate at import time to `types.UnionType`. Sphinx's `.. autodata:: Alias` directive renders Python's internal docstring verbatim:

```text
"Represent a PEP 604 union type — E.g. for int | str"
```

Resolution:

- In Python 3.12+, define aliases using the `type` statement (`type Alias = A | B`) and Sphinx 9 `.. autotype::` (or explicit `.. py:type:: Alias`).
- On large module constants and dictionary maps (`SQLSTATE_MAP`, `DEFAULT_CONFIG`), always pass the `:no-value:` flag to avoid dumping huge unreadable data structures into the documentation.

### 3. `TypedDict` & `msgspec.Struct` Field Invisibility

Sphinx `autoclass` introspects `TypedDict` and `msgspec.Struct` classes via runtime attributes:

- Fields without an inline PEP 257 string literal (`"""..."""` immediately below the field assignment) render **zero fields** under Sphinx `autoclass`.
- Do **not** attempt to fix this by enabling `:undoc-members:`, which generates hundreds of empty `<dd></dd>` stub tags.
- Document every field on public `TypedDict` and `msgspec.Struct` definitions with an inline PEP 257 docstring.

### 4. Directives and Cross-Reference Anchors

- **Never place `:no-index:` on primary `.. automodule::` directives**: `:no-index:` strips all HTML `id=""` anchors from public classes, breaking `:class:` and `:meth:` cross-references site-wide.
- **Avoid pairing `autodoc_class_signature = "separated"` with `special-members: __init__`**: This causes constructors to render twice on the class reference page.
- **For Click CLIs**: Always use `sphinx-click` (`.. click:: <module>:<group>\n   :prog: <command>\n   :nested: full`) rather than `automodule`, which renders empty pages for Click command groups.

## Theme CSS Invariants (`docs/_static/custom.css`)

Maintain readability and scannability by applying these CSS invariants to **Shibuya** (for `litestar-sphinx-theme` / `pydata-sphinx-theme`, apply the corresponding rules to `.bd-sidebar-secondary`, `.bd-article-container`, and `[data-theme="dark"]`):

```css
/* 1. Never hide the secondary "On this page" TOC */
.sy-rside {
  display: block !important;
  visibility: visible !important;
}

/* 2. Cap reading measure at 46rem (68-75ch) */
.sy-content {
  max-width: 46rem !important;
  margin-inline: auto;
}

/* 3. High-contrast sapphire link affordance */
.sy-content a:not(.headerlink):not(.sd-btn) {
  color: #1d4ed8;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

[data-theme="dark"] .sy-content a:not(.headerlink):not(.sd-btn) {
  color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

/* 4. Brand harmony: 10% intentional accent */
.sy-head-brand .sy-brand-text {
  font-weight: 700;
}
```

## Building and Verification Commands

Execute Sphinx builds with warning escalation enabled to prevent documentation rot:

```bash
# Clean build with warnings treated as errors
uv run sphinx-build -b html -W --keep-going docs site

# Interactive autobuild server for local authoring
uv run sphinx-autobuild docs site --port 8000 --watch <package_name>
```
