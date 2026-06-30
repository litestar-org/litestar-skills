# Complete Types Catalog

## Overview

Advanced Alchemy provides custom SQLAlchemy column types that handle cross-database compatibility, encryption, file storage, and specialized data formats. All types are importable from `advanced_alchemy.types` unless noted otherwise.

```python
from advanced_alchemy.types import (
    DateTimeUTC,
    EncryptedString,
    EncryptedText,
    GUID,
    JsonB,
    BigIntIdentity,
    ORA_JSONB,
    PasswordHash,
    Bool,
    Vector,
    TOTPSecret,
    OneTimeCode,
)
from advanced_alchemy.types.file_object import FileObject, StoredObject
```

---

## DateTimeUTC

Timezone-aware datetime that always stores and returns UTC. On databases that support timezone-aware timestamps (PostgreSQL `TIMESTAMP WITH TIME ZONE`), it uses the native type. On others, it stores as naive UTC and re-attaches `timezone.utc` on load.

```python
from advanced_alchemy.types import DateTimeUTC

class Event(UUIDAuditBase):
    __tablename__ = "event"

    name: Mapped[str] = mapped_column()
    scheduled_at: Mapped[datetime] = mapped_column(DateTimeUTC)
```

- Always pass timezone-aware datetimes when writing; naive datetimes raise `TypeError`
- Reads always return `datetime` with `tzinfo=timezone.utc`, including backends that store naive UTC internally

---

## GUID

Cross-database UUID type. Uses native UUID columns where the dialect supports them, Oracle `RAW(16)`, and binary or hex storage on backends without native UUID support.

```python
from advanced_alchemy.types import GUID

class Token(UUIDAuditBase):
    __tablename__ = "token"

    external_id: Mapped[UUID] = mapped_column(GUID)
```

- Transparent round-trip: you always work with Python `uuid.UUID` objects
- Oracle stores UUIDs as `RAW(16)`; do not document or migrate new Oracle schemas as `CHAR(32)`
- The AA base classes (`UUIDBase`, `UUIDAuditBase`, etc.) already use `GUID` for their `id` column

---

## JsonB

Cross-database JSONB type. Uses native `JSONB` on PostgreSQL/CockroachDB (with indexing support). On Oracle, it routes through `ORA_JSONB`; other databases use standard `JSON`.

```python
from advanced_alchemy.types import JsonB

class Config(UUIDAuditBase):
    __tablename__ = "config"

    settings: Mapped[dict] = mapped_column(JsonB, default=dict)
    tags: Mapped[list] = mapped_column(JsonB, default=list)
```

- On PostgreSQL/CockroachDB, supports native JSONB indexing for fast key/value lookups.
- On Oracle with SQLAlchemy 2.1+ and Oracle 21c+, stores as native `oracle.JSON`; otherwise uses BLOB binary JSON with an `IS JSON` check constraint.
- On SQLite/MySQL, stores as standard `JSON`.

---

## ORA_JSONB

Oracle-compatible JSONB type. Uses native `sqlalchemy.dialects.oracle.JSON` on SQLAlchemy 2.1+ when the Oracle server is 21c or newer. Falls back to BLOB binary JSON with an `IS JSON` check constraint when native Oracle JSON is unavailable.

```python
from advanced_alchemy.types import ORA_JSONB

class OracleModel(UUIDAuditBase):
    __tablename__ = "oracle_model"

    metadata_: Mapped[dict] = mapped_column(ORA_JSONB, default=dict)
```

- Use when targeting Oracle as a primary or secondary database.
- Keep the fallback path in mind for SQLAlchemy 2.0.x, Oracle 19c, offline DDL, or first-connect flows without server version information.

---

## BigIntIdentity

Auto-incrementing `BigInteger` primary key type. Used internally by `BigIntBase` and `BigIntAuditBase` for their `id` columns.

```python
from advanced_alchemy.types import BigIntIdentity

class LegacyRecord(UUIDAuditBase):
    __tablename__ = "legacy_record"

    legacy_id: Mapped[int] = mapped_column(BigIntIdentity, unique=True)
```

- Produces `BIGSERIAL` on PostgreSQL, `BIGINT AUTO_INCREMENT` on MySQL, `INTEGER` on SQLite
- Typically not used directly — prefer `BigIntBase` / `BigIntAuditBase` for integer-PK models

---

## EncryptedString / EncryptedText

Transparent encryption at rest for sensitive data. Values are encrypted before writing and decrypted on read. `EncryptedString` is for short values (API keys, tokens). `EncryptedText` is for longer payloads (notes, documents).

```python
from advanced_alchemy.types import EncryptedString, EncryptedText
from advanced_alchemy.types.encrypted_string import FernetBackend, PGCryptoBackend
```

