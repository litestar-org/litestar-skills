# Declarative Base Classes Deep Dive

## Overview

Advanced Alchemy provides a hierarchy of declarative base classes in `advanced_alchemy.base` that add automatic primary keys, audit timestamps, and utility mixins on top of SQLAlchemy's declarative system.

```python
from advanced_alchemy.base import (
    BigIntAuditBase,
    BigIntBase,
    DefaultBase,
    IdentityAuditBase,
    IdentityBase,
    NanoIDAuditBase,
    NanoIDBase,
    UUIDAuditBase,
    UUIDBase,
    UUIDv6AuditBase,
    UUIDv6Base,
    UUIDv7AuditBase,
    UUIDv7Base,
    metadata_registry,
    orm_registry,
)
from advanced_alchemy.mixins import (
    AuditColumns,
    BigIntPrimaryKey,
    IdentityPrimaryKey,
    NanoIDPrimaryKey,
    SentinelMixin,
    SlugKey,
    UUIDPrimaryKey,
    UUIDv6PrimaryKey,
    UUIDv7PrimaryKey,
    UniqueMixin,
)
```

---

## Base Class Hierarchy

### DefaultBase

The plain base with no opinions — no automatic `id`, no timestamps. Use when you need full control over the schema.

```python
from advanced_alchemy.base import DefaultBase
from sqlalchemy.orm import Mapped, mapped_column


class CustomModel(DefaultBase):
    """Custom model with manually defined primary key."""

    __tablename__ = "custom_model"

    my_pk: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
```

- All other AA base classes inherit from this
- Registers the model with `orm_registry` automatically

---

## UUID Base Classes

### UUIDBase / UUIDAuditBase

Random UUID v4 primary key for general-purpose models.

```python
from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from sqlalchemy.orm import Mapped, mapped_column


class Tag(UUIDBase):
    """Lookup table model with UUID primary key and no audit timestamps."""

    __tablename__ = "tag"
    name: Mapped[str] = mapped_column(unique=True)


class User(UUIDAuditBase):
    """User account model with UUID primary key and audit timestamps."""

    __tablename__ = "user_account"
    email: Mapped[str] = mapped_column(unique=True)
```

| Column | Type | Behavior |
| --- | --- | --- |
| `id` | `UUID` (v4) | Auto-generated random UUID |
| `created_at` | `DateTimeUTC` | Set on insert (audit bases only) |
| `updated_at` | `DateTimeUTC` | Set on insert and update (audit bases only) |

### UUIDv6Base / UUIDv6AuditBase

UUID v6 primary key. With `uuid-utils` installed (or Python 3.14+), the
timestamp is encoded in the high bits, improving B-tree locality over random
UUID v4 values. Earlier Python versions without `uuid-utils` log a warning and
fall back to UUID v4 generation.

```python
from advanced_alchemy.base import UUIDv6AuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column


class AuditLog(UUIDv6AuditBase):
    """Audit log model with time-sortable UUID v6 primary key."""

    __tablename__ = "audit_log"
    action: Mapped[str] = mapped_column()
    details: Mapped[dict] = mapped_column(JsonB, default=dict)
```

- IDs sort chronologically by creation time when UUID v6 generation is available
- Good for append-heavy tables (logs, events)

### UUIDv7Base / UUIDv7AuditBase

UUID v7 primary key. With `uuid-utils` installed (or Python 3.14+), it encodes
a millisecond timestamp and random suffix. Earlier Python versions without
`uuid-utils` log a warning and fall back to UUID v4 generation.

```python
from advanced_alchemy.base import UUIDv7AuditBase
from sqlalchemy.orm import Mapped, mapped_column


class Order(UUIDv7AuditBase):
    """Order model with time-sortable UUID v7 primary key."""

    __tablename__ = "order"
    total: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(default="pending")
```

- Time-ordered by the UUIDv7 timestamp component when UUID v7 generation is available
- Compatible with PostgreSQL `UUID` type and all AA repository/service patterns

---

## BigInt Base Classes

### BigIntBase / BigIntAuditBase

Auto-incrementing `BigInteger` primary key. Use for high-volume tables where integer PKs are preferred, or when interfacing with legacy systems.

```python
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class PageView(BigIntAuditBase):
    """Page view model with BigInteger primary key."""

    __tablename__ = "page_view"
    url: Mapped[str] = mapped_column()
    user_agent: Mapped[str | None] = mapped_column(default=None)
```

