---
name: polyfactory
description: "Auto-activate for polyfactory imports, ModelFactory, DataclassFactory, MsgspecFactory, AttrsFactory, Use, Fixture, register_fixture, polyfactory.pytest_plugin, __random_seed__, or coverage(). Use when generating typed mock data for tests or pytest fixtures. Not for production seeding or property-based testing."
---

# polyfactory

Polyfactory is a typed mock-data factory library: declare `ModelFactory[T]` (or `DataclassFactory`, `MsgspecFactory`, `AttrsFactory`, `TypedDictFactory`) and `.build()` returns a fully-populated, validation-passing instance of `T`. Because the factory inspects the model's annotations and constraints, generated data already respects `msgspec.Meta` ranges, Pydantic `Field` constraints, and attrs validators — no additional fixtures needed for happy-path tests.

In Litestar projects, polyfactory's pytest plugin is the canonical way to feed `TestClient.post(...)` / `AsyncTestClient.put(...)` payloads. The companion skill `litestar:litestar-testing` covers the request side.

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`.
- **`from __future__ import annotations` rule** — Modules that **define** factory subclasses with introspected `Meta` config (`__model__`, `__random_seed__`, `__set_as_default_factory_for_type__`) are library-like and SHOULD avoid future annotations on the factory module itself if the model class is also defined there. Test modules that *use* factories (call `.build()`, register fixtures) MAY and typically SHOULD use future annotations — they are pure consumer code. The same rule applies as msgspec/dishka/SAQ.
- One factory per model. Don't reuse a factory across unrelated models — clarity beats DRY when the test fails at 3am.
- Pick the right factory base by backend: `ModelFactory` (Pydantic), `DataclassFactory`, `MsgspecFactory`, `AttrsFactory`, `TypedDictFactory`. The wrong base silently degrades to attribute-by-attribute introspection and produces lower-quality data.
- Prefer `register_fixture` over hand-rolled `@pytest.fixture` wrappers — it gives you both the fixture and the factory class with one decorator.

## Quick Reference

### Picking the right factory base

| Model kind | Factory base | Import |
| --- | --- | --- |
| `pydantic.BaseModel` | `ModelFactory` | `from polyfactory.factories.pydantic_factory import ModelFactory` |
| `@dataclass` | `DataclassFactory` | `from polyfactory.factories import DataclassFactory` |
| `msgspec.Struct` | `MsgspecFactory` | `from polyfactory.factories.msgspec_factory import MsgspecFactory` |
| `@attrs.define` / `attr.s` | `AttrsFactory` | `from polyfactory.factories.attrs_factory import AttrsFactory` |
| `TypedDict` | `TypedDictFactory` | `from polyfactory.factories.typed_dict_factory import TypedDictFactory` |
| Beanie / Odmantic / SQLA | dedicated bases | see [factories.md](references/factories.md) |

### Defining a factory

```python
from dataclasses import dataclass
from polyfactory.factories import DataclassFactory


@dataclass
class Order:
    id: int
    customer_email: str
    total_cents: int
    status: str


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order


# Use it
one = OrderFactory.build()
many = OrderFactory.batch(10)
```

`build()` returns a single populated instance. `batch(n)` returns `list[T]` of size `n`. `coverage()` yields one instance per Union/Optional branch — useful for parametrized tests across discriminated unions.

### Customizing fields

```python
from polyfactory import Use
from polyfactory.factories import DataclassFactory


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order

    # Plain literal — every build returns this exact value
    status = "pending"

    # Callable — re-evaluated per build
    customer_email = Use(lambda: "test@example.com")

    # Random choice — re-evaluated per build
    total_cents = Use(DataclassFactory.__random__.randint, 100, 10_000)
```

`Use(callable, *args, **kwargs)` is re-invoked on every `build()`, so each generated instance gets a fresh value.

### Determinism

```python
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    __random_seed__ = 42  # same seed → same output across runs
```

Set `__random_seed__` (or `__faker__ = Faker(seed=...)` for finer Faker control) when test assertions depend on the exact generated values.

### Default factory registration

```python
class CustomerFactory(DataclassFactory[Customer]):
    __model__ = Customer
    __set_as_default_factory_for_type__ = True


@dataclass
class Order:
    id: int
    customer: Customer  # automatically populated by CustomerFactory.build()


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
```

When `__set_as_default_factory_for_type__ = True`, polyfactory uses that factory whenever the type appears as a field on another model — no manual nesting required.

### Pytest fixture from a factory

```python
import pytest
from polyfactory.pytest_plugin import register_fixture
from polyfactory.factories import DataclassFactory


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order


def test_order_total(order_factory: OrderFactory) -> None:
    order = order_factory.build()
    assert order.total_cents >= 0
