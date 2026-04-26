# Factories

Reference for picking and configuring factory bases. The factory base owns *how* a model is introspected — match it to the model's backend or generated data quietly drifts off-spec.

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

Wrong base = silent fallback to attribute-by-attribute introspection. The fallback often produces values that violate `msgspec.Meta(...)` ranges, Pydantic `Field(...)` constraints, or attrs validators — your model raises during construction or the test passes with off-spec data. Always pick the base that matches the backend.

## The basic pattern

```python
class WidgetFactory(<Base>[Widget]):
    __model__ = Widget
```

`__model__` must be set. The base reads it via `__init_subclass__` to introspect annotations; without it `.build()` raises `ConfigurationException` the first time it runs.

## Build helpers

| Method | Returns | Use case |
| --- | --- | --- |
| `Factory.build(**overrides)` | one `T` | most tests |
| `Factory.batch(n, **overrides)` | `list[T]` of length `n` | list-handler tests, repository smoke tests |
| `Factory.coverage(**overrides)` | iterator over `T` | one instance per Union / Optional branch — drives `pytest.mark.parametrize` over polymorphic shapes |
| `Factory.build_async(**overrides)` | coroutine returning one `T` | async ODMs (Beanie, Odmantic) where construction is async |

`build()` accepts keyword overrides (`OrderFactory.build(status="paid")`) — useful for one-off variations without subclassing.

## Field customization

### Literal pin

```python
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order

    status = "pending"  # every build produces status="pending"
```

A class attribute with a non-callable value pins the field to that literal across all builds.

### `Use(callable, *args, **kwargs)`

Re-evaluated on every `build()`:

```python
from polyfactory import Use


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order

    total_cents = Use(DataclassFactory.__random__.randint, 100, 10_000)
    customer_email = Use(lambda: f"user-{DataclassFactory.__random__.randint(1, 999)}@example.com")
```

`Use(fn, *args, **kwargs)` calls `fn(*args, **kwargs)` per build. Access the factory's seeded `Random` via `Factory.__random__` so values stay deterministic when `__random_seed__` is set.

### `PostGenerated(callable)`

Field generators that depend on values already produced for the same instance:

```python
from polyfactory import PostGenerated


def _slug_from_name(name: str, **_: object) -> str:
    return name.lower().replace(" ", "-")


class ArticleFactory(DataclassFactory[Article]):
    __model__ = Article

    slug = PostGenerated(_slug_from_name)
```

The callable receives all already-generated fields by name. Useful when one field is derived from another (slug from title, full_name from first/last, etc.).

## Default factory registration

Polyfactory looks up nested-field factories by type. Setting `__set_as_default_factory_for_type__ = True` makes a factory the default for its model whenever that model appears as a nested field on another model:

```python
class CustomerFactory(DataclassFactory[Customer]):
    __model__ = Customer
    __set_as_default_factory_for_type__ = True


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    # Order.customer: Customer is automatically populated via CustomerFactory.build()
```

Without the default flag, polyfactory introspects the nested type generically — fine for simple types, but loses any field overrides defined on `CustomerFactory`.

## Determinism

### Per-factory seed

```python
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    __random_seed__ = 42
```

Re-running the test with the same seed produces identical instances — set this when assertions check exact generated values.

### Per-factory Faker

```python
from faker import Faker


class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    __faker__ = Faker(locale="en_US")
    __faker__.seed_instance(42)
```

Use a custom `Faker` to control locale (regional names, addresses) or to share a single seeded Faker across multiple factories.

### `__allow_none_optionals__`

Probability that an `Optional[T]` field comes back as `None`. Default `1.0` (50/50). Set to `0.0` to never produce `None`, or `2.0` to always produce `None` — handy for testing the null-handling branch specifically.

```python
class OrderFactory(DataclassFactory[Order]):
    __model__ = Order
    __allow_none_optionals__ = 0.0  # always populate optionals
```

### `__check_model__`

When `True`, polyfactory validates each generated instance through the model's own validation step (Pydantic `model_validate`, msgspec `convert`, attrs validators). Default `False` — turn on while debugging factory drift.

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
    __model__ = Contact


# Yields one Contact with method=Email, then one with method=Phone
for contact in ContactFactory.coverage():
    ...
```

`coverage()` walks each Union/Optional branch and yields one instance per branch. Pair with `pytest.mark.parametrize` to fan out test cases over polymorphic shapes:

```python
import pytest


@pytest.mark.parametrize("contact", list(ContactFactory.coverage()))
def test_contact_dispatch(contact: Contact) -> None:
    ...
```

Note `coverage()` is best-effort — for deeply nested unions it produces a representative sample, not the Cartesian product. For exhaustive input-space exploration, reach for [Hypothesis](https://hypothesis.readthedocs.io/) instead; polyfactory's job is realistic single-instance generation.