| Column | Type | Behavior |
| --- | --- | --- |
| `id` | `BigInteger` | Auto-incrementing (`BIGSERIAL` on PostgreSQL) |
| `created_at` | `DateTimeUTC` | Set on insert (audit bases only) |
| `updated_at` | `DateTimeUTC` | Set on insert and update (audit bases only) |

---

## Identity Base Classes

### IdentityBase / IdentityAuditBase

Database native `IDENTITY` primary key (`BigIntIdentity`). Use when database-level identity generation is required.

```python
from advanced_alchemy.base import IdentityAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class Invoice(IdentityAuditBase):
    """Invoice model with native identity primary key."""

    __tablename__ = "invoice"
    invoice_number: Mapped[str] = mapped_column(unique=True)
    amount: Mapped[int] = mapped_column()
```

| Column | Type | Behavior |
| --- | --- | --- |
| `id` | `BigIntIdentity` | Database native `IDENTITY` generation via SQLAlchemy `Identity()` |
| `created_at` | `DateTimeUTC` | Set on insert (audit bases only) |
| `updated_at` | `DateTimeUTC` | Set on insert and update (audit bases only) |

---

## NanoID Base Classes

### NanoIDBase / NanoIDAuditBase

NanoID string primary key — a URL-friendly, unique string ID. Useful when you need short, human-readable identifiers.

```python
from advanced_alchemy.base import NanoIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class ShortLink(NanoIDAuditBase):
    """Short link model with NanoID string primary key."""

    __tablename__ = "short_link"
    target_url: Mapped[str] = mapped_column()
    clicks: Mapped[int] = mapped_column(default=0)
```

| Column | Type | Behavior |
| --- | --- | --- |
| `id` | `String` | Auto-generated NanoID (e.g., `V1StGXR8_Z5jdHi6B-myT`) |
| `created_at` | `DateTimeUTC` | Set on insert (audit bases only) |
| `updated_at` | `DateTimeUTC` | Set on insert and update (audit bases only) |

- Shorter and more URL-friendly than UUIDs
- Install `fastnanoid` for NanoID generation. Without it, 1.11 logs a warning and falls back to UUIDv4 generation.

---

## Mixins

### AuditColumns

Adds only `created_at` and `updated_at` without any primary key. Use when you need timestamps on a model that defines its own PK.

```python
from advanced_alchemy.base import DefaultBase
from advanced_alchemy.mixins import AuditColumns
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column


class ExternalRecord(DefaultBase, AuditColumns):
    """External record model with custom primary key and audit timestamps."""

    __tablename__ = "external_record"

    external_id: Mapped[str] = mapped_column(primary_key=True)
    data: Mapped[dict] = mapped_column(JsonB, default=dict)
```

- `created_at`: set automatically on insert
- `updated_at`: set automatically on insert and every update

### SlugKey

Adds a `slug: Mapped[str]` column (unique, indexed) for URL-friendly identifiers. Pair with `SQLAlchemyAsyncSlugRepository` for automatic slug generation.

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.mixins import SlugKey
from sqlalchemy.orm import Mapped, mapped_column


class Article(UUIDAuditBase, SlugKey):
    """Article model with slug column."""

    __tablename__ = "article"
    title: Mapped[str] = mapped_column()
    body: Mapped[str] = mapped_column()
```

- The slug column is automatically unique and indexed
- `SQLAlchemyAsyncSlugRepository.get_available_slug()` generates unique slugs (e.g., `my-title`, `my-title-1`)
- Slugs are not auto-generated from a field — you provide the source value to the slug repository

### UniqueMixin

Select-or-create pattern for deduplication. Ensures only one row exists for a given set of unique criteria.

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.mixins import UniqueMixin
from sqlalchemy.orm import Mapped, mapped_column


class Tag(UUIDAuditBase, UniqueMixin):
    """Deduplicated tag model."""

    __tablename__ = "tag"
    name: Mapped[str] = mapped_column(unique=True)

    @classmethod
    def unique_hash(cls, name: str) -> str:
        """Return a hashable key for the in-memory cache."""
        return name

    @classmethod
    def unique_filter(cls, name: str):
        """Return the uniqueness predicate."""
        return cls.name == name
```

- `unique_hash()`: returns a hashable key for in-memory dedup within a session
- `unique_filter()`: returns a SQLAlchemy boolean expression
- Call `await Tag.as_unique_async(session, name)` or `Tag.as_unique_sync(session, name)`; this API is independent of repository `get_or_upsert()`

---

## Table Naming Conventions

### Automatic `__tablename__` Generation

