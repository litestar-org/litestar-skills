# Integrations

Autowire 0.2.0 runs integrations after controller and listener discovery and
before those components are registered on `AppConfig`.

## Select an integration

`AutowireConfig.integrations` accepts:

- `"dishka"` (`DishkaIntegration`) or `"queues"` (`QueuesIntegration`);
- one `AutowireIntegration` object;
- an iterable mixing built-in names and integration objects.

Inputs normalize to a tuple of integration objects. There is no
`LitestarQueuesIntegration` or `SAQIntegration` class; use `QueuesIntegration`
for `litestar-queues` and `AutowireLoader` for SAQ or custom module registries.
The legacy `extensions=...` argument always raises:

```text
TypeError: AutowireConfig.extensions was renamed to integrations. Use integrations=[...].
```

Unknown strings raise `ValueError`. Every integration name must be non-empty
and unique. Custom integrations cannot reuse `dishka` or `queues`.

## Custom integrations

Implement the public protocol:

```python
from litestar_autowire import AutowireContext


class AuditIntegration:
    name = "audit"

    def on_autowire(self, context: AutowireContext) -> None:
        context.app_config.state["autowire_domains"] = context.feature_packages
```

`AutowireContext` exposes:

| Field | Meaning |
| --- | --- |
| `app_config` | Mutable Litestar `AppConfig` being initialized |
| `config` | Normalized `AutowireConfig` |
| `feature_packages` | Configured roots and discovered direct children |
| `controllers` | Discovered controller classes |
| `listeners` | Discovered `EventListener` objects |
| `router_class` | Configured or integration-selected router class |
| `task_names` | Task names reported by the Queues integration |
| `loaded_task_count` | Integer count reported by loader integrations |

`context.task_count` combines unique queue task names and loader counts.
`context.record_task_count(count)` rejects negative counts with `ValueError`.

Malformed custom objects raise `TypeError` unless they expose a non-empty
string `name` and callable `on_autowire`. Duplicate names and built-in-name
collisions raise `ValueError` during `AutowireConfig` construction.

## AutowireLoader

Use `AutowireLoader` when an existing registry accepts dotted module paths:

```python
from litestar_autowire import AutowireConfig, AutowireLoader

config = AutowireConfig(
    domain_packages=["my_app.domains"],
    integrations=[
        AutowireLoader(
            name="notification_handlers",
            modules=["handlers"],
            loader="my_app.registry:load_handlers",
        )
    ],
)
```

The loader runs once for each existing
`<feature_package>.<configured_module>` target. `modules` accepts a string or
iterable. `loader` accepts a callable or a `pkg.module:callable` string; dotted
attribute syntax is also resolved by 0.2.0, but prefer the explicit colon form.

Absent target modules are skipped. Missing dependencies inside an existing
target are re-raised. If the loader returns an `int`, Autowire adds it to the
startup task count; `bool` is intentionally ignored.

Precise loader failures:

- Empty `name`: `ValueError`.
- Malformed dotted callable: `ValueError`.
- Missing callable module: `ValueError`.
- Missing attribute: `ValueError`.
- Resolved non-callable attribute: `TypeError`.
- Negative integer count: `ValueError`.

## Router classes and Dishka

Set `router_class=Router` for standard Litestar router wrapping. When at least
one controller is discovered, Autowire constructs the selected class with:

```python
router_class(
    path="/",
    route_handlers=controllers,
    before_request=config.before_request,
    after_response=config.after_response,
)
```

If no controllers are discovered, `AutowirePlugin` logs a warning and skips
router instantiation.

Use the Dishka integration only when the project already uses Dishka:

```python
from litestar_autowire import AutowireConfig

config = AutowireConfig(
    domain_packages=["my_app.domains"],
    integrations=["dishka"],
)
```

Install `litestar-autowire[dishka]`. The integration selects
`dishka.integrations.litestar.DishkaRouter` only when `router_class` is unset.
It does not create a Dishka container or call `setup_dishka()`. A missing
Dishka extra raises `RuntimeError`; dependency failures within Dishka propagate.

### Dishka controller gotchas

- **Runtime type hint resolution with `from __future__ import annotations`**:
  `DishkaRouter.register` wraps each controller route handler using
  `typing.get_type_hints(func)` at router registration time. When a controller
  module enables `from __future__ import annotations`, every type referenced in
  a route handler signature (including `FromDishka[ServiceType]` and
  `ServiceType`) must exist in the module's runtime globals (`func.__globals__`).
  Hiding `ServiceType` or `FromDishka` inside `if TYPE_CHECKING:`, or defining
  them in a local function scope under `from __future__ import annotations`,
  raises `NameError` during `AutowirePlugin.on_app_init`.
- **In-place `Controller.get_route_handlers` mutation**:
  `DishkaRouter.register` mutates each `Controller` subclass in-place by
  assigning `ControllerSubclass.get_route_handlers = _inject_route_handlers(ControllerSubclass.get_route_handlers)`
  directly on the class object. Reusing the same `Controller` class across unit
  tests without restoring `get_route_handlers` leaks Dishka wrapping into later
  tests. See [Testing](testing.md) for isolation patterns.

## Litestar Queues

Use the Queues integration only when the project already uses
`litestar-queues`:

```python
from litestar_autowire import AutowireConfig

config = AutowireConfig(
    domain_packages=["my_app.domains"],
    integrations=["queues"],
    task_modules=["jobs", "scheduled"],
    force_reload_tasks=False,
)
```

Install `litestar-autowire[queues]`. For each configured root and task module
name, Autowire calls:

```python
litestar_queues.discover_tasks(
    package_name,
    subpackage=module_name,
    force_reload=force_reload_tasks,
)
```

The integration imports task modules and records returned task names. It does
not configure `QueuePlugin`, queue storage, execution, workers, schedules, or
task results.

A missing Queues extra raises `RuntimeError`. An installed
`litestar_queues` without `discover_tasks()` also raises `RuntimeError`.

## Related references

- [Discovery](discovery.md)
- [Testing](testing.md)
- [Skill overview](../SKILL.md)
- [Litestar DI](../../litestar/references/di-and-dishka.md)
- [Litestar Queues](../../litestar-queues/SKILL.md)

## Tagged source

- <https://github.com/cofin/litestar-autowire/blob/v0.2.0/litestar_autowire/integrations.py>
- <https://github.com/cofin/litestar-autowire/blob/v0.2.0/litestar_autowire/config.py>
