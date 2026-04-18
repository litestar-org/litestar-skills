# Service Layer — Per-Stack Patterns

The service layer pattern in a Litestar app depends on your data-access stack. Pick the branch that matches your project and stay consistent — do not mix an `advanced-alchemy` repository service with a `sqlspec` driver call in the same Controller.

## Pick the branch for your stack

- **`advanced-alchemy`** → `SQLAlchemyAsyncRepositoryService` — opinionated ORM service with audit fields, filters, and pagination built in. Start here when you want a complete CRUD surface without writing SELECTs.
- **`sqlspec`** → `SQLSpecAsyncService` + driver methods — thin async service over explicit SQL. Start here for direct SQL control, 15+ adapter support, or Arrow / analytics integration. See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md).
- **raw SQLAlchemy** → `async_sessionmaker` + hand-rolled statements — start here only when you have an existing SA Core / ORM investment and explicitly do not want the repository abstraction.

## Branch A — `advanced-alchemy` repository service

`SQLAlchemyAsyncRepositoryService` is the opinionated default when `advanced-alchemy` is in the project. Subclassing gets you a complete async CRUD surface, automatic DTO conversion, filtering, and pagination — without writing a single SELECT.

```python
from __future__ import annotations

from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

from app.db.models import User


class UserRepository(SQLAlchemyAsyncRepository[User]):
    model_type = User


class UserService(SQLAlchemyAsyncRepositoryService[User]):
    """Handles database operations for users."""

    repository_type = UserRepository

    async def authenticate(self, email: str, password: str) -> User | None:
        db_user = await self.get_one_or_none(email=email)
        if db_user is None or not db_user.verify_password(password):
            return None
        return db_user
```

### Methods you get for free

| Method | Use case |
| --- | --- |
| `get(id)` | Fetch by primary key; raises `NotFoundError` if missing |
| `get_one(**kwargs)` | Fetch one by field filters; raises if missing |
| `get_one_or_none(**kwargs)` | Fetch one or `None` |
| `list(*filters, **kwargs)` | Plain list, no pagination metadata |
| `list_and_count(*filters, **kwargs)` | Returns `(rows, total)` — pair with `to_schema` for `OffsetPagination[T]` |
| `create(data)` | Insert; `data` may be dict / dataclass / Struct |
| `update(data, **kwargs)` | Update by id (in `data`) or by `**kwargs` filters |
| `upsert(data, match_fields=[...])` | Insert-or-update on natural keys |
| `delete(id, **kwargs)` | Delete by id or filter |
| `exists(**kwargs)` | Boolean existence check (cheap) |
| `count(*filters, **kwargs)` | Row count with filters applied |
| `to_schema(rows, total=None, filters=None, schema_type=...)` | Convert ORM rows → msgspec DTO; auto-paginates when `total` provided |

### `to_schema` variants

```python
# Single object
return service.to_schema(db_user, schema_type=User)

# List with pagination metadata (returns OffsetPagination[T])
results, total = await service.list_and_count(*filters)
return service.to_schema(results, total, filters=filters, schema_type=User)

# List without pagination
return service.to_schema(results, schema_type=User)
```

`to_schema` reads filter context (limit/offset, total) and synthesizes the right envelope. Never hand-roll pagination shapes.

### When to drop to hand-written queries inside an advanced-alchemy service

Repository services cover ~90% of the data-access surface. Drop to hand-written SQLAlchemy when:

- You need a multi-table aggregate join that's expensive to express via filters
- You're computing window functions, recursive CTEs, or `LATERAL` joins
- You need raw SQL for a vendor-specific feature (Postgres `JSONB` ops, Oracle hierarchical queries)
- A read path is so hot that you've measured a win from a hand-tuned query

In all cases, keep the hand-written query inside the service class — never push raw SQL into Controllers.

```python
class UserService(SQLAlchemyAsyncRepositoryService[User]):
    repository_type = UserRepository

    async def active_user_emails_by_org(self, org_id: UUID) -> list[str]:
        stmt = select(User.email).join(OrgMember).where(
            OrgMember.org_id == org_id, User.is_active.is_(True),
        )
        result = await self.repository.session.execute(stmt)
        return list(result.scalars())
```

## Branch B — `sqlspec` async service

`SQLSpecAsyncService` wraps a `sqlspec` driver and gives you the same Controller-facing shape (`list_and_count`, `get_one_or_none`, etc.) while keeping SQL explicit and driver-adapter agnostic. The base class itself is a **project-defined** pattern adapted from [`litestar-sqlstack`](https://github.com/cofin/litestar-sqlstack) — copy it into your project's `app/lib/service.py` (it's ~40 lines). See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) for the reference implementation.

```python  # pragma: legacy-example
from __future__ import annotations

from sqlspec.service import SQLSpecAsyncService  # project-defined — see callout above

from app.schemas import Post


class PostService(SQLSpecAsyncService):
    async def list_and_count(self, *filters) -> tuple[list[Post], int]:
        return await self.driver.select_with_total(
            "SELECT * FROM posts WHERE tenant_id = :tid",
            filters=filters,
            schema_type=Post,
        )

    async def get_one_or_none(self, post_id: UUID) -> Post | None:
        return await self.driver.select_one_or_none(
            "SELECT * FROM posts WHERE id = :id",
            parameters={"id": post_id},
            schema_type=Post,
        )
```

Pick `sqlspec` when: you want direct SQL, you're targeting multiple database backends (15+ adapters including DuckDB and BigQuery), or you need Arrow-native result streams for analytics. See [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) for the full pattern including filters, pagination, and transaction boundaries.

## Branch C — raw SQLAlchemy with manual sessions

If the project predates `advanced-alchemy` (or intentionally avoids it), the canonical pattern is a thin service class over `async_sessionmaker`. Sessions are resolved via `Provide()` or Dishka — never instantiated inside a handler.

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post


class PostService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_and_count(self, limit: int, offset: int) -> tuple[list[Post], int]:
        stmt = select(Post).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())
        total = await self._session.scalar(select(func.count()).select_from(Post))
        return rows, total or 0

    async def get_one_or_none(self, post_id: UUID) -> Post | None:
        return await self._session.scalar(select(Post).where(Post.id == post_id))
```

No automatic `to_schema` — convert to DTOs explicitly at the handler boundary, or via a msgspec `convert()` helper.

## When to pick which

| Stack choice | Pick this when | Avoid this when |
| --- | --- | --- |
| `advanced-alchemy` service | You want an opinionated ORM service with audit fields, soft-delete, filters, and pagination built in | The project is explicitly raw-SA or sqlspec-only; you need multi-adapter support beyond what SQLAlchemy covers |
| `sqlspec` service | You want direct SQL, 15+ driver adapters, Arrow streams for analytics, or you're operating across heterogeneous databases | You want ORM-style attribute access on rows; you want automatic schema migrations driven by model classes |
| raw SQLAlchemy with `async_sessionmaker` | You have an existing SA Core / ORM codebase and explicitly do not want the `advanced-alchemy` repository abstraction | You're starting a new Litestar project — the other two give you more for free |

## Cross-references

- Custom exceptions raised by `get` / `get_one`: [exceptions.md](exceptions.md)
- Filter dependencies and pagination (per-stack): [pagination.md](pagination.md)
- DTO conversion via `to_schema`: [dto.md](dto.md)
- Sibling skill for deeper advanced-alchemy patterns (audit bases, Alembic): [`../../advanced-alchemy/SKILL.md`](../../advanced-alchemy/SKILL.md)
- Sibling skill for deeper sqlspec patterns (driver adapters, Arrow, query builder): [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md)
