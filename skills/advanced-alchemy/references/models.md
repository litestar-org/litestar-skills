# Model Definition Patterns

## Base Classes

For Advanced Alchemy declarative models, select a base matching the required
primary-key and audit-column behavior. SQLModel `table=True` models are also
supported; see [SQLModel Compatibility](#sqlmodel-compatibility).

```python
from advanced_alchemy.base import UUIDAuditBase, UUIDv7AuditBase, BigIntAuditBase
```

| Base Class | PK Type | Notes |
| --- | --- | --- |
| `UUIDAuditBase` | UUID v4 | Most common — random UUID primary key |
| `UUIDv7AuditBase` | UUID v7 | Time-sortable UUID (better index locality) |
| `BigIntAuditBase` | BigInt | Auto-incrementing integer PK |

All audit bases include: `id`, `created_at` (auto-set), `updated_at` (auto-set on change).

## Basic Model

```python
from __future__ import annotations

from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(UUIDAuditBase):
    """User account model."""

    __tablename__ = "user_account"
    __table_args__ = {"comment": "User accounts"}

    email: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str | None] = mapped_column(default=None)
    username: Mapped[str | None] = mapped_column(
        String(length=30),
        unique=True,
        index=True,
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    login_count: Mapped[int] = mapped_column(default=0)
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"),
        default=None,
    )

    team: Mapped[Team | None] = relationship(back_populates="members", lazy="selectin")
    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete",
    )
```

## Mixins

### SlugKey — URL-friendly Identifiers

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.mixins import SlugKey
from sqlalchemy.orm import Mapped, mapped_column


class Article(UUIDAuditBase, SlugKey):
    """Article with a unique slug column."""

    __tablename__ = "article"

    title: Mapped[str] = mapped_column()
    body: Mapped[str] = mapped_column()
```

`SlugKey` adds a unique `slug: Mapped[str]` column. Use
`SQLAlchemyAsyncSlugRepository` to derive and deduplicate slug values; the
mixin itself does not populate the column.

### UniqueMixin — Select-or-Create

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.mixins import UniqueMixin
from sqlalchemy.orm import Mapped, mapped_column


class Tag(UUIDAuditBase, UniqueMixin):
    """Tag that is created once and reused."""

    __tablename__ = "tag"

    name: Mapped[str] = mapped_column(unique=True)

    @classmethod
    def unique_hash(cls, name: str) -> str:
        return name

    @classmethod
    def unique_filter(cls, name: str):
        return cls.name == name
```

Call `await Tag.as_unique_async(session, name)` for an async session or
`Tag.as_unique_sync(session, name)` for a sync session. The mixin caches the
result on that session.

## Special Types

Advanced Alchemy provides custom types for timezone-aware datetimes (`DateTimeUTC`), cross-dialect UUIDs (`GUID`), JSON storage (`JsonB`), encryption (`EncryptedString`, `EncryptedText`), and file storage (`FileObject`, `StoredObject`).

```python
from advanced_alchemy.types import (
    DateTimeUTC,
    EncryptedString,
    EncryptedText,
    GUID,
    JsonB,
)
from advanced_alchemy.types.file_object import FileObject, StoredObject
```

### EncryptedString

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import EncryptedString, EncryptedText
from advanced_alchemy.types.encrypted_string import FernetBackend
from sqlalchemy.orm import Mapped, mapped_column


class UserSecret(UUIDAuditBase):
    """User secret model storing encrypted API keys and private notes."""

    __tablename__ = "user_secret"

    api_key: Mapped[str] = mapped_column(
        EncryptedString(key="your-fernet-key", backend=FernetBackend),
    )
    notes: Mapped[str | None] = mapped_column(
        EncryptedText(key="your-fernet-key", backend=FernetBackend),
        default=None,
    )
```

Always pass `key=` explicitly. In 1.11, omitting it emits a deprecation
warning and uses a process-random key; data written with that default cannot be
decrypted after restart. Load the stable passphrase from application settings
or a secrets manager.

### FileObject / StoredObject

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import FileObject, StoredObject
from advanced_alchemy.utils.sync_tools import await_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column


class ProjectAttachment(UUIDAuditBase):
    """Project attachment model with stored file and signed URL property."""

    __tablename__ = "project_attachment"

    name: Mapped[str] = mapped_column(nullable=False)
    file: Mapped[FileObject] = mapped_column(StoredObject(backend="private"))

    @hybrid_property
    def url(self) -> str:
        """Generate a signed URL synchronously from an async storage backend."""
        return await_(self.file.sign_async)()
```

Register storage backends during app boot. Supports `FSSpecBackend` (local, S3, GCS) and `ObstoreBackend`.

## Deferred Loading Groups

For security-sensitive or large fields, use deferred loading so they are only fetched when explicitly requested:

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class User(UUIDAuditBase):
    """User model with deferred security credentials."""

    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(
        deferred_group="security_sensitive",
    )
    totp_secret: Mapped[str | None] = mapped_column(
        deferred_group="security_sensitive",
        default=None,
    )
```

To load deferred columns:

```python
from sqlalchemy.orm import undefer_group

user = await service.get(
    user_id,
    load=[undefer_group("security_sensitive")],
)
```

## Relationship Patterns

### One-to-Many with Cascade

```python
class Team(UUIDAuditBase):
    __tablename__ = "team"

    name: Mapped[str] = mapped_column()
    members: Mapped[list[User]] = relationship(
        back_populates="team",
        lazy="selectin",
        cascade="all, delete",
    )


class User(UUIDAuditBase):
    __tablename__ = "user_account"

    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"),
        default=None,
    )
    team: Mapped[Team | None] = relationship(back_populates="members", lazy="selectin")
