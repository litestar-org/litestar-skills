# Pytest integration

Polyfactory ships a pytest plugin that turns factory classes into pytest fixtures. The plugin is loaded automatically when polyfactory is on the path — no `pytest_plugins = [...]` entry is required in most setups.

## `@register_fixture` — the canonical decorator

```python
from polyfactory.factories import DataclassFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order


def test_order(order_factory: OrderFactory) -> None:
    order = order_factory.build()
    assert order.id > 0
```

What happens:

1. `OrderFactory` remains a regular factory class — importable, usable directly via `OrderFactory.build()`.
2. A pytest fixture named `order_factory` (snake-case of the class name) is registered.
3. The fixture *yields the factory class itself*, not an instance. Call `.build()` / `.batch()` on the fixture to get model instances.

This dual nature — factory + fixture — is why the decorator is preferred over hand-rolling `@pytest.fixture` wrappers.

## Naming

Snake-case conversion: `OrderFactory` → `order_factory`, `OrderItemFactory` → `order_item_factory`, `HTTPSessionFactory` → `http_session_factory`. To override, pass `name=`:

```python
@register_fixture(name="orders")
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order


def test_x(orders: OrderFactory) -> None:
    ...
```

## Scope

Default scope is `"function"`. Override with `scope=`:

```python
@register_fixture(scope="session")
class CustomerFactory(DataclassFactory[Customer]):
    __model__ = Customer
```

Session-scoped factories are common for read-only test data shared across many tests. Function-scoped is the default and the right choice when factories produce data that flows into a database with per-test cleanup.

## Cross-model wiring

When one factory's field should use another factory, prefer default factory registration:

```python
from polyfactory import Use
from polyfactory.factories import DataclassFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class CustomerFactory(DataclassFactory[Customer]):
    __model__ = Customer
    __set_as_default_factory_for_type__ = True


@register_fixture
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    customer = Use(CustomerFactory.build)
```

Use `__set_as_default_factory_for_type__ = True` when the same nested factory should be used broadly. Use `Use(CustomerFactory.build)` when one parent factory needs an explicit local override.

## Function-decorator form

For simple cases, decorate a factory-returning function:

```python
@pytest.fixture
def special_order_factory() -> type[OrderFactory]:
    class SpecialOrderFactory(OrderFactory):
        status = "expedited"

    return SpecialOrderFactory


def test_special_order(special_order_factory: type[OrderFactory]) -> None:
    order = special_order_factory.build()
    assert order.status == "expedited"
```

This is plain pytest with no polyfactory decorator — useful when the factory is a one-off subclass parameterized by other fixtures.

## Async factories

For async ODMs (Beanie, Odmantic) where build is async:

```python
from polyfactory.factories.beanie_odm_factory import BeanieDocumentFactory
from polyfactory.pytest_plugin import register_fixture


@register_fixture
class UserFactory(BeanieDocumentFactory[User]):
    __model__ = User


@pytest.mark.anyio
async def test_user(user_factory: UserFactory) -> None:
    user = await user_factory.build_async()
    assert user.id is not None
```

Use `build_async()` instead of `build()`; the async factory handles awaitable defaults and async validators correctly.

## When NOT to register as a fixture

- Factories used in exactly one test — call `.build()` inline; the indirection isn't worth it.
- Factories used to seed data outside test bodies (conftest setup, CLI scripts) — register as a regular pytest fixture only if the seeding happens during a test.

## Plugin discovery

The plugin is registered as a pytest entry point. If you see `register_fixture` apparently doing nothing, verify polyfactory is installed in the same environment as pytest (`uv pip list | grep polyfactory`) and that no `conftest.py` has explicitly disabled it. Pinning `pytest_plugins = ["polyfactory.pytest_plugin"]` in `conftest.py` is supported but redundant in most setups.

## Interaction with parametrize

`@pytest.mark.parametrize` runs once per parameter — call the fixture inside the test body, not at parametrize-time:

```python
@pytest.mark.parametrize("status", ["pending", "paid", "shipped"])
def test_order_status_transitions(order_factory: OrderFactory, status: str) -> None:
    order = order_factory.build(status=status)
    ...
```

Don't try to `parametrize` over `OrderFactory.coverage()` results outside the test — the factory hasn't been instantiated yet at collection time. Either call `coverage()` inside the test body, or generate the list at module-level (not via the fixture):

```python
@pytest.mark.parametrize("contact", list(ContactFactory.coverage()))
def test_contact_dispatch(contact: Contact) -> None:
    ...
```
