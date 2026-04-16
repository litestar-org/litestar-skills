# Repository Services (Advanced Alchemy)

`SQLAlchemyAsyncRepositoryService` is THE data-access pattern for Litestar consumer apps. Subclassing gets you a complete async CRUD surface, automatic DTO conversion, filtering, and pagination — without writing a single SELECT.

## Pattern

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

## Methods You Get for Free

| Method | Use case |
|---|---|
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

## `to_schema` Variants

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

## When to Drop to Hand-Written Queries

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

## Cross-references

- Custom exceptions raised by `get` / `get_one`: [exceptions.md](exceptions.md)
- Filter dependencies and pagination: [pagination.md](pagination.md)
- DTO conversion via `to_schema`: [dto.md](dto.md)
- Sibling skill for deeper Advanced Alchemy patterns (audit bases, Alembic): `../../advanced-alchemy/SKILL.md`
