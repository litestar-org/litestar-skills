# Vector search with sqlspec

This reference covers similarity search for semantic retrieval and intent classification against embeddings stored in the same transactional database as the application's data. It documents the Oracle `VECTOR_DISTANCE(..., COSINE)` pattern in full (sourced from [oracledb-vertexai-demo](https://github.com/cofin/oracledb-vertexai-demo)) with pgvector cross-reference for PostgreSQL stacks. For the Litestar handler and ADK runner that consume these services, see [`../../litestar-ai-serving/references/ai-serving.md`](../../litestar-ai-serving/references/ai-serving.md).

## Backend support matrix

| Backend | Distance operator | Similarity expression | Row limit |
| --- | --- | --- | --- |
| Oracle | `VECTOR_DISTANCE(:a, :b, COSINE)` | `1 - VECTOR_DISTANCE(...)` | `FETCH FIRST :n ROWS ONLY` |
| PostgreSQL + pgvector | `:a <=> :b` | `1 - (:a <=> :b)` | `LIMIT :n` |
| SQLite + sqlite-vec | `vec_distance_cosine(:a, :b)` | `1 - vec_distance_cosine(...)` | `LIMIT :n` |

This reference documents the **Oracle** path in full (sourced from `oracledb-vertexai-demo`). See [pgvector branch (short)](#pgvector-branch-short) for the PostgreSQL equivalent; full pgvector coverage will land when a canonical pgvector reference app is available.

## Vector-search service pattern (Oracle)

Cosine distance is converted to similarity via `1 - VECTOR_DISTANCE(..., COSINE)` so that higher values mean more similar. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/products/services/services.py:L42–53`.

`SQLSpecAsyncService` ships upstream in `sqlspec.service`. Use it for services that wrap an async driver with helpers like `paginate`, `get_one`, `exists`, and `begin_transaction`.

```python
from typing import Any
from sqlspec.service import SQLSpecAsyncService


class VectorSearchService(SQLSpecAsyncService):
    async def search_by_vector(
        self,
        query_embedding: list[float],
        similarity_threshold: float = 0.7,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT id, title, description,
               1 - VECTOR_DISTANCE(embedding, :query_vector, COSINE) AS similarity_score
          FROM record
         WHERE 1 - VECTOR_DISTANCE(embedding, :query_vector, COSINE) > :threshold
         ORDER BY similarity_score DESC
         FETCH FIRST :limit ROWS ONLY
        """
        return await self.driver.select(
            sql,
            {"query_vector": query_embedding, "threshold": similarity_threshold, "limit": limit},
        )
```

Key idioms:

- `1 - VECTOR_DISTANCE(..., COSINE)` converts distance (lower = closer) to similarity (higher = better).
- Threshold filter before `ORDER BY` avoids returning low-confidence matches.
- Oracle uses `FETCH FIRST :limit ROWS ONLY` — not the ANSI `LIMIT :n`.

## Generating embeddings (Vertex AI)

Call `client.aio.models.embed_content(model, text)` and extract the first embedding's values list. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/products/services/services.py:L93–100`.

```python
from google import genai


async def generate_embedding(
    client: genai.Client,
    model: str,
    text: str,
) -> list[float] | None:
    response = await client.aio.models.embed_content(
        model=model,
        contents=text,
    )
    embedding_list = response.embeddings
    if not embedding_list or not embedding_list[0].values:
        return None
    return embedding_list[0].values
```

**Match-Your-Stack:** the abstraction boundary is `embed(model, text) -> list[float] | None`. If the project uses OpenAI embeddings, replace the `genai` call with `openai.AsyncOpenAI().embeddings.create(model=model, input=text)` and extract `.data[0].embedding`. The cache and search layers are provider-agnostic.

## Embedding cache

A SQL-based cache keyed by `SHA256(text)` avoids redundant embedding API calls. `ON CONFLICT DO NOTHING` is safe under concurrent inserts. `hit_count` and `last_accessed` support decay-based eviction if needed. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/system/services/services.py:L155–180`.

```python  # pragma: legacy-example
import hashlib
from typing import Any
from app.lib.service import SQLSpecAsyncService


class EmbeddingCacheService(SQLSpecAsyncService):
    async def get_embedding(self, text: str, model: str) -> list[float] | None:
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        sql = "SELECT embedding FROM embedding_cache WHERE text_hash = :hash AND model = :model"
        row = await self.driver.select_one_or_none(sql, {"hash": text_hash, "model": model})
        if row:
            await self.driver.execute(
                "UPDATE embedding_cache SET hit_count = hit_count + 1,"
                " last_accessed = CURRENT_TIMESTAMP WHERE text_hash = :hash",
                {"hash": text_hash},
            )
            return list(row["embedding"]) if isinstance(row["embedding"], list) else None
        return None

    async def save_embedding(self, text: str, embedding: list[float], model: str) -> None:
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        sql = """
        INSERT INTO embedding_cache (text_hash, embedding, model)
             VALUES (:hash, :emb, :model)
        ON CONFLICT (text_hash) DO NOTHING
        """
        await self.driver.execute(sql, {"hash": text_hash, "emb": embedding, "model": model})
```

Call `get_embedding` before calling the Vertex AI API; call `save_embedding` on a cache miss. This cache is SQL-resident — no Redis required for embedding dedup.

## Intent classification via exemplar similarity

Store labeled exemplar phrases with pre-computed embeddings in an `intent_exemplar` table. At query time, embed the user input and retrieve the top-K most-similar exemplars. Each row carries a `confidence_threshold` column — if the top match's similarity falls below the threshold, the intent is treated as ambiguous. Canonical source: `oracledb-vertexai-demo/src/py/app/domain/system/services/services.py:L226–234`.

```python
async def search_similar_intents(
    self,
    query_embedding: list[float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    sql = """
    SELECT intent, phrase,
           1 - VECTOR_DISTANCE(embedding, :query_vector, COSINE) AS similarity,
           confidence_threshold
      FROM intent_exemplar
     ORDER BY similarity DESC
     FETCH FIRST :limit ROWS ONLY
    """
    return await self.driver.select(sql, {"query_vector": query_embedding, "limit": limit})
```

Example result set:

| intent | phrase | similarity | confidence_threshold |
| --- | --- | --- | --- |
| `SEARCH` | "find me something to …" | 0.92 | 0.80 |
| `HELP` | "how does this work?" | 0.87 | 0.75 |
| `CONVERSATION` | "thanks for your help" | 0.61 | 0.70 |

Neutral-domain intent labels: `SEARCH`, `HELP`, `PURCHASE`, `SUPPORT`, `CONVERSATION`. The `confidence_threshold` gates whether the top match is trusted — if `similarity < confidence_threshold`, fall back to a default intent or prompt the user to clarify.

## Schema sketch

DDL for the three tables this pattern uses (Oracle syntax; adapt `VECTOR(768)` dimension to your embedding model):

```sql
-- Semantic content store
CREATE TABLE record (
    id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title        VARCHAR2(255)   NOT NULL,
    description  CLOB,
    embedding    VECTOR(768)
);

-- SHA256-keyed embedding cache
CREATE TABLE embedding_cache (
    text_hash    VARCHAR2(64)    PRIMARY KEY,
    embedding    VECTOR(768)     NOT NULL,
    model        VARCHAR2(64)    NOT NULL,
    hit_count    NUMBER          DEFAULT 0,
    last_accessed TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
);

-- Intent exemplar store
CREATE TABLE intent_exemplar (
    id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    intent               VARCHAR2(64)    NOT NULL,
    phrase               CLOB            NOT NULL,
    embedding            VECTOR(768)     NOT NULL,
    confidence_threshold FLOAT           DEFAULT 0.75
);
```

Use `VECTOR(1536)` if using OpenAI's `text-embedding-3-small` model, or `VECTOR(768)` for Vertex AI `gemini-embedding-001`.

## Vertex AI settings

`VertexAISettings` is a plain `@dataclass` loaded from environment variables. Strip application-specific defaults (e.g., any app-name prefix) before reusing in a new project. Canonical source: `oracledb-vertexai-demo/src/py/app/lib/settings.py:L283–318`.

```python
import os
from dataclasses import dataclass, field


@dataclass
class VertexAISettings:
    PROJECT_ID: str = field(
        default_factory=lambda: os.getenv("VERTEX_AI_PROJECT_ID", "")
    )
    LOCATION: str = field(
        default_factory=lambda: os.getenv("VERTEX_AI_LOCATION") or "us-central1"
    )
    API_KEY: str | None = field(
        default_factory=lambda: (
            os.getenv("VERTEX_AI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
    )
    EMBEDDING_MODEL: str = field(
        default_factory=lambda: os.getenv(
            "VERTEX_AI_EMBEDDING_MODEL", "gemini-embedding-001"
        )
    )
    EMBEDDING_DIMENSIONS: int = 768
    CHAT_MODEL: str = field(
        default_factory=lambda: os.getenv(
            "VERTEX_AI_CHAT_MODEL", "gemini-1.5-flash-001"
        )
    )
    CACHE_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("VERTEX_AI_CACHE_TTL_SECONDS", "3600"))
    )
```

## pgvector branch (short)

For PostgreSQL stacks with the `pgvector` extension, replace the Oracle `VECTOR_DISTANCE(..., COSINE)` expression with the `<=>` cosine-distance operator. Requires `CREATE EXTENSION vector` on the database.

```sql
SELECT id, title, description,
       1 - (embedding <=> :query_vector) AS similarity_score
  FROM record
 WHERE 1 - (embedding <=> :query_vector) > :threshold
 ORDER BY similarity_score DESC
 LIMIT :limit
```

The `<=>` operator returns cosine distance (0 = identical, 2 = opposite); `1 - (embedding <=> :query_vector)` converts it to the same `[−1, 1]` similarity scale used in the Oracle path. See the [pgvector documentation](https://github.com/pgvector/pgvector) for index types (`ivfflat`, `hnsw`) that accelerate ANN queries at scale.

## Cross-references

- [`../../litestar-ai-serving/references/ai-serving.md`](../../litestar-ai-serving/references/ai-serving.md) — Litestar handler, ADK Runner wiring, Dishka provider chain, persona-augmented prompts
- [`./service-patterns.md`](./service-patterns.md) — `SQLSpecAsyncService` base, named SQL templates, driver API
- [`./observability.md`](./observability.md) — SQL broadcast telemetry (applies to embedding inserts if observability is needed)

## Shared Styleguide Baseline

- [`../litestar-styleguide/references/general.md`](../litestar-styleguide/references/general.md) — Cross-language baseline
- [`../litestar-styleguide/references/python.md`](../litestar-styleguide/references/python.md) — Python conventions
- [`../litestar-styleguide/references/litestar.md`](../litestar-styleguide/references/litestar.md) — Litestar-specific baseline
