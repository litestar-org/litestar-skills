# CLI Discovery, Commands, Environment Variables, and Project Config

## Application Autodiscovery

When `litestar` runs without `--app` or `LITESTAR_APP`, it searches the working directory (or `--app-dir`) in this exact order:

1. **Module / package paths checked**:
   - `app.py`
   - `app/__init__.py` and all submodules inside `app/`
   - `application.py`
   - `application/__init__.py` and all submodules inside `application/`
2. **Symbols checked within each module**:
   - `app` or `application` bound to a `Litestar` instance
   - Any global variable whose value is an instance of `Litestar`
   - `create_app` callable
   - Any callable whose return annotation is `Litestar` (`-> Litestar`)

When using a `src/` layout (for example `src/app/main.py` or `src/my_service/asgi.py`), set `LITESTAR_APP` explicitly or pass `--app` / `--app-dir`:

```bash
export LITESTAR_APP="app.main:create_app"
litestar --app app.main:create_app --app-dir src info
```

If `python-dotenv` is installed, the Litestar CLI automatically loads `.env` from the current working directory before resolving `LITESTAR_*` variables. Set `LITESTAR_WARN_IMPLICIT_ENV_HEADERS=0` to silence the implicit `.env` loading notice.

## Built-in CLI Environment Variables

| Environment Variable | CLI Flag Equivalent | Purpose |
| --- | --- | --- |
| `LITESTAR_APP` | `--app` | Import path in `module:attribute` format (`app.asgi:create_app`). |
| `LITESTAR_APP_NAME` | — | Display name used by the CLI banner. |
| `LITESTAR_HOST` | `--host` (`-H`) | Bind host for `litestar run` (default `127.0.0.1`). |
| `LITESTAR_PORT` | `--port` (`-p`) | Bind port for `litestar run` (default `8000`). |
| `LITESTAR_RELOAD` | `--reload` (`-r`) | Enable file-watcher auto-reload during development. |
| `LITESTAR_RELOAD_DIRS` | `--reload-dir` (`-R`) | Comma-separated directories watched when reload is active. |
| `LITESTAR_RELOAD_INCLUDES` | `--reload-include` (`-i`) | Glob patterns included in reload watching. |
| `LITESTAR_RELOAD_EXCLUDES` | `--reload-exclude` (`-e`) | Glob patterns excluded from reload watching. |
| `LITESTAR_WEB_CONCURRENCY` / `WEB_CONCURRENCY` | `--wc` | Number of server worker processes (default `1`). |
| `LITESTAR_DEBUG` | `--debug` (`-d`) | Enable Litestar debug mode at startup. |
| `LITESTAR_PDB` | `--pdb` (`-P`) | Drop into `pdb` on unhandled application exceptions. |
| `LITESTAR_QUIET_CONSOLE` | `-q` / `--quiet-console` | Suppress non-essential Rich console output. |
| `LITESTAR_FILE_DESCRIPTOR` | `--fd` | Bind server to an existing file descriptor. |
| `LITESTAR_UNIX_DOMAIN_SOCKET` | `--uds` | Bind server to a Unix domain socket path. |
| `LITESTAR_SSL_CERT_PATH` | `--ssl-certfile` | TLS certificate file path for `litestar run`. |
| `LITESTAR_SSL_KEY_PATH` | `--ssl-keyfile` | TLS private key file path for `litestar run`. |
| `LITESTAR_CREATE_SELF_SIGNED_CERT` | `--create-self-signed-cert` | Generate a local self-signed TLS certificate if none exists. |

## Built-in CLI Commands

| Command | Purpose |
| --- | --- |
| `litestar info` | Print resolved Litestar version, debug status, app path, and installed plugins. |
| `litestar run` | Run the development server (Uvicorn by default, or Granian when `GranianPlugin` from `litestar-granian` is registered). |
| `litestar routes` | Render the registered route table (`--schema` includes OpenAPI routes; `--exclude` filters path patterns). |
| `litestar version` | Print the installed Litestar version (`-s` / `--short` omits release metadata). |
| `litestar schema openapi` | Export the OpenAPI schema to `--output` (`openapi_schema.json` or `.yaml` / `.yml`). |
| `litestar schema typescript` | Export TypeScript OpenAPI types to `--output` (`api-specs.ts`) under `--namespace` (`API`). |
| `litestar sessions delete <session-id>` | Delete a specific server-side session from the configured session backend store. |
| `litestar sessions clear` | Clear all sessions from the configured session backend store. |

First-party plugins attach subcommands automatically when registered in `Litestar(plugins=[...])`:

- `SQLAlchemyPlugin` (`advanced-alchemy`): `litestar database ...` (Alembic migrations, fixtures, table drop/create)
- `GranianPlugin` (`litestar-granian`): replaces `litestar run` with the Granian Rust HTTP server
- `SAQPlugin` (`litestar-saq`): `litestar workers ...`
- `QueuePlugin` (`litestar-queues`): `litestar queues ...`
- `VitePlugin` (`litestar-vite`): `litestar assets ...`

## Extending the CLI (`CLIPlugin` and `server_lifespan`)

Subclass `CLIPlugin` (or implement `CLIPluginProtocol`) to register custom Click commands on the `litestar` group or wrap the `litestar run` server process lifecycle:

```python
from collections.abc import Iterator
from contextlib import contextmanager

import click
from litestar import Litestar
from litestar.plugins import CLIPlugin, InitPlugin
from litestar.config.app import AppConfig


class MaintenancePlugin(InitPlugin, CLIPlugin):
    """Register a custom CLI subcommand and wrap server process startup."""

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        return app_config

    def on_cli_init(self, cli: click.Group) -> None:
        @cli.command(name="seed-reference-data")
        def seed_reference_data(app: Litestar) -> None:
            """Seed reference tables using the resolved Litestar app."""
            click.echo(f"Seeding data for {app.debug=}")

    @contextmanager
    def server_lifespan(self, app: Litestar) -> Iterator[None]:
        """Run once around the CLI server process before workers fork."""
        _ = app
        yield
```

## Project Configuration (`pyproject.toml` and `litestar.toml`)

While the core `litestar` CLI reads `--app`, `.env`, and `LITESTAR_*` environment variables, Litestar ecosystem tools (`litestar-vite`, project templates, and IDE/agent hooks) read `[tool.litestar]` in `pyproject.toml` or a root `litestar.toml` file:

```toml
[tool.litestar]
app = "app.asgi:create_app"

[tool.litestar.vite]
bundle_dir = "public"
resource_dir = "resources"
use_server_lifespan = true
```

Keep environment-specific values (credentials, hosts, ports, DSNs) in `.env` / typed settings classes ([`settings.md`](settings.md)), and keep static project layout metadata in `pyproject.toml`.
