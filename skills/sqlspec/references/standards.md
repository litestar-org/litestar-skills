# SQLSpec Code Quality Standards & Mypyc Patterns

## MANDATORY Code Quality Standards

### Type Annotation Rules

Stringified type hints for non-builtins and built-in generics without `__future__.annotations` in core/driver code:

```python
def process_config(config: "SQLConfig") -> "SessionResult": ...


def get_value(key: str) -> str | None: ...


def get_items() -> "list[str]": ...


__all__ = ("CONSTANT", "MyClass", "my_function")
```

### Import Standards

Order: stdlib -> third-party -> first-party. Use `TYPE_CHECKING` for type-only imports:

```python
import logging
from typing import TYPE_CHECKING, Any

from sqlglot import exp

from sqlspec.core.result import SQLResult
from sqlspec.protocols import HasWhereProtocol

if TYPE_CHECKING:
    from sqlspec.core.statement import SQL
```

**Rules:**

- ALL imports at module level by default
- ONLY nest imports for circular import prevention
- Third-party packages may be nested for optional dependencies only

### Function Length & Style

- **Maximum**: 75 lines per function (including docstring)
- **Preferred**: 30-50 lines
- Use early returns over nested conditionals
- Place guard clauses at function start
- No inline comments - use docstrings
- Google-style docstrings with Args, Returns, Raises sections

### Testing Standards

Use function-based tests:

```python
def test_config_validation():
    config = AsyncpgConfig(connection_config={"dsn": "postgresql://..."})
    assert config.is_async is True
```

Do not use class-based tests.

**Guidelines:**

- Use `pytest-databases` service fixtures (`postgres_service`, etc.) instead of infra scripts.
- Keep fixtures session-scoped where possible to avoid container churn.
- Use `pytest-xdist` for parallelism.
- **Avoid `:memory:` for pooling tests**: Use `tempfile.NamedTemporaryFile` to isolate databases.

### Type Guards Pattern

Use guards from `sqlspec.utils.type_guards` instead of `hasattr()`:

```python
from sqlspec.utils.type_guards import supports_where

if supports_where(obj):
    result = obj.where("condition")
```

Available type guards: `is_readable`, `has_array_interface`, `has_cursor_metadata`, `has_expression_and_sql`, `has_expression_and_parameters`, `is_statement_filter`

---

## Mypyc-Compatible Class Pattern

For data-holding classes in `sqlspec/core/` and `sqlspec/driver/`:

```python
class MyMetadata:
    __slots__ = ("field1", "field2", "optional_field")

    def __init__(self, field1: str, field2: int, optional_field: str | None = None) -> None:
        self.field1 = field1
        self.field2 = field2
        self.optional_field = optional_field

    def __repr__(self) -> str:
        return f"MyMetadata(field1={self.field1!r}, field2={self.field2!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MyMetadata):
            return NotImplemented
        return self.field1 == other.field1 and self.field2 == other.field2

    def __hash__(self) -> int:
        return hash((self.field1, self.field2, self.optional_field))
```

**Key Principles:**

- `__slots__` reduces memory and speeds up attribute access
- Explicit `__init__`, `__repr__`, `__eq__`, `__hash__`
- Avoid `@dataclass` decorators in mypyc-compiled modules

### Mypyc-Compatible Dataclass with Factory Method

When using `@dataclass` with a `@classmethod` factory that references defaults, use module-level `Final` constants:

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

_DEFAULT_MAX_RETRIES: Final[int] = 10
_DEFAULT_BASE_DELAY_MS: Final[float] = 50.0
_DEFAULT_ENABLE_LOGGING: Final[bool] = True


@dataclass(frozen=True)
class RetryConfig:
    """Configuration with factory method pattern."""

    max_retries: int = _DEFAULT_MAX_RETRIES
    base_delay_ms: float = _DEFAULT_BASE_DELAY_MS
    enable_logging: bool = _DEFAULT_ENABLE_LOGGING

    @classmethod
    def from_features(cls, driver_features: "Mapping[str, Any]") -> "RetryConfig":
        """Build config from driver features dict."""
        return cls(
            max_retries=int(driver_features.get("max_retries", _DEFAULT_MAX_RETRIES)),
            base_delay_ms=float(driver_features.get("retry_delay_base_ms", _DEFAULT_BASE_DELAY_MS)),
            enable_logging=bool(driver_features.get("enable_retry_logging", _DEFAULT_ENABLE_LOGGING)),
        )
```

**Why this pattern:**

- Mypyc error: "Cannot access instance attribute through class object" when using `cls.max_retries`
- `Final` tells mypyc the value is a compile-time constant, enabling inlining
- Module-level constants provide single source of truth

### Mypyc-Incompatible Protocol Patterns

Avoid `@runtime_checkable` on Protocol classes in mypyc-compiled modules when isinstance checks are not needed:

```python
from typing import Protocol


class MyProtocol(Protocol):
    def method(self) -> None: ...
```

**When to use `@runtime_checkable`:**

- Only when you need `isinstance(obj, MyProtocol)` checks at runtime
- If no isinstance checks exist, remove the decorator for mypyc compatibility
