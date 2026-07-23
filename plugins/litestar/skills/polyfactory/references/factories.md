# Factories

Reference for picking and configuring factory bases. The factory base owns *how* a model is introspected — match it to the model's backend or factory creation fails.

## Per-backend factory bases

| Model kind | Factory base | Module |
| --- | --- | --- |
| `pydantic.BaseModel` (v1 or v2) | `ModelFactory[T]` | `polyfactory.factories.pydantic_factory` |
| `@dataclass` (stdlib) | `DataclassFactory[T]` | `polyfactory.factories` |
| `msgspec.Struct` | `MsgspecFactory[T]` | `polyfactory.factories.msgspec_factory` |
| `@attrs.define` / `attr.s` | `AttrsFactory[T]` | `polyfactory.factories.attrs_factory` |
| `TypedDict` | `TypedDictFactory[T]` | `polyfactory.factories.typed_dict_factory` |
| Beanie `Document` | `BeanieDocumentFactory[T]` | `polyfactory.factories.beanie_odm_factory` |
| Odmantic `Model` | `OdmanticModelFactory[T]` | `polyfactory.factories.odmantic_odm_factory` |
| SQLAlchemy declarative | `SQLAlchemyFactory[T]` | `polyfactory.factories.sqlalchemy_factory` |

A mismatched base raises `ConfigurationException` during factory class creation. Always match the backend.

## The basic pattern

```python
from dataclasses import dataclass

from polyfactory.factories import DataclassFactory


@dataclass
class Widget:
    name: str


class WidgetFactory(DataclassFactory[Widget]):
    pass
```

Polyfactory infers `__model__` when the factory has exactly one concrete generic model argument. Set `__model__` explicitly for an unparameterized concrete factory or when multiple generic bases make inference ambiguous. Missing or unsupported models raise `ConfigurationException` during class creation.

## Build helpers

| Method | Returns | Use case |
| --- | --- | --- |
| `Factory.build(**overrides)` | one `T` | most tests |
| `Factory.batch(n, **overrides)` | `list[T]` of length `n` | list-handler tests, repository smoke tests |
| `Factory.coverage(**overrides)` | iterator over `T` | minimal representative coverage of supported variants |
| `Factory.create_sync(**overrides)` | persisted `T` | requires `__sync_persistence__` |
| `Factory.create_batch_sync(n, **overrides)` | persisted `list[T]` | requires `__sync_persistence__` |
| `Factory.create_async(**overrides)` | persisted `T` | requires `__async_persistence__` |
| `Factory.create_batch_async(n, **overrides)` | persisted `list[T]` | requires `__async_persistence__` |

`build()` accepts keyword overrides (`OrderFactory.build(status="paid")`) — useful for one-off variations without subclassing.
There is no `build_async()`: the async methods build synchronously, then await a configured persistence handler.

## Field customization

### Literal pin

```python
class OrderFactory(DataclassFactory[Order]):
    status = "pending"  # every build produces status="pending"
```

A class attribute with a non-callable value pins the field to that literal across all builds.

### `Use(callable, *args, **kwargs)`

Re-evaluated on every `build()`:

```python
from polyfactory import Use


class OrderFactory(DataclassFactory[Order]):
    total_cents = Use(DataclassFactory.__random__.randint, 100, 10_000)
    customer_email = Use(lambda: f"user-{DataclassFactory.__random__.randint(1, 999)}@example.com")
```

`Use(fn, *args, **kwargs)` calls `fn(*args, **kwargs)` per build. Access the factory's seeded `Random` via `Factory.__random__` so values stay deterministic when `__random_seed__` is set.

### `PostGenerated(callable)`

Field generators that depend on values already produced for the same instance:

```python
from polyfactory import PostGenerated


def _slug_from_title(name: str, values: dict[str, object]) -> str:
    return str(values["title"]).lower().replace(" ", "-")


class ArticleFactory(DataclassFactory[Article]):
    slug = PostGenerated(_slug_from_title)
```

The callback signature is `(field_name, generated_values, *args, **kwargs)`. The second argument maps all non-post-generated fields by name. Use it when one field derives from another.

## Default factory registration

Polyfactory looks up nested-field factories by type. Setting `__set_as_default_factory_for_type__ = True` makes a factory the default for its model whenever that model appears as a nested field on another model:

```python
class CustomerFactory(DataclassFactory[Customer]):
    __set_as_default_factory_for_type__ = True


class OrderFactory(DataclassFactory[Order]):
    # Order.customer: Customer is automatically populated via CustomerFactory.build()
    pass
```

Without the default flag, polyfactory introspects the nested type generically — fine for simple types, but loses any field overrides defined on `CustomerFactory`.

## Determinism

