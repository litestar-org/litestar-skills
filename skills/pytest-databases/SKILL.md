---
name: pytest-databases
description: "Auto-activate for pytest_databases imports, conftest.py database fixtures, Docker-backed PostgreSQL/MySQL/SQLite/Oracle tests, or integration-test database lifecycle. Use when configuring pytest database containers and fixtures. Not for mocked databases or non-pytest test frameworks."
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

<guardrails>

## Guardrails

- **Keep fixtures container-based.** Do not monkey-patch or mock the database client — prefer the real service fixture so tests cover driver behavior.
- **Use `xdist` isolation helpers.** For parallel runs, select the `database`-level or `server`-level isolation fixtures from `references/xdist.md` instead of sharing one schema across workers.
- **Do not hand-roll container lifecycle.** Rely on the plugin's fixtures; they handle startup, readiness, and teardown.
- **Scope fixtures to the smallest unit that works.** A session-scoped Docker container with function-scoped schemas is almost always the right trade-off.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] `conftest.py` declares only the database plugins you actually use (`pytest_plugins = [...]`)
- [ ] Tests pull the correct fixture (`postgres_service`, `mysql_service`, etc.) rather than opening raw connections
- [ ] Parallel runs (`pytest -n auto`) produce isolated data — verified via `references/xdist.md`
- [ ] CI runs Docker-in-Docker (or Podman) with enough resources for the requested fixtures

</validation>

<example>

## Example: PostgreSQL integration test

```python
import pytest

pytest_plugins = ["pytest_databases.docker.postgres"]


@pytest.mark.asyncio
async def test_user_insert(postgres_service, postgres_connection):
    await postgres_connection.execute(
        "INSERT INTO users (email) VALUES ($1)", "alice@example.com"
    )
    row = await postgres_connection.fetchrow(
        "SELECT email FROM users WHERE email = $1", "alice@example.com"
    )
    assert row["email"] == "alice@example.com"
```

</example>

---

## Cross-References

- **[litestar-testing](../litestar-testing/SKILL.md)** — Litestar-specific testing patterns; integrates pytest-databases fixtures with `AsyncTestClient`.

## Official References

- <https://github.com/litestar-org/pytest-databases>
- <https://litestar-org.github.io/pytest-databases/latest/>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Testing](../litestar-styleguide/references/testing.md)
- [Python](../litestar-styleguide/references/python.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
