# Repository Patterns

## Repository Types

Advanced Alchemy provides three async repository variants:

| Repository | Use Case |
| --- | --- |
| `SQLAlchemyAsyncRepository` | Standard async CRUD operations |
| `SQLAlchemyAsyncSlugRepository` | CRUD + automatic slug generation via `get_available_slug()` |
| `SQLAlchemyAsyncQueryRepository` | Complex read-only queries (no model_type required) |

```python
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
    SQLAlchemyAsyncSlugRepository,
    SQLAlchemyAsyncQueryRepository,
)
```

## Basic Repository

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from app.db import models as m


class UserRepository(SQLAlchemyAsyncRepository[m.User]):
    """User repository."""

    model_type = m.User
```

## Slug Repository

For models using `SlugKey` mixin:

```python
from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository
from app.db import models as m


class ArticleRepository(SQLAlchemyAsyncSlugRepository[m.Article]):
    """Article repository with slug support."""

    model_type = m.Article
```

This adds `get_available_slug()` which auto-generates unique slugs (e.g., `my-article`, `my-article-1`).

## Query Repository

For complex read-only queries that don't map to a single model:

```python
from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository


class ReportRepository(SQLAlchemyAsyncQueryRepository):
    """Read-only repository for complex reporting queries."""

    async def get_user_activity_summary(self, user_id):
        result = await self.session.execute(
            text("""
                SELECT u.email, COUNT(a.id) as activity_count
                FROM user_account u
                LEFT JOIN activity a ON a.user_id = u.id
                WHERE u.id = :user_id
                GROUP BY u.email
            """),
            {"user_id": user_id},
        )
        return result.mappings().first()
```

## In-Memory Test Repository

For unit-testing services without spinning up a real database, Advanced Alchemy ships mock repositories under `advanced_alchemy.repository.memory`. They share the production repository protocols (`SQLAlchemyAsyncRepositoryProtocol` / `SQLAlchemySyncRepositoryProtocol`), so any service that accepts a `repository_type` accepts the mock.

```python
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemyAsyncMockSlugRepository,
    SQLAlchemySyncMockRepository,
    SQLAlchemySyncMockSlugRepository,
)
```

Each class wraps a process-wide `SQLAlchemyMultiStore` keyed by model type, with `SQLAlchemyInMemoryStore` instances holding individual rows. Primary keys (including composite) are honored; foreign-key relationships are set via mapper introspection so that assigning a child populates `child.parent_id`.

### Substitution pattern

The idiomatic pattern is to subclass your service's inner `Repo` class, swap only the base, and set the same `model_type`:

```python
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository
from app.domain.orders.services import OrderService
from app.db import models as m


class OrderMockRepo(SQLAlchemyAsyncMockRepository[m.Order]):
    model_type = m.Order


class OrderServiceForTest(OrderService):
    repository_type = OrderMockRepo
```

The session is still required (an `AsyncSession` instance) but the mock ignores it — a `create_autospec`-based `Dialect` placeholder is used internally, so passing any `AsyncSession` fixture works.

### Supported filter subset

`SQLAlchemyAsyncMockRepository._apply_filters` handles `LimitOffset`, `BeforeAfter`, `OnBeforeAfter`, `CollectionFilter`, `NotInCollectionFilter`, `SearchFilter`, `NotInSearchFilter`, and `OrderBy`. A raw SQLAlchemy `ColumnElement` is silently accepted (not evaluated); any other filter type raises `RepositoryError` with `"Unexpected filter"`. `load` / `loader_options` / `execution_options` are accepted but ignored — eager loading is implicit because rows are Python objects.

### Fixture + test example

```python
import pytest
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository
from app.db import models as m


class TaskMockRepo(SQLAlchemyAsyncMockRepository[m.Task]):
    model_type = m.Task


@pytest.fixture(autouse=True)
def _clear_mock_store() -> None:
    SQLAlchemyAsyncMockRepository.__database_clear__()


async def test_task_archive(async_session) -> None:
    repo = TaskMockRepo(session=async_session)
    task = await repo.add(m.Task(title="draft spec"))
    task.is_archived = True
    await repo.update(task)
    assert (await repo.get(task.id)).is_archived is True
```

### When NOT to use

The mock bypasses SQLAlchemy compilation entirely — dialect-specific SQL, `MergeStatement`, `OnConflictUpsert` (see [`operations.md`](operations.md)), and any `text(...)` query repository go unverified. Use the mock for service-layer logic (lifecycle hooks, validation, branching); switch to `pytest-databases` container fixtures for integration tests that must exercise real SQL, triggers, or Alembic migrations.

## Configuration Options

### model_type

Required for `SQLAlchemyAsyncRepository` and `SQLAlchemyAsyncSlugRepository`:

```python
class UserRepository(SQLAlchemyAsyncRepository[m.User]):
    model_type = m.User
```

### uniquify for Many-to-Many

When dealing with many-to-many relationships, set `uniquify=True` to automatically deduplicate related objects:

```python
class UserRepository(SQLAlchemyAsyncRepository[m.User]):
    model_type = m.User
    uniquify = True  # Deduplicates related objects in many-to-many joins
```

## Nested Repository Pattern

The idiomatic pattern is to define the repository as an inner class of the service:

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from app.db import models as m


class UserService(SQLAlchemyAsyncRepositoryService[m.User]):
    """User service with nested repository."""

    class Repo(SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
```

This keeps the repository definition co-located with the service that uses it and avoids standalone repository files for simple cases.

## Direct Repository Usage

When you need to use a repository outside a service (e.g., in tests or scripts):

```python
from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_by_email(session: AsyncSession, email: str):
    repo = UserRepository(session=session)
    return await repo.get_one_or_none(email=email)
```

## Repository Methods Reference

Key methods available on all async repositories:

```python
# Add (create)
instance = await repo.add(model_instance)
instances = await repo.add_many([model1, model2])

# Get
instance = await repo.get(id)                          # Raises NotFoundError
instance = await repo.get_one_or_none(email="x@y.com") # Returns None

# List
results = await repo.list()
results, count = await repo.list_and_count(*filters)

# Update
instance = await repo.update(model_instance)
instances = await repo.update_many([model1, model2])

# Upsert
instance = await repo.upsert(model_instance, match_fields=["email"])

# Delete
instance = await repo.delete(id)

# Exists / Count
exists = await repo.exists(email="x@y.com")
count = await repo.count()
```
