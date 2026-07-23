# Discovery

Autowire 0.2.0 discovers components from dotted domain package roots. Pass a
string or iterable of strings to `domain_packages`; the normalized public value
is a tuple.

## Package traversal

For each configured root, discovery includes:

1. The configured root package itself.
2. Each direct importable child package reported by `pkgutil.iter_modules()`.
3. Each direct visible child directory found under every entry in the root
   package's `__path__`.

The filesystem scan is what supports PEP 420 namespace domains without
`__init__.py`. Child directories beginning with `_` or `.` are ignored. Domain
discovery does not recursively treat grandchildren as new feature packages.

The configured root must expose `__path__`. A missing configured root or a
module without `__path__` contributes no components and emits a warning.

## Controller discovery

The default controller module names are:

```python
("controllers", "routes", "controller", "route")
```

For every feature package and configured module name, Autowire:

1. Imports `<feature_package>.<module_name>` when it exists.
2. If that target is a package, walks its importable non-package descendants.
3. Selects public `Controller` subclasses defined directly in each inspected
   module.
4. Deduplicates selected classes by object identity.

Imported or re-exported controller classes are excluded because their
`__module__` does not match the inspected module. The `Controller` base class
and names beginning with `_` are also excluded.

## Listener discovery

The default listener module names are:

```python
("events", "listeners")
```

Listener discovery follows the same module traversal as controllers and selects
objects that are instances of Litestar's `EventListener`. Results are
deduplicated by object identity and appended to `AppConfig.listeners`.

Disable either built-in component type explicitly:

```python
from litestar_autowire import AutowireConfig

config = AutowireConfig(
    domain_packages=["my_app.domains"],
    discover_controllers=False,
    discover_listeners=True,
)
```

Autowire does not discover standalone route-handler functions. Put routes on a
`Controller`, write a custom integration, or compose those handlers manually.

## Optional task discovery

Core discovery does not inspect task decorators. The built-in `queues`
integration calls `litestar_queues.discover_tasks()` for every configured
domain root and configured `task_modules` name. The default is `("jobs",)`.

See [Integrations](integrations.md) for the Queues boundary and
`force_reload_tasks`.

## Import failure behavior

Autowire distinguishes an optional target that is absent from a broken target
that imports a missing dependency:

- Missing configured package: warn and skip it.
- Missing controller, listener, or loader target module: skip it.
- `ModuleNotFoundError` raised by a dependency inside an existing package or
  target module: re-raise it unchanged.
- Other import exceptions: re-raise them unchanged.

Never catch these errors broadly around app construction. A broken domain must
fail startup instead of disappearing from the route or listener registry.

## Discovery caches

The process-local caches cover:

- feature packages per configured root;
- controller results per package/module-name tuple;
- listener results per package/module-name tuple;
- successful optional module imports;
- missing optional module results.

Public discovery functions return copies where appropriate so callers cannot
mutate cached lists. Clear every cache with:

```python
from litestar_autowire import clear_autowire_cache

clear_autowire_cache()
```

Clear caches when tests alter `sys.path` or `sys.modules`, when dynamic package
contents change, and before intentional rediscovery in reload tooling.

## Related references

- [Integrations](integrations.md)
- [Testing](testing.md)
- [Skill overview](../SKILL.md)

## Tagged source

- <https://github.com/cofin/litestar-autowire/blob/v0.2.0/litestar_autowire/discovery.py>
- <https://github.com/cofin/litestar-autowire/blob/v0.2.0/litestar_autowire/plugin.py>
