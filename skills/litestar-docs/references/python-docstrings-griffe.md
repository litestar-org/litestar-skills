# Python Docstrings & Griffe Rendering

Google-style docstring conventions and custom Jinja templates for **`mkdocstrings-python` (Griffe static AST)**.

## Core Google-Style Rules for Griffe

1. **Omit types in `Args:` and `Returns:` when PEP 484/604 type annotations exist on the signature.** Reason: Griffe reads type annotations directly from the AST; repeating types in `Args:` causes drift and redundant rendering.
2. **Never attach a docstring to `@typing.overload` stubs.** Reason: Griffe renders `@overload` docstrings above the implementation docstring, duplicating descriptions for every overload variant. Place the single comprehensive docstring on the concrete implementation function or method.
3. **Never leak internal compiler or ABI details into public docstrings.** Reason: phrases such as `mypyc`, `compiled C extension`, `PyCapsule`, `use_mypyc`, or `Cython` belong in contributor architecture notes, not consumer-facing API docs.

```python
from typing import overload


@overload
def fetch_value(key: str) -> str: ...


@overload
def fetch_value(key: str, default: int) -> str | int: ...


def fetch_value(key: str, default: int | None = None) -> str | int | None:
    """Fetch a configuration value by key.

    Args:
        key: Configuration lookup key.
        default: Fallback value returned when ``key`` is absent.

    Returns:
        Resolved value or ``default``.
    """
    return default
```

## Inline PEP 257 Attribute Docstrings for `TypedDict` and `msgspec.Struct`

Griffe does **not** synthesize parameter tables from bare `TypedDict` or `msgspec.Struct` field annotations unless each field has an inline PEP 257 string literal immediately below the field assignment:

- **Every field on a public `TypedDict` (`*ConnectionParams`, `*PoolParams`, `*DriverFeatures`, framework config `TypedDict`s) must have a concise 1-sentence PEP 257 docstring immediately below the field.**
- **Omit duplicate class-level `Attributes:` sections on `TypedDict` classes.** Reason: combining a class-level `Attributes:` table with per-field inline docstrings renders every field twice on the Reference page.
- **When a public `TypedDict` inherits fields from a private `_Base*` `TypedDict`**, document every field on the private `_Base*` `TypedDict` as well and set `inherited_members: true` on the primary public subclass block in the Reference Markdown file.

```python
from typing import NotRequired, TypedDict


class AsyncpgPoolParams(TypedDict, total=False):
    """Pool configuration parameters for AsyncPG."""

    min_size: NotRequired[int]
    """Minimum number of connections maintained in the pool."""

    max_size: NotRequired[int]
    """Maximum number of connections allowed in the pool."""

    max_inactive_connection_lifetime: NotRequired[float]
    """Seconds before an idle connection is closed and replaced."""
```

## Compact 3-Column `TypedDict` Table Templates (`tools/docs/templates/python/material/`)

By default, `mkdocstrings-python` renders every `TypedDict` field as a full `<div class="doc doc-object doc-attribute">` card with an `<h4>` heading and permalink, inflating 60-field connection `TypedDict`s (`OracleConnectionParams`, `AsyncpgConnectionConfig`) past `160 KB` of HTML.

Override `tools/docs/templates/python/material/` (`children.html.jinja` and `attribute.html.jinja`) so classes whose bases include `TypedDict` (or whose names end in `Params`, `Config`, or `Features` with attribute-only members) render their attributes inside a single compact 3-column Markdown/HTML table (`Parameter` | `Type` | `Description`) instead of 60 individual `<h4>` cards:

- Reduces `site/reference/adapters/oracledb/index.html` from `>240 KB` to `~101 KB` (`<= 120 KB` cap).
- Keeps `"On this page"` TOC items `<= 14` per Reference page.

## Automated Public Docstring Scanner (`tools/docs/scan_public_docstrings.py`)

Run `uv run python -m tools.docs.scan_public_docstrings --check-leaks --check-overloads --check-typeddicts <pkg>` in `Makefile` `docs` and PR CI to fail automatically when:

- Any public class, function, or method docstring matches forbidden compiler/internal leak patterns (`mypyc`, `PyCapsule`, `Represent a PEP 604 union type`, `Sentinel.UNSET`)
- Any `@overload` stub defines a docstring
- Any public `TypedDict` class has undocumented fields or a duplicate class-level `Attributes:` block
