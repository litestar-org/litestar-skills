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

- Always pass timezone-aware datetimes when writing; naive datetimes are assumed UTC
- Reads always return `datetime` with `tzinfo=timezone.utc`

---

## GUID

Cross-database UUID type. Uses native `UUID` column on PostgreSQL. Falls back to `CHAR(32)` storing hex on other backends (SQLite, MySQL, Oracle).

```python
from advanced_alchemy.types import GUID

class Token(UUIDAuditBase):
    __tablename__ = "token"

    external_id: Mapped[UUID] = mapped_column(GUID)
```

- Transparent round-trip: you always work with Python `uuid.UUID` objects
- The AA base classes (`UUIDBase`, `UUIDAuditBase`, etc.) already use `GUID` for their `id` column

---

## JsonB

Cross-database JSONB type. Uses native `JSONB` on PostgreSQL (with indexing support). Falls back to standard `JSON` on other databases.

```python
from advanced_alchemy.types import JsonB

class Config(UUIDAuditBase):
    __tablename__ = "config"

    settings: Mapped[dict] = mapped_column(JsonB, default=dict)
    tags: Mapped[list] = mapped_column(JsonB, default=list)
```

- On PostgreSQL, supports GIN indexing for fast key/value lookups
- On SQLite/MySQL, stores as JSON text

---

## ORA_JSONB

Oracle-compatible JSONB type. Handles Oracle's specific JSON column semantics while remaining compatible with other databases.

```python
from advanced_alchemy.types import ORA_JSONB

class OracleModel(UUIDAuditBase):
    __tablename__ = "oracle_model"

    metadata_: Mapped[dict] = mapped_column(ORA_JSONB, default=dict)
```

- Use when targeting Oracle as a primary or secondary database
- Falls back to standard JSON behavior on non-Oracle backends

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
fernet = FernetBackend(key=ENCRYPTION_KEY)


class UserSecret(UUIDAuditBase):
    __tablename__ = "user_secret"

    # Short encrypted value
    api_key: Mapped[str] = mapped_column(
        EncryptedString(backend=fernet),
    )

    # Long encrypted text
    private_notes: Mapped[str | None] = mapped_column(
        EncryptedText(backend=fernet),
        default=None,
    )
```

### PGCrypto Backend (PostgreSQL Only)

```python
from advanced_alchemy.types.encrypted_string import PGCryptoBackend

pg_backend = PGCryptoBackend(key="your-encryption-key")


class SecureRecord(UUIDAuditBase):
    __tablename__ = "secure_record"

    secret: Mapped[str] = mapped_column(
        EncryptedString(backend=pg_backend),
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

# Verifying — compare plain text against the stored hash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

hasher = Argon2Hasher()
is_valid = hasher.verify("my-secret-password", account.password)
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

StoredObject uses `obstore` for cloud storage. Configure backends at application startup:

```python
from advanced_alchemy.types.file_object import StorageBackend, FileObject

# S3 backend
s3_storage = StorageBackend(
    key="documents",
    backend="s3",
    options={
        "bucket": "my-bucket",
        "region": "us-east-1",
        "access_key_id": "...",
        "secret_access_key": "...",
    },
)

# GCS backend
gcs_storage = StorageBackend(
    key="uploads",
    backend="gcs",
    options={
        "bucket": "my-gcs-bucket",
        "service_account_path": "/path/to/credentials.json",
    },
)

# Local filesystem backend
local_storage = StorageBackend(
    key="local",
    backend="file",
    options={
        "root": "/var/data/uploads",
    },
)
```

### Registering Backends

```python
from advanced_alchemy.types.file_object import storages

# Register during app startup — `storages` is a module-level `StorageRegistry`
# singleton; `register_backend` is a method on it.
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
    data=file_bytes,
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

## Type Compatibility Matrix

| Type | PostgreSQL | SQLite | MySQL | Oracle |
| --- | --- | --- | --- | --- |
| `DateTimeUTC` | `TIMESTAMP WITH TIME ZONE` | `DATETIME` | `DATETIME` | `TIMESTAMP WITH TIME ZONE` |
| `GUID` | `UUID` (native) | `CHAR(32)` | `CHAR(32)` | `CHAR(32)` |
| `JsonB` | `JSONB` (native) | `JSON` | `JSON` | `JSON` |
| `ORA_JSONB` | `JSONB` | `JSON` | `JSON` | `JSON` (Oracle-optimized) |
| `BigIntIdentity` | `BIGSERIAL` | `INTEGER` | `BIGINT AUTO_INCREMENT` | `NUMBER(19)` |
| `EncryptedString` | `VARCHAR` | `VARCHAR` | `VARCHAR` | `VARCHAR2` |
| `EncryptedText` | `TEXT` | `TEXT` | `TEXT` | `CLOB` |
| `PasswordHash` | `VARCHAR` | `VARCHAR` | `VARCHAR` | `VARCHAR2` |
| `StoredObject` | `JSONB` | `JSON` | `JSON` | `JSON` |