If you omit `__tablename__`, Advanced Alchemy auto-generates it by converting the class name from CamelCase to snake_case (`user_account` for `UserAccount`, `http_request` for `HTTPRequest`).

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class UserAccount(UUIDAuditBase):
    """Table name is auto-generated as 'user_account'."""

    email: Mapped[str] = mapped_column(unique=True)


class HTTPRequest(UUIDAuditBase):
    """Table name is auto-generated as 'http_request'."""

    url: Mapped[str] = mapped_column()
```

### Explicit Table Names

Best practice is to always set `__tablename__` explicitly:

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class User(UUIDAuditBase):
    """User model with explicit table name."""

    __tablename__ = "user_account"
    email: Mapped[str] = mapped_column(unique=True)
```

### Table Arguments

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class User(UUIDAuditBase):
    """User model with table constraints and comments."""

    __tablename__ = "user_account"
    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_user_email_tenant"),
        {"comment": "User accounts with multi-tenant uniqueness"},
    )

    email: Mapped[str] = mapped_column()
    tenant_id: Mapped[str] = mapped_column()
```

---

## Metadata Registry and Multi-Database

### orm_registry

All AA base classes register their models in a shared `orm_registry`. This registry holds the SQLAlchemy `MetaData` used by Alembic for migration auto-generation.

```python
from advanced_alchemy.base import orm_registry

target_metadata = orm_registry.metadata
```

### metadata_registry and Bind Keys

For multi-database setups, use `__bind_key__` on your model to route it to a specific database. The `metadata_registry` maps bind keys to separate `MetaData` instances.

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column


class AnalyticsEvent(UUIDAuditBase):
    """Analytics model routed to the analytics database bind."""

    __tablename__ = "analytics_event"
    __bind_key__ = "analytics"

    event_type: Mapped[str] = mapped_column()
    payload: Mapped[dict] = mapped_column(JsonB, default=dict)
```

- Models without `__bind_key__` use the default (primary) database
- Each bind key gets its own metadata and config-owned engine
- Configure the corresponding `SQLAlchemyAsyncConfig` with matching `bind_key`
- Configure a distinct Alembic `script_location` when binds require separate migration histories

---

## Creating Custom Base Classes

Combine mixins to create project-specific bases:

```python
from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.mixins import AuditColumns, SlugKey
from sqlalchemy.orm import Mapped, mapped_column


class ProjectBase(UUIDv7Base, AuditColumns):
    """Custom base with UUIDv7 PK and audit timestamps."""

    __abstract__ = True


class ContentBase(UUIDv7Base, AuditColumns, SlugKey):
    """Custom base for content models with slugs."""

    __abstract__ = True


class BlogPost(ContentBase):
    """Blog post model using ContentBase."""

    __tablename__ = "blog_post"
    title: Mapped[str] = mapped_column()
    body: Mapped[str] = mapped_column()


class Setting(ProjectBase):
    """Setting model using ProjectBase."""

    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(unique=True)
    value: Mapped[str] = mapped_column()
```

- Always set `__abstract__ = True` on custom bases to prevent SQLAlchemy from creating a table for them
- Mixins are applied left-to-right; place the PK base first

---

## Quick Reference Table

| Base Class | PK Type | Audit Fields | Best For |
| --- | --- | --- | --- |
| `DefaultBase` | None (define your own) | None | Custom primary keys with AA table naming |
| `UUIDBase` | UUID v4 | None | Simple lookup tables |
| `UUIDAuditBase` | UUID v4 | `created_at`, `updated_at` | General-purpose models |
| `UUIDv6Base` | UUID v6 | None | Time-sortable without audit |
| `UUIDv6AuditBase` | UUID v6 | `created_at`, `updated_at` | Time-sortable append tables |
| `UUIDv7Base` | UUID v7 | None | New projects (preferred) |
| `UUIDv7AuditBase` | UUID v7 | `created_at`, `updated_at` | Time-ordered IDs when UUIDv7 generation is available |
| `BigIntBase` | BigInteger | None | High-volume, legacy systems |
| `BigIntAuditBase` | BigInteger | `created_at`, `updated_at` | High-volume with audit |
| `IdentityBase` | BigIntIdentity | None | Native identity columns |
| `IdentityAuditBase` | BigIntIdentity | `created_at`, `updated_at` | Native identity with audit |
| `NanoIDBase` | NanoID string | None | Short URLs, human-readable IDs |
| `NanoIDAuditBase` | NanoID string | `created_at`, `updated_at` | Short URLs with audit |
