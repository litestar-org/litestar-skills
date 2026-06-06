---
name: litestar-dto-openapi
description: "Auto-activate for MsgspecDTO, DTOConfig, litestar.dto, OpenAPIConfig, response DTOs, schema_extra, RequestEncodingType, or /schema. Not for persistence models alone."
---

# Litestar DTO and OpenAPI

Use this skill for DTO selection, msgspec-first schemas, request/response typing, and OpenAPI shape.

## Code Style Rules

- Prefer msgspec DTOs in Litestar apps unless the project is already Pydantic-led.
- Keep persistence models separate from API DTOs.
- Use camelCase wire names while Python stays snake_case.
- Exclude server-owned fields from write DTOs.

## Quick Reference

- DTO patterns: [dto.md](references/dto.md)
- Pair with [litestar-data-services](../litestar-data-services/SKILL.md) when mapping service results.
- Pair with [msgspec](../msgspec/SKILL.md) for deeper Struct modeling.

<workflow>

## Workflow

1. Identify input, output, and persistence shapes separately.
2. Choose msgspec DTOs or match the existing Pydantic stack.
3. Configure excludes, partial updates, rename behavior, and media type.
4. Check the generated OpenAPI schema.

</workflow>

<guardrails>

## Guardrails

- Do not leak internal persistence-only fields into write DTOs.
- Do not switch an existing Pydantic-heavy project to msgspec opportunistically.
- Do not rely on untyped dict payloads when request shape is known.
- Do not treat OpenAPI as documentation only; it is the contract.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Request and response DTOs are explicit.
- [ ] Wire names match the API convention.
- [ ] Server-owned fields are excluded from writes.
- [ ] /schema output matches the intended contract.

</validation>

<example>

## Example

```python
from litestar.dto import DTOConfig, MsgspecDTO

class UserWriteDTO(MsgspecDTO[UserWrite]):
    config = DTOConfig(exclude={"id", "created_at"})
```

</example>

## References Index

- [dto.md](references/dto.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