### Per-factory seed

```python
class OrderFactory(DataclassFactory[Order]):
    __random_seed__ = 42
```

Re-running the test with the same seed produces identical instances — set this when assertions check exact generated values.

### Per-factory Faker

```python
from faker import Faker


class OrderFactory(DataclassFactory[Order]):
    __faker__ = Faker(locale="en_US")
    __faker__.seed_instance(42)
```

Use a custom `Faker` to control locale (regional names, addresses) or to share a single seeded Faker across multiple factories.

### Optional and default values

`__allow_none_optionals__` is a boolean and defaults to `True`. When true, `build()` randomly chooses between `None` and the wrapped type. Set it to `False` to always populate optional fields.

```python
class OrderFactory(DataclassFactory[Order]):
    __allow_none_optionals__ = False
```

Set `__use_defaults__ = True` to use model field defaults instead of generating replacements. It defaults to `False` and does not apply to `TypedDictFactory`.

### `__check_model__`

This defaults to `True` in Polyfactory 3. It rejects `Use`, `PostGenerated`, `Ignore`, and `Require` declarations whose names do not exist on the model. It does not run a second model-validation pass.

## Dynamic factory creation

Build a factory class at runtime from a model:

```python
from polyfactory.factories import DataclassFactory


WidgetFactory = DataclassFactory.create_factory(Widget)
instance = WidgetFactory.build()
```

`create_factory(Type)` synthesizes a factory subclass without writing a class body — useful for table-driven tests that iterate over model types.

## `coverage()` for discriminated unions

```python
@dataclass
class Email:
    address: str


@dataclass
class Phone:
    number: str


@dataclass
class Contact:
    method: Email | Phone


class ContactFactory(DataclassFactory[Contact]):
    pass


# Yields one Contact with method=Email, then one with method=Phone
for contact in ContactFactory.coverage():
    ...
```

`coverage()` attempts to cover every supported form with the fewest instances. The field with the most variants determines the result count; variants from shorter fields are reused instead of producing a Cartesian product.

```python
import pytest


@pytest.mark.parametrize("contact", list(ContactFactory.coverage()))
def test_contact_dispatch(contact: Contact) -> None:
    ...
```

Optional fields contribute both the wrapped form and `None` to coverage. Collection coverage contains the available child variants, while `__min_collection_length__` and `__max_collection_length__` are ignored. Recursive-model coverage is unsupported. For exhaustive input-space exploration, use [Hypothesis](https://hypothesis.readthedocs.io/).

## Persistence protocols

Configure a handler class or instance that implements the corresponding protocol:

```python
from polyfactory import AsyncPersistenceProtocol


order_store: dict[int, Order] = {}


class OrderPersistence(AsyncPersistenceProtocol[Order]):
    async def save(self, data: Order) -> Order:
        order_store[data.id] = data
        return data

    async def save_many(self, data: list[Order]) -> list[Order]:
        order_store.update((order.id, order) for order in data)
        return data


class OrderFactory(DataclassFactory[Order]):
    __async_persistence__ = OrderPersistence


order = await OrderFactory.create_async()
orders = await OrderFactory.create_batch_async(3)
```

`create_sync()` / `create_batch_sync()` require `SyncPersistenceProtocol`; the async pair require `AsyncPersistenceProtocol`. The handler receives objects already produced by `build()` / `batch()`.

## SQLAlchemy 3.3 behavior

Polyfactory 3 defaults all four SQLAlchemy inclusion flags to `True`:

- `__set_primary_key__`
- `__set_foreign_keys__`
- `__set_relationships__`
- `__set_association_proxy__`

Set flags explicitly when tests need a smaller object graph or database-generated keys:

```python
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory


class OrderModelFactory(SQLAlchemyFactory[OrderModel]):
    __set_primary_key__ = False
    __set_relationships__ = False
    __set_association_proxy__ = False
```

For built-in persistence, set `__session__` or `__async_session__` to a session or zero-argument session provider. Then call `create_sync()` / `create_batch_sync()` or await `create_async()` / `create_batch_async()`.

The default `SQLAlchemyPersistenceMethod.COMMIT` commits each save. Polyfactory 3.3 adds `SQLAlchemyPersistenceMethod.FLUSH` for transaction-controlled tests:

```python
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyPersistenceMethod


class OrderModelFactory(SQLAlchemyFactory[OrderModel]):
    __async_session__ = async_session
    __persistence_method__ = SQLAlchemyPersistenceMethod.FLUSH


order = await OrderModelFactory.create_async()
await async_session.rollback()
```

Async persistence refreshes saved instances so server-generated defaults are available and leaves the supplied async session open. `create_sync()` and `create_async()` skip computed columns so the database can populate them.
