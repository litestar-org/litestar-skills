# Testing

Test Autowire through a real `Litestar` application when registration behavior
matters. Test the public discovery functions directly when isolating package
traversal or import failures.

## Clear caches

Discovery caches successful imports and optional-module misses. Use an
autouse fixture when tests create temporary packages:

```python
import pytest
from litestar_autowire import clear_autowire_cache


@pytest.fixture(autouse=True)
def isolate_autowire_cache() -> None:
    clear_autowire_cache()
    yield
    clear_autowire_cache()
```

Also remove temporary package names from `sys.modules` before recreating them.
Changing files or `sys.path` alone does not invalidate Python's import cache or
Autowire's discovery cache.

## Test controller registration

Create a package under `tmp_path`, prepend the directory to `sys.path`, and
construct the application:

```python
from pathlib import Path

from litestar import Litestar
from litestar.testing import TestClient
from litestar_autowire import AutowireConfig, AutowirePlugin


def test_discovers_controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    controller_file = tmp_path / "sample_app" / "domains" / "accounts" / "controllers.py"
    controller_file.parent.mkdir(parents=True)
    controller_file.write_text(
        """
from litestar import Controller, get


class AccountController(Controller):
    path = "/accounts"

    @get()
    async def list_accounts(self) -> dict[str, str]:
        return {"status": "ok"}
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    app = Litestar(
        plugins=[
            AutowirePlugin(
                AutowireConfig(domain_packages=["sample_app.domains"]),
            )
        ],
    )

    with TestClient(app=app) as client:
        response = client.get("/accounts")

    assert response.status_code == 200
```

This layout intentionally omits `__init__.py` and therefore exercises PEP 420
namespace discovery. Add `__init__.py` files when testing regular-package
behavior instead.

## Test listeners

Place a `@listener(...)` object in `events.py` or `listeners.py`, construct the
app, and assert against `app.event_emitter.listeners`. Disable controller
discovery when the test concerns listeners only:

```python
config = AutowireConfig(
    domain_packages=["sample_app.domains"],
    discover_controllers=False,
)
```

## Test custom integrations

Use a small integration object and assert against the resulting app config or
application:

```python
from litestar_autowire import AutowireContext


class MarkerIntegration:
    name = "marker"

    def on_autowire(self, context: AutowireContext) -> None:
        context.app_config.state["autowire_marker"] = True
```

Do not mock `AutowireIntegration`; a concrete object verifies runtime protocol
validation and lifecycle ordering together.

For `AutowireLoader`, create only the target module that should load and record
the module paths passed to the loader. Test callable and
`"pkg.module:callable"` forms separately. Return an integer only when the test
also asserts the deferred startup task count.

## Test import errors

Protect the fail-fast boundary with two separate cases:

1. Configure a package or component module that does not exist and assert that
   discovery returns no component for it.
2. Create an existing package that imports a deliberately missing dependency
   and assert that the exact `ModuleNotFoundError` propagates.

Use a unique dependency name and assert `exc_info.value.name`. Do not broadly
match error text; the missing-module name proves Autowire did not misclassify an
internal dependency as an optional target.

## Test optional integrations

- Dishka: provide or monkeypatch `dishka.integrations.litestar.DishkaRouter`;
  assert controllers are reachable through the selected router.
- Queues: provide or monkeypatch `litestar_queues.discover_tasks`; assert the
  calls contain `(domain_package, task_module, force_reload_tasks)`.
- Missing extras: remove only the top-level optional package and assert the
  documented `RuntimeError`.
- Broken optional dependencies: raise `ModuleNotFoundError` for a nested
  dependency and assert it propagates unchanged.

## Related references

- [Discovery](discovery.md)
- [Integrations](integrations.md)
- [Skill overview](../SKILL.md)
- [Litestar Testing](../../litestar-testing/SKILL.md)

## Tagged tests

- <https://github.com/cofin/litestar-autowire/blob/v0.2.0/tests/unit/test_autowire_plugin.py>
