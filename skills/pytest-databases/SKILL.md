---
name: pytest-databases
description: "Auto-activate for pytest_databases imports, conftest.py with database fixtures. Container-based database testing with pytest. Use when: creating PostgreSQL/MySQL/SQLite/Oracle fixtures, Docker test containers, database integration tests, or any pytest database setup. Produces container-based database test fixtures with proper lifecycle management. Not for mocking databases or non-pytest test frameworks."
---

# pytest-databases

A pytest plugin providing ready-made database fixtures for testing using Docker containers.

---

<workflow>

## References Index

For detailed guides and code examples, refer to the following documents in `references/`:

- **[Supported Databases](references/databases.md)**
  - Examples for PostgreSQL, MySQL, Oracle with service/connection fixtures.
- **[Complete Reference](references/reference.md)**
  - Fixture tables for all supported SQL, KV, Search, and Object Storage databases.
- **[Xdist Parallel Testing](references/xdist.md)**
  - Isolation levels (database vs server) and helper functions.
- **[Configuration](references/config.md)**
  - Fixture overrides and environment variable support.
- **[Troubleshooting](references/troubleshooting.md)**
  - ARM architecture tips, port conflicts, and health checks.

## Quick Start

### 1. Enable in Project

Add to `conftest.py`:

```python
pytest_plugins = ["pytest_databases.docker.postgres"]
```

### 2. Use Fixtures

```python
def test_database(postgres_service):
    # Use postgres_service.host, .port, etc.
    pass
```

</workflow>

---

## Cross-References

- **[litestar-testing](../litestar-testing/SKILL.md)** — Litestar-specific testing patterns; integrates pytest-databases fixtures with `AsyncTestClient`.

## Official References

- <https://github.com/litestar-org/pytest-databases>
- <https://litestar-org.github.io/pytest-databases/latest/>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../../../.agents/code-styleguides/general.md)
- [Testing](../../../.agents/code-styleguides/testing.md)
- [Python](../../../.agents/code-styleguides/python.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
