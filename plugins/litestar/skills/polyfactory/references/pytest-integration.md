# Pytest integration

Polyfactory exposes `register_fixture`, which injects a pytest fixture into the caller's module. Invoke it in a test module or `conftest.py` that pytest collects. Installing Polyfactory alone does not register factory classes automatically.

## `@register_fixture` — the canonical decorator

```python
from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    pass


def test_order(order_factory: type[OrderFactory]) -> None:
    order = order_factory.build()
    assert order.id > 0
```

What happens:

1. `OrderFactory` remains a regular factory class — importable, usable directly via `OrderFactory.build()`.
2. A pytest fixture named `order_factory` (snake-case of the class name) is registered.
3. The fixture returns the factory class itself, not an instance. Call `.build()` / `.batch()` on the fixture to get model instances.

This dual nature — factory + fixture — is why the decorator is preferred over hand-rolling `@pytest.fixture` wrappers.

## Naming

Snake-case conversion: `OrderFactory` → `order_factory`, `OrderItemFactory` → `order_item_factory`, `HTTPSessionFactory` → `http_session_factory`. To override, pass `name=`:

```python
@register_fixture(name="orders")
class OrderFactory(DataclassFactory[Order]):
    pass


def test_x(orders: type[OrderFactory]) -> None: ...
```

## Scope and autouse

Default `scope` is `"function"` and `autouse` is `False`. Override either on `@register_fixture(scope=..., autouse=..., name=...)`:

```python
@register_fixture(scope="session", autouse=False)
class CustomerFactory(DataclassFactory[Customer]):
    pass
```

The fixture returns a class, and each `.build()` still creates new model data. Keep function scope unless another fixture explicitly requires a broader dependency scope.

## Cross-model wiring

When one factory's field should use another factory, prefer default factory registration:

```python
from polyfactory import Use
from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class CustomerFactory(DataclassFactory[Customer]):
    __set_as_default_factory_for_type__ = True


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    customer = Use(CustomerFactory.build)
```

Use `__set_as_default_factory_for_type__ = True` when the same nested factory should be used broadly. Use `Use(CustomerFactory.build)` when one parent factory needs an explicit local override.

## Registering separately

Call `register_fixture()` after the class definition when the factory and pytest registration live in different modules:

```python
from polyfactory.pytest_plugin import register_fixture

from tests.factories import OrderFactory


register_fixture(OrderFactory, name="orders")


def test_order(orders: type[OrderFactory]) -> None:
    assert orders.build().id > 0
```

The call injects `orders` into the current module, so place it at module scope in a pytest-discovered file. `register_fixture` accepts only `BaseFactory` subclasses and raises `ParameterException` otherwise.

## Async persistence

Async factory methods build and persist instances. They require an async persistence handler; `BeanieDocumentFactory` supplies one:

```python
import pytest

from polyfactory.factories.beanie_odm_factory import BeanieDocumentFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class UserFactory(BeanieDocumentFactory[User]):
    pass


@pytest.mark.anyio
async def test_user(user_factory: type[UserFactory]) -> None:
    user = await user_factory.create_async()
    assert user.id is not None
```

Polyfactory has no `build_async()`. Use `build()` for in-memory construction and `create_async()` / `create_batch_async()` only for configured persistence.

## When NOT to register as a fixture

- Factories used in exactly one test — call `.build()` inline; the indirection isn't worth it.
- Factories used to seed data outside test bodies (conftest setup, CLI scripts) — register as a regular pytest fixture only if the seeding happens during a test.

## Collection boundary

`register_fixture` writes the pytest fixture into the caller's global namespace. Calling it from an ordinary helper module does not make pytest collect that module. Decorate in the test module, or import the factory into `conftest.py` and call `register_fixture(Factory)` there.

## Interaction with parametrize

`@pytest.mark.parametrize` runs once per parameter — call the fixture inside the test body, not at parametrize-time:

```python
@pytest.mark.parametrize("status", ["pending", "paid", "shipped"])
def test_order_status_transitions(order_factory: type[OrderFactory], status: str) -> None:
    order = order_factory.build(status=status)
    ...
```

Factory methods are class methods, so module-level coverage generation is valid without fixture setup:

```python
@pytest.mark.parametrize("contact", list(ContactFactory.coverage()))
def test_contact_dispatch(contact: Contact) -> None: ...
```
