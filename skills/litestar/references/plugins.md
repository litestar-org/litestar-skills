# Plugins (`InitPluginProtocol`, lifecycle, ecosystem)

Plugins are the canonical way to extend Litestar — first-party plugins compose into `Litestar(plugins=[...])`, and you can author your own with `InitPluginProtocol` / `CLIPluginProtocol`.

## Custom Plugin (`InitPluginProtocol`)

```python
from __future__ import annotations

from dataclasses import dataclass

from litestar.plugins import InitPluginProtocol
from litestar.config.app import AppConfig


@dataclass
class MyPluginConfig:
    enabled: bool = True
    api_key: str | None = None


class MyPlugin(InitPluginProtocol):
    __slots__ = ("config",)

    def __init__(self, config: MyPluginConfig | None = None) -> None:
        self.config = config or MyPluginConfig()

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        if not self.config.enabled:
            return app_config
        # Mutate app_config: register routes, middleware, deps, state
        app_config.state["my_plugin"] = self
        app_config.dependencies["my_plugin"] = Provide(lambda: self)
        return app_config
```

## Plugin Lifecycle

| Hook | Protocol | When |
| --- | --- | --- |
| `on_app_init(app_config)` | `InitPluginProtocol` | App boot, before `Litestar.__init__` finishes |
| `on_cli_init(cli)` | `CLIPluginProtocol` | When the `litestar` CLI builds its Click group |
| Lifespan startup/shutdown | Register via `app_config.lifespan.append(...)` | App start / stop |

## State Sharing

Plugins typically expose themselves via `app_config.state["name"] = self` and a matching `Provide`. Handlers can then accept the plugin as a typed dependency:

```python
class MyController(Controller):
    @get("/")
    async def index(self, my_plugin: MyPlugin) -> dict:
        return {"key_set": my_plugin.config.api_key is not None}
```

## First-Party Ecosystem

These plugins ship as separate packages and have their own SKILLs in this repo. Use them in preference to hand-rolled glue:

| Plugin | Sibling skill | Purpose |
| --- | --- | --- |
| `litestar-granian` | `../../litestar-granian/SKILL.md` | Granian ASGI server (replaces uvicorn CLI) |
| `litestar-saq` | `../../litestar-saq/SKILL.md` | SAQ task queues + cron + workers |
| `litestar-vite` | `../../litestar-vite/SKILL.md` | Vite frontend integration, TypeGen, Inertia |
| `litestar-mcp` | `../../litestar-mcp/SKILL.md` | MCP tools/resources over JSON-RPC 2.0 |
| `litestar-email` | `../../litestar-email/SKILL.md` | Email backends (SMTP, Resend, SendGrid, Mailgun) |
| `advanced-alchemy` | `../../advanced-alchemy/SKILL.md` | Repository/Service patterns, audit base |
| `litestar-asyncpg` | (not yet) | Direct AsyncPG pool lifespan |
| `litestar-oracledb` | (not yet) | OracleDB pool lifespan |

## Wiring Multiple Plugins

```python
from __future__ import annotations

from litestar import Litestar
from litestar_granian import GranianPlugin
from litestar_saq import SAQPlugin, SAQConfig, QueueConfig
from litestar_vite import VitePlugin, ViteConfig
from litestar_mcp import LitestarMCP, MCPConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

from app.lib.settings import get_settings
from app.lib.exceptions import ApplicationError, application_exception_handler


settings = get_settings()

app = Litestar(
    route_handlers=[...],
    exception_handlers={ApplicationError: application_exception_handler},
    plugins=[
        GranianPlugin(),
        SQLAlchemyPlugin(config=SQLAlchemyAsyncConfig(connection_string=settings.database.url)),
        SAQPlugin(config=SAQConfig(
            use_server_lifespan=True,
            queue_configs=[QueueConfig(name="default", dsn=settings.redis.url)],
        )),
        VitePlugin(config=ViteConfig(dev_mode=settings.debug)),
        LitestarMCP(MCPConfig(name=settings.name)),
    ],
)
```

## Cross-references

- Plugin-supplied dependencies (e.g. `TaskQueues`, `EmailService`): see each sibling skill
- Channels plugin (real-time pub/sub): [websockets.md](websockets.md)
- DomainPlugin auto-discovery: [domains.md](domains.md)