```

`@register_fixture` turns the class into a pytest fixture (snake-cased class name). The factory itself is still importable as `OrderFactory` for use outside fixtures.

### Cross-referencing fixtures

```python
import pytest
from polyfactory import Fixture
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class CustomerFactory(DataclassFactory[Customer]):
    __model__ = Customer


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    customer = Fixture(CustomerFactory)  # pull from the customer fixture
```

`Fixture(OtherFactory)` forwards to another registered factory, making cross-model wiring explicit.

<workflow>

## Workflow

### Step 1: Pick the factory base

Match the base to your model backend (table above). Wrong base = silent degradation to generic attribute introspection. If your project uses multiple backends (e.g., Pydantic for HTTP DTOs + msgspec for internal events), import each base separately and don't try to share a factory across backends.

### Step 2: Define one factory per model

Subclass the appropriate base, set `__model__`. Keep the factory adjacent to the test files that consume it — typically `tests/factories.py` or `tests/<feature>/factories.py`. Don't put factories in production code paths.

### Step 3: Customize only what the test cares about

If a field can take any valid value, leave it for the factory to randomize. Override (literal value or `Use(...)`) only fields the assertion depends on. Tests that pin every field defeat the purpose of using a factory.

### Step 4: Register as a pytest fixture (if used widely)

For factories used in many tests, decorate with `@register_fixture` and consume via the snake-cased fixture name. For one-off use, call `Factory.build()` directly inline.

### Step 5: Wire cross-model relationships

Set `__set_as_default_factory_for_type__ = True` on a base factory and let nested fields be populated automatically, or use `Fixture(OtherFactory)` to forward to a registered fixture explicitly.

### Step 6: Pin determinism only when needed

Tests that assert on specific generated values need `__random_seed__`. Tests that assert on shape or invariants (e.g., `total >= 0`) should not — leaving randomization on widens coverage across runs.

</workflow>

<guardrails>

## Guardrails

- **Always set `__model__`.** The factory base reads `__model__` to introspect annotations; without it `.build()` errors at runtime, not at class definition.
- **Don't override fields you're about to assert on with random values.** Either pin the value (`status = "pending"`) or assert on shape, not both.
- **Don't reuse `__random_seed__` across factories that share a Faker instance.** They will collide and produce unexpected duplicates. Use a different seed per factory or a single shared seeded `__faker__`.
- **Use the right base for the backend.** `ModelFactory` on a `msgspec.Struct` falls back to generic introspection and can produce values that violate `Meta` constraints. Always use `MsgspecFactory` for msgspec.
- **Factories belong under `tests/`.** Importing them from production modules ties test data to runtime code and is a refactor hazard.
- **`coverage()` is a parametrize tool, not a build tool.** It returns one instance per Union/Optional branch, not per field — use it via `pytest.mark.parametrize` to fan out test cases over polymorphic shapes.
- **`from __future__ import annotations`** — same rule as msgspec / dishka. The module that *defines* the factory + model SHOULD avoid future annotations if the model is runtime-introspected. Test modules that *use* factories MAY freely use future annotations.

</guardrails>

<validation>

## Validation Checkpoint

Before delivering polyfactory code, verify:

- [ ] Factory base matches the model backend (Pydantic → `ModelFactory`, dataclass → `DataclassFactory`, msgspec → `MsgspecFactory`, attrs → `AttrsFactory`).
- [ ] `__model__` is set on every factory subclass.
- [ ] Factories live under `tests/` (or a sibling test-only module), never in production code.
- [ ] Fields overridden in the factory match what the test asserts on; fields the test does not care about are left for randomization.
- [ ] If the test asserts on exact values, `__random_seed__` is set; otherwise it is not.
- [ ] `@register_fixture` is used for factories shared across more than ~2 test files; one-offs call `.build()` inline.
- [ ] Cross-model relationships use `__set_as_default_factory_for_type__` or `Fixture(OtherFactory)` (not manual nesting in `Use(...)`).
- [ ] Factory module avoids `from __future__ import annotations` if and only if it co-defines runtime-introspected model classes.

</validation>

<example>

## Example: Litestar handler test with msgspec DTOs and polyfactory

```python
# tests/factories.py
from polyfactory.factories.msgspec_factory import MsgspecFactory
from polyfactory.pytest_plugin import register_fixture

from myapp.events import OrderCreatedEvent  # msgspec.Struct


@register_fixture
class OrderCreatedEventFactory(MsgspecFactory[OrderCreatedEvent]):
    __model__ = OrderCreatedEvent
```

```python
# tests/test_orders.py
from __future__ import annotations  # consumer module — fine to use future annotations

from litestar.testing import AsyncTestClient

import pytest


@pytest.mark.anyio
async def test_create_order_emits_event(
    client: AsyncTestClient,
    order_created_event_factory: OrderCreatedEventFactory,
) -> None:
    payload = order_created_event_factory.build()
    response = await client.post("/orders", json=payload)

    assert response.status_code == 201
    assert response.json()["id"] == payload.id
```

The factory provides a fully-populated, validation-passing `OrderCreatedEvent`; the test focuses on the request/response contract instead of constructing fake data inline.

</example>

---

## References Index

For detailed guides, refer to the following documents in `references/`:

- **[Factories](references/factories.md)** — Per-backend factory bases (Pydantic / dataclass / msgspec / attrs / TypedDict / ODM), randomization control (`__random_seed__`, `__faker__`, `__allow_none_optionals__`), `__set_as_default_factory_for_type__` defaults, dynamic factories via `Factory.create_factory`, `coverage()` for discriminated unions.
- **[Pytest integration](references/pytest-integration.md)** — `@register_fixture`, `Fixture(...)` cross-references, fixture scoping, the `polyfactory.pytest_plugin` module, async fixtures, and the difference between class-decorator and function-decorator forms.
- **[Litestar patterns](references/litestar-patterns.md)** — Using factories with `TestClient` / `AsyncTestClient`, parametrizing handler tests via `coverage()`, integrating with `litestar-testing` fixtures, msgspec DTOs, advanced-alchemy model factories, and SAQ task payload generation.

---

## Official References

- <https://polyfactory.litestar.dev/>
- <https://polyfactory.litestar.dev/usage/index.html>
- <https://polyfactory.litestar.dev/usage/library_factories/index.html>
- <https://polyfactory.litestar.dev/usage/decorators.html>
- <https://polyfactory.litestar.dev/usage/fixtures.html>
- <https://polyfactory.litestar.dev/usage/configuration.html>
- <https://github.com/litestar-org/polyfactory>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
