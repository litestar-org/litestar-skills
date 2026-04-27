# Litestar patterns

How polyfactory fits into a Litestar test suite. The companion skill `litestar:litestar-testing` covers TestClient/AsyncTestClient setup; this page covers what to feed them.

## The default pairing

```python
# tests/factories.py
from polyfactory.factories.msgspec_factory import MsgspecFactory
from polyfactory.pytest_plugin import register_fixture

from myapp.dtos import CreateOrderDTO


@register_fixture
class CreateOrderDTOFactory(MsgspecFactory[CreateOrderDTO]):
    __model__ = CreateOrderDTO
```

```python
# tests/test_orders.py
from __future__ import annotations

import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.anyio
async def test_create_order(
    client: AsyncTestClient,
    create_order_dto_factory: CreateOrderDTOFactory,
) -> None:
    payload = create_order_dto_factory.build()
    response = await client.post("/orders", json=payload)

    assert response.status_code == 201
```

The factory provides validation-passing data; the test focuses on the request/response contract. `client` comes from your `litestar-testing` fixtures — see that skill for `AsyncTestClient` lifespan + DI override patterns.

## Backend → factory base, in Litestar projects

| Litestar use site | Model backend | Factory base |
| --- | --- | --- |
| Handler input DTO via `data: MyDTO` | usually `msgspec.Struct` (fastest path) | `MsgspecFactory` |
| Pydantic input DTO | `pydantic.BaseModel` | `ModelFactory` |
| Response model with attrs (legacy) | `@attrs.define` | `AttrsFactory` |
| Domain model → SQLAlchemy via `advanced-alchemy` | declarative `Base` | `SQLAlchemyFactory` |
| msgspec event payload (Channels, SAQ, etc.) | `msgspec.Struct` | `MsgspecFactory` |

If you mix backends (Pydantic for HTTP boundaries, msgspec for internal events), keep one factory per model and don't try to share base classes — the introspection rules differ.

## Parametrizing handler tests via `coverage()`

For handlers that accept tagged unions or polymorphic DTOs, `coverage()` produces one instance per branch — drive `parametrize` with it to exercise every dispatch path:

```python
import pytest

# myapp/dtos.py exports CreateOrderDTO = CreateRetailOrder | CreateWholesaleOrder


class CreateOrderDTOFactory(MsgspecFactory[CreateOrderDTO]):
    __model__ = CreateOrderDTO


@pytest.mark.anyio
@pytest.mark.parametrize("payload", list(CreateOrderDTOFactory.coverage()))
async def test_create_order_all_variants(client: AsyncTestClient, payload) -> None:
    response = await client.post("/orders", json=payload)
    assert response.status_code in (201, 202)
```

One test function, one parametrize, every dispatch branch covered. Beats hand-rolling discriminator-aware fixtures.

## Generating advanced-alchemy model data

```python
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from polyfactory.pytest_plugin import register_fixture

from myapp.db.models import Order  # advanced_alchemy.base.UUIDBase or similar


@register_fixture
class OrderModelFactory(SQLAlchemyFactory[Order]):
    __model__ = Order
    __set_as_default_factory_for_type__ = True
    __set_relationships__ = True  # populate FK fields with nested factories
```

Two flags worth knowing for ORM use:

- `__set_relationships__ = True` — populate relationship fields (one-to-many, many-to-one) using their default factories. Off by default because it can blow out object graphs.
- `__set_primary_key__ = True` — set primary key fields explicitly. Off by default; usually you want the database to assign primary keys, so leave it off and let the session populate them on flush.

Bias toward calling `.build()` at the boundary and letting the session/repository persist:

```python
@pytest.mark.anyio
async def test_order_repo(order_repository, order_model_factory) -> None:
    order = order_model_factory.build()
    persisted = await order_repository.add(order)
    assert persisted.id is not None
```

Don't try to wire factories into `add_all` directly — the session lifecycle gets confusing. Build, then hand to the repository.

## SAQ task payload generation

```python
from polyfactory.factories.msgspec_factory import MsgspecFactory
from polyfactory.pytest_plugin import register_fixture

from myapp.tasks import EmailJobPayload


@register_fixture
class EmailJobPayloadFactory(MsgspecFactory[EmailJobPayload]):
    __model__ = EmailJobPayload


@pytest.mark.anyio
async def test_email_task(email_job_payload_factory, queue) -> None:
    payload = email_job_payload_factory.build()
    job = await queue.enqueue("send_email", **payload.__dict__)
    assert job.status == "queued"
```

For SAQ task tests, factories provide the task payload; the queue fixture (function- or session-scoped, depending on isolation needs) dispatches.

## Channels event-system tests

When testing realtime event publishing, factories drop straight into `RealtimePublisher` calls:

```python
@pytest.mark.anyio
async def test_order_event_publishes(realtime_publisher, order_created_event_factory) -> None:
    event = order_created_event_factory.build()
    await realtime_publisher.publish_workspace_event(event)
    # assert subscriber observed event
```

This pairs with the `litestar-testing` skill's WebSocket / Channels fixtures.

## When NOT to use polyfactory in Litestar tests

- **End-to-end smoke tests with hand-curated data.** When the test exists to demonstrate "this exact realistic payload works", inline the JSON. Factories add indirection that hides intent.
- **Property-based testing.** Polyfactory generates one realistic value per call. For exploring an input space (finding edge-case bugs), use [Hypothesis](https://hypothesis.readthedocs.io/) — it's a different tool for a different job.
- **Production seeding.** Don't reuse factories for `manage.py seed-demo-data`; they're test-only and will rot if used outside that context. Write a deterministic seeder script instead.

## Cross-skill links

- Request side: [`litestar:litestar-testing`](../../litestar-testing/SKILL.md) — TestClient/AsyncTestClient, lifespan, Guard mocks, DI overrides.
- Database fixtures: [`litestar:pytest-databases`](../../pytest-databases/SKILL.md) — container-based DB fixtures that pair with SQLAlchemy factories.
- Data shapes: [`litestar:msgspec`](../../msgspec/SKILL.md), [`litestar:advanced-alchemy`](../../advanced-alchemy/SKILL.md) for the model side; polyfactory inspects whatever those skills produce.