### Backends

| Backend | Import | Notes |
| --- | --- | --- |
| `FernetBackend` | `advanced_alchemy.types.encrypted_string` | Fernet symmetric encryption (recommended default) |
| `PGCryptoBackend` | `advanced_alchemy.types.encrypted_string` | PostgreSQL pgcrypto extension (server-side) |

### Usage

```python
from advanced_alchemy.types import EncryptedString, EncryptedText
from advanced_alchemy.types.encrypted_string import FernetBackend

# Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = "your-fernet-key-here"


class UserSecret(UUIDAuditBase):
    __tablename__ = "user_secret"

    # Short encrypted value
    api_key: Mapped[str] = mapped_column(
        EncryptedString(key=ENCRYPTION_KEY, backend=FernetBackend),
    )

    # Long encrypted text
    private_notes: Mapped[str | None] = mapped_column(
        EncryptedText(key=ENCRYPTION_KEY, backend=FernetBackend),
        default=None,
    )
```

### PGCrypto Backend (PostgreSQL Only)

```python
from advanced_alchemy.types.encrypted_string import PGCryptoBackend


class SecureRecord(UUIDAuditBase):
    __tablename__ = "secure_record"

    secret: Mapped[str] = mapped_column(
        EncryptedString(key="your-encryption-key", backend=PGCryptoBackend),
    )
```

- `PGCryptoBackend` requires the PostgreSQL `pgcrypto` extension and performs encryption server-side.
- Encrypted columns cannot be used in WHERE clauses or indexes (the ciphertext changes each write).
- Store the encryption key in environment variables or a secrets manager, never in code.

---

## PasswordHash

Automatic password hashing on write with verification support. The column stores a hashed value; plain-text is never persisted.

```python
from advanced_alchemy.types import PasswordHash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher
from advanced_alchemy.types.password_hash.passlib import PasslibHasher
```

### Backends

| Backend | Library | Import path | Notes |
| --- | --- | --- | --- |
| `Argon2Hasher` | `argon2-cffi` | `advanced_alchemy.types.password_hash.argon2` | Recommended — memory-hard, resistant to GPU attacks |
| `PwdlibHasher` | `pwdlib` | `advanced_alchemy.types.password_hash.pwdlib` | Modern wrapper supporting argon2 / bcrypt |
| `PasslibHasher` | `passlib` | `advanced_alchemy.types.password_hash.passlib` | Legacy support, many algorithms |

Each backend lives in its own submodule and pulls in its hashing dependency only when imported — install the matching extra (e.g., `pip install argon2-cffi`).

### Usage

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

### Verification

```python
# Writing — plain text is automatically hashed
account = Account(email="user@example.com", password="my-secret-password")

# Verifying — use the stored PasswordHash wrapper
is_valid = account.password.verify("my-secret-password")

# Rehashing — persist the replacement hash when the backend policy changed
is_valid, new_hash = account.password.verify_and_update("my-secret-password")
if is_valid and new_hash is not None:
    account.password = new_hash
```

---

## FileObject / StoredObject

Cloud and local file storage integrated into SQLAlchemy columns. Files are stored in a configured backend (S3, GCS, Azure, local filesystem) and referenced by a JSON metadata object in the database.

```python
from advanced_alchemy.types.file_object import FileObject, StoredObject
```

### Column Definition

```python
from advanced_alchemy.types.file_object import FileObject, StoredObject


class Document(UUIDAuditBase):
    __tablename__ = "document"

    title: Mapped[str] = mapped_column()
    file: Mapped[FileObject | None] = mapped_column(StoredObject, default=None)
```

### Backend Configuration

Register storage backends at application startup. `ObstoreBackend` is the preferred backend when `advanced-alchemy[obstore]` is installed; use `FSSpecBackend` for protocols that need fsspec.

```python
from advanced_alchemy.types.file_object import storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
from obstore.store import LocalStore, S3Store

local_storage = ObstoreBackend(
    key="local",
    fs=LocalStore(prefix="/var/data/uploads"),
)
s3_storage = ObstoreBackend(
    key="documents",
    fs=S3Store(bucket="my-bucket", region="us-east-1"),
)
```

### Registering Backends

```python
from advanced_alchemy.types.file_object import storages

# Register during app startup.
storages.register_backend(s3_storage)
storages.register_backend(local_storage)
```

### Storing Files

```python
# Create a FileObject and assign to the model
file_obj = FileObject(
    filename="report.pdf",
    content_type="application/pdf",
    backend="documents",  # matches the StorageBackend key
    content=file_bytes,
)

document = Document(title="Q4 Report", file=file_obj)
await service.create(document)
```

### Reading Files

