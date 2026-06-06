---
name: litestar-plugins
description: "Auto-activate for plugins=, InitPlugin, CLIPluginProtocol, SerializationPluginProtocol, OpenAPISchemaPluginProtocol, DomainPlugin, or app plugin lists. Not for package installation."
---

# Litestar Plugins

Use this skill for plugin composition, first-party plugin setup, plugin protocol authoring, and app startup wiring.

## Code Style Rules

- Prefer first-party Litestar plugins where they exist.
- Keep plugin configuration near app setup or settings modules.
- Use `InitPlugin` for reusable app initialization; keep protocol names for legacy code and non-init hooks.
- Keep domain routes and plugin lifecycle concerns separated.

## Quick Reference

- Plugin patterns: [plugins.md](references/plugins.md)
- Pair with [litestar-routing](../litestar-routing/SKILL.md) for DomainPlugin layout.
- Pair with focused first-party plugin skills when available.

<workflow>

## Workflow

1. Identify whether the task is app composition or plugin authoring.
2. Use existing first-party plugins before custom glue.
3. Register plugins in app setup with settings-backed config.
4. Test startup, shutdown, CLI, or schema behavior touched by the plugin.

</workflow>

<guardrails>

## Guardrails

- Do not hide route logic inside plugin setup.
- Do not add a custom plugin where a plain provider or middleware is enough.
- Do not scatter plugin config across unrelated modules.
- Do not bypass first-party plugins for common integrations.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Plugin config is settings-backed when environment-specific.
- [ ] Startup and shutdown behavior are covered.
- [ ] Plugin protocols match the integration point.
- [ ] App setup remains readable.

</validation>

<example>

## Example

```python
app = Litestar(
    route_handlers=[UserController],
    plugins=[DomainPlugin()],
)
```

</example>

## References Index

- [plugins.md](references/plugins.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
