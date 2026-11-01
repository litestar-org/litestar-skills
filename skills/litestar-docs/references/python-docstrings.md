# Python Docstrings & API Hygiene

Universal Google-style docstring conventions, type annotation rules, and inline attribute patterns compatible with both **Sphinx Autodoc + Napoleon** and **Zensical mkdocstrings (Griffe AST)**.

## Core Google-Style Rules

1. **Omit types in `Args:` and `Returns:` when PEP 484/604 annotations exist on the signature**:
   - Both Sphinx and Griffe extract signature types directly from the Python AST.
   - Repeating type names in `Args:` parameter descriptions causes drift and duplicate rendering (e.g., `param (str): description` vs `param: str`).
2. **Never attach a docstring to `@typing.overload` stubs**:
   - Both engines prioritize overload docstrings if present, leading to duplicate or fragmented documentation cards.
   - Place a single comprehensive docstring on the concrete implementation function or method.
3. **Never leak internal compiler or implementation details into public docstrings**:
   - Banned phrases: `mypyc`, `compiled C extension`, `PyCapsule`, `use_mypyc`, `Cython`, `Sentinel.UNSET`.
   - Internal optimization details belong in internal design notes, not public API contracts.

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

## Inline PEP 257 Attribute Docstrings for `TypedDict` & `msgspec.Struct`

Standard class-level `Attributes:` blocks cause critical failures across both documentation engines:

- **Sphinx Autodoc**: Renders **zero fields** for `TypedDict` or `msgspec.Struct` classes unless each field has an inline PEP 257 string literal (`"""..."""` immediately below the field assignment). Enabling `:undoc-members:` produces hundreds of empty `<dd></dd>` stub tags.
- **Zensical (Griffe)**: Renders parameters in structured tables only when inline attribute docstrings are present. Combining class-level `Attributes:` with inline docstrings renders every field twice.

### Canonical Pattern

Place a 1-sentence PEP 257 docstring immediately below every public field, and omit class-level `Attributes:` blocks:

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

```python
import msgspec


class DatabaseConfig(msgspec.Struct, frozen=True, gc=False):
    """Database runtime configuration."""

    dsn: str
    """Database connection string."""

    timeout: float = 30.0
    """Query timeout in seconds."""
```

### Inherited Fields from Private Base Types

When a public `TypedDict` inherits fields from a private `_Base*` definition:

1. Document each field on the private `_Base*` class with inline PEP 257 docstrings.
2. Under Zensical: Set `inherited_members: true` locally on the public class directive.
3. Under Sphinx: Enable `:inherited-members:` on that specific class directive.

## Type Aliases and Constant Values

### PEP 604 Union Leak Prevention

In Python 3.10 and 3.11 modules lacking `from __future__ import annotations`, assigning `Alias = A | B` creates a runtime `types.UnionType` instance whose `__doc__` is Python's internal built-in string:

```text
"Represent a PEP 604 union type — E.g. for int | str"
```

Sphinx's `.. autodata::` directive extracts and renders this internal docstring verbatim.

To prevent this:

1. In Python 3.12+, declare type aliases with the `type` keyword: `type DriverAlias = SyncDriver | AsyncDriver`.
2. In Sphinx: Use Sphinx 9 `.. autotype::` or explicit `.. py:type:: DriverAlias`.
3. For large dictionaries and configuration mappings (`SQLSTATE_MAP`, `DEFAULT_CONFIG`), always include `:no-value:` in Sphinx or set `show_source: false` in Griffe to prevent printing multi-thousand-line dictionaries.

## Compact Parameter Table Templates (Zensical)

By default, `mkdocstrings-python` renders every `TypedDict` field as an individual `<h4>` card with deep permalinks, causing 60-field configuration schemas to inflate HTML pages past 200 KB.

Custom Jinja templates in `tools/docs/templates/python/material/` (`children.html.jinja` and `attribute.html.jinja`) detect classes subclassing `TypedDict` or `msgspec.Struct` and render their fields in a single compact 3-column table (`Parameter` | `Type` | `Description`):

- Keeps Reference pages well within the `<= 120 KB` HTML cap.
- Prevents field permalinks from overwhelming the `<= 14` secondary TOC budget.

## Automated Docstring Scanner (`tools/docs/scan_public_docstrings.py`)

Run the pre-build AST scanner in CI and local Makefile targets:

```bash
uv run python -m tools.docs.scan_public_docstrings --check-leaks --check-overloads --check-typeddicts <package_name>
```

Verification assertions:

- Fails if any public docstring contains compiler leak strings (`mypyc`, `Represent a PEP 604 union type`, `Sentinel.UNSET`).
- Fails if any `@overload` stub defines a docstring.
- Fails if any public `TypedDict` or `msgspec.Struct` field lacks an inline PEP 257 docstring.