```python
document = await service.get(doc_id)
if document.file:
    content = await document.file.read()
    filename = document.file.filename
    content_type = document.file.content_type
```

---

## Bool (dialect-aware boolean)

`Bool` (added 1.11) resolves to each dialect's stock boolean type, including Oracle 23c's real `BOOLEAN` when SQLAlchemy exposes `oracle.BOOLEAN`. Older Oracle versions and SQLAlchemy 2.0.x fall back to stock SQLAlchemy `Boolean`. Use it when a model must run on Oracle as well as PostgreSQL/SQLite/MySQL.

```python
from advanced_alchemy.types import Bool
from sqlalchemy.orm import Mapped, mapped_column


class User(UUIDBase):
    is_active: Mapped[bool] = mapped_column(Bool, default=True)
```

## Vector (dialect-aware similarity search)

`Vector` (added 1.11) is a single fixed-dimension vector column that resolves per dialect — Oracle 23ai `VECTOR`, PostgreSQL/CockroachDB `pgvector` (when installed), and a JSON-array fallback everywhere else. Importing it never requires `pgvector` or `oracledb`; the backend is chosen in `load_dialect_impl`.

```python
from advanced_alchemy.types import Vector
from sqlalchemy.orm import Mapped, mapped_column


class Document(UUIDBase):
    embedding: Mapped[list[float]] = mapped_column(Vector(dim=1536))  # storage_format="FLOAT32" default
```

Similarity search uses the dialect-aware distance operators on the column's `.comparator` — `cosine_distance`, `l2_distance`, `l1_distance`, `max_inner_product` (each maps to the backend operator; the JSON fallback raises, since it has no distance operator):

```python
from sqlalchemy import select

stmt = (
    select(Document)
    .order_by(Document.embedding.cosine_distance(query_vector))
    .limit(10)
)
```

## TOTP and One-Time Codes

Added in 1.11 for authentication flows. `TOTPSecret` is an `EncryptedString` subtype that stores a TOTP shared secret encrypted at rest; it requires `pyotp` and an explicit encryption key. Pair it with `TOTPProvider` / `generate_totp_secret` to issue and verify codes. `OneTimeCode` is the SQLAlchemy column type for single-use codes (email/SMS verification); it requires an explicit password-hashing backend and loaded values expose the `HashedOneTimeCode` verification wrapper.

```python
from typing import Any

from advanced_alchemy.types import (
    TOTPSecret,
    OneTimeCode,
    generate_totp_secret,
    generate_one_time_code,
)
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
from sqlalchemy.orm import Mapped, mapped_column


class Account(UUIDBase):
    totp_secret: Mapped[str | None] = mapped_column(TOTPSecret(key=ENCRYPTION_KEY), default=None)
    # writes a plaintext code; the column hashes it. Loaded values verify through HashedOneTimeCode.
    email_code: Mapped[Any | None] = mapped_column(
        OneTimeCode(backend=Argon2Hasher(), ttl_seconds=600, max_attempts=3),
        default=None,
    )
```

## Type Compatibility Matrix

| Type | PostgreSQL | SQLite | MySQL | Oracle |
| --- | --- | --- | --- | --- |
| `DateTimeUTC` | `TIMESTAMP WITH TIME ZONE` | `DATETIME` | `DATETIME` | `TIMESTAMP WITH TIME ZONE` |
| `GUID` | `UUID` (native) | `CHAR(32)` / `BINARY(16)` | `CHAR(32)` / `BINARY(16)` | `RAW(16)` |
| `JsonB` | `JSONB` (native) | `JSON` | `JSON` | `oracle.JSON` on SQLAlchemy 2.1+ / Oracle 21c+; BLOB + check constraint fallback |
| `ORA_JSONB` | `JSONB` | `JSON` | `JSON` | `oracle.JSON` on SQLAlchemy 2.1+ / Oracle 21c+; BLOB + check constraint fallback |
| `BigIntIdentity` | `BIGSERIAL` | `INTEGER` | `BIGINT AUTO_INCREMENT` | `NUMBER(19)` |
| `EncryptedString` | `VARCHAR` | `VARCHAR` | `VARCHAR` | `VARCHAR2` |
| `EncryptedText` | `TEXT` | `TEXT` | `TEXT` | `CLOB` |
| `PasswordHash` | `VARCHAR` | `VARCHAR` | `VARCHAR` | `VARCHAR2` |
| `StoredObject` | `JSONB` | `JSON` | `JSON` | `JSON` |
| `Bool` | `BOOLEAN` | `BOOLEAN` | `BOOL` | `BOOLEAN` on SQLAlchemy 2.1+ / Oracle 23c+; stock SQLAlchemy `Boolean` fallback |
| `Vector` | `pgvector` / JSON | `JSON` | `JSON` | `VECTOR` |