```

### Many-to-Many with Association Table

```python
from sqlalchemy import Column, ForeignKey, Table

from advanced_alchemy.base import orm_registry

user_role_table = Table(
    "user_role",
    orm_registry.metadata,
    Column("user_id", ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)


class User(UUIDAuditBase):
    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(unique=True)
    roles: Mapped[list[Role]] = relationship(
        secondary=user_role_table,
        back_populates="users",
        lazy="selectin",
    )


class Role(UUIDAuditBase):
    __tablename__ = "role"

    name: Mapped[str] = mapped_column(unique=True)
    users: Mapped[list[User]] = relationship(
        secondary=user_role_table,
        back_populates="roles",
        lazy="selectin",
    )
```

### Read-Only Subquery Projections (`SQLQuery`) & `AssociationProxy`

Use `SQLQuery` to map read-only aggregate or window-function subqueries as `viewonly=True` ORM relationships, and flatten scalar fields with `AssociationProxy`:

```python
from uuid import UUID

from advanced_alchemy.base import SQLQuery, UUIDAuditBase
from sqlalchemy import ForeignKey, and_, func, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Project(UUIDAuditBase):
    """Project model with read-only aggregate and window relationships."""

    __tablename__ = "project"

    name: Mapped[str] = mapped_column(index=True)
    active_member_count: AssociationProxy[int] = association_proxy(
        "member_stats",
        "active_members",
    )


class ProjectMember(UUIDAuditBase):
    """Project membership link."""

    __tablename__ = "project_member"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("project.id", ondelete="cascade"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user_account.id", ondelete="cascade"))


class ProjectReport(UUIDAuditBase):
    """Periodic report generated for a project."""

    __tablename__ = "project_report"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("project.id", ondelete="cascade"))
    status: Mapped[str] = mapped_column()


class LatestProjectReport(SQLQuery):
    """Window-function subquery selecting the most recent report per project."""

    __table__ = select(
        ProjectReport,
        func.row_number()
        .over(order_by=ProjectReport.created_at.desc(), partition_by=ProjectReport.project_id)
        .label("report_index"),
    ).alias("latest_project_reports")


Project.latest_report = relationship(
    LatestProjectReport,
    primaryjoin=and_(
        LatestProjectReport.project_id == Project.id,
        LatestProjectReport.report_index == 1,
    ),
    viewonly=True,
    lazy="joined",
    uselist=False,
)


class ProjectMemberCount(SQLQuery):
    """Aggregate subquery counting members per project."""

    __table__ = (
        select(
            Project.id.label("project_id"),
            func.count(ProjectMember.id).label("active_members"),
        )
        .join_from(Project, ProjectMember, onclause=Project.id == ProjectMember.project_id, isouter=True)
        .group_by(Project.id)
    ).alias("project_member_count")
    project_id: UUID
    active_members: int


Project.member_stats = relationship(
    ProjectMemberCount,
    primaryjoin=ProjectMemberCount.project_id == Project.id,
    foreign_keys=ProjectMemberCount.project_id,
    viewonly=True,
    lazy="joined",
    innerjoin=True,
    uselist=False,
)
```

For multi-column grouping queries on `SQLQuery`, declare composite primary keys via `__mapper_args__ = {"primary_key": [__table__.c.project_id, __table__.c.category]}`.

### Joined-Table Polymorphic Inheritance & `AssociationProxy` Flattening

Combine SQLAlchemy joined-table polymorphism (`polymorphic_on` / `polymorphic_identity`) with `AssociationProxy` to expose parent relationship attributes directly on child models for `service.to_schema()` serialization:

```python
from uuid import UUID

from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship


class EvaluationRule(UUIDAuditBase):
    """Base polymorphic rule model."""

    __tablename__ = "evaluation_rule"
    __mapper_args__ = {
        "polymorphic_identity": "evaluation_rule",
        "polymorphic_on": "rule_type",
    }

    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategy.id", ondelete="cascade"))
    strategy_name: AssociationProxy[str] = association_proxy("strategy", "name")
    rule_type: Mapped[str]
    name: Mapped[str]

    strategy: Mapped[Strategy] = relationship(
        lazy="joined",
        innerjoin=True,
        viewonly=True,
        uselist=False,
    )


class EffortRule(EvaluationRule):
    """Joined-table polymorphic child model for effort scoring."""

    __tablename__ = "effort_rule"
    __mapper_args__ = {"polymorphic_identity": "effort_rule"}

    id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_rule.id"), primary_key=True)
    hours_per_unit: Mapped[float] = mapped_column(default=1.0)
```

## Password Hashing Types

```python
from advanced_alchemy.types import PasswordHash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher


class Account(UUIDAuditBase):
    __tablename__ = "account"

    email: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str] = mapped_column(
        PasswordHash(backend=Argon2Hasher()),
    )
```

Available hashers (each in its own submodule under `advanced_alchemy.types.password_hash`):

- `argon2.Argon2Hasher` — requires the `argon2-cffi` extra.
- `pwdlib.PwdlibHasher` — requires the `pwdlib` extra.
- `passlib.PasslibHasher` — requires the `passlib` extra.

## SQLModel Compatibility

Advanced Alchemy 1.11 accepts SQLModel table models directly. Use
`table=True`; a schema-only SQLModel has no SQLAlchemy mapper and is treated as
an input schema instead.

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from sqlmodel import Field, SQLModel


class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str


class HeroRepository(SQLAlchemyAsyncRepository[Hero]):
    model_type = Hero
```

Repositories and services use `model_to_dict()` for mapped SQLModel objects.
Create SQLModel tables from `SQLModel.metadata`; Advanced Alchemy base-class
mixins and automatic table metadata do not apply to an unrelated SQLModel
base.
