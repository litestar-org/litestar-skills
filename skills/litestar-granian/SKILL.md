---
name: litestar-granian
description: "Auto-activate for litestar_granian, GranianPlugin, litestar run Granian options, runtime threads, HTTP/2, TLS, access logs, metrics, static mounts, or Granian worker lifecycle. Not for another ASGI server's native CLI — use that server's documentation."
---

# litestar-granian

`litestar-granian` 0.15.0 replaces Litestar's `run` command with a Granian-backed
command and integrates Granian loggers with Litestar logging. It requires
Granian 2.7 or later.

## Code Style Rules

- Keep handlers async when they perform I/O.
- Configure the server at the command line. `GranianPlugin()` has no constructor
  options.
- Use the `litestar run` option names documented here. Do not substitute
  similarly named options from older Granian or Uvicorn releases.

## Quick Reference

### Register the plugin

```python
from litestar import Litestar, get
from litestar_granian import GranianPlugin


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[health],
    plugins=[GranianPlugin()],
)
```

```bash
litestar --app app:app run
```

`GranianPlugin` registers the Granian-backed `run` command. During app
initialization, it adds missing `_granian` and `granian.access` logger entries
and a compatible formatter without replacing user-defined entries. It also
handles the standard-library logging configuration wrapped by Litestar's
`StructlogPlugin`.

### Defaults in 0.15.0

| Concern | Default |
| --- | --- |
| Bind | `127.0.0.1:8000` |
| HTTP mode | `auto` |
| Workers | `1` |
| Runtime threads | `1` per worker |
| Runtime mode | `auto` |
| Event loop | `auto` |
| Async task implementation | `asyncio` |
| Backlog | `1024` globally |
| Backpressure | `backlog / workers` per worker |
| Granian log | Enabled at `info` |
| Access log | Disabled |
| WebSockets | Enabled except in HTTP/2-only mode |
| Process mode | Subprocess |
| Reload | Disabled |
| Metrics | Disabled unless `PrometheusPlugin` is detected; `127.0.0.1:9090` when enabled |
| Static-file cache | `86400` seconds; no implicit route or mount |
| Minimum TLS protocol | TLS 1.3 |

The 0.15.0 release changed `--runtime-mode` from `st` to `auto`. Pin
`--runtime-mode st` only when preserving the earlier single-thread runtime is
intentional.

### Valid production controls

```bash
litestar --app app:app run \
    --host 0.0.0.0 \
    --workers 4 \
    --runtime-mode auto \
    --runtime-threads 1 \
    --backpressure 1024 \
    --granian-access-log
```

Use these option families:

| Concern | Options |
| --- | --- |
| Processes and runtime | `--workers`, `--blocking-threads`, `--runtime-threads`, `--runtime-blocking-threads`, `--runtime-mode`, `--loop`, `--task-impl` |
| Capacity | `--backlog`, `--backpressure` |
| Protocols | `--http`, `--ws` / `--no-ws`, `--http1-*`, `--http2-*` |
| Granian logging | `--granian-log`, `--granian-log-level`, `--granian-access-log`, `--granian-access-log-fmt` |
| Litestar logging | `--use-litestar-logger`, `--log-config` |
| TLS | `--ssl-certificate` (`--ssl-certfile` alias), `--ssl-keyfile`, `--ssl-keyfile-password`, `--ssl-protocol-min`, `--ssl-ca`, `--ssl-crl`, `--ssl-client-verify` |
| Worker lifecycle | `--respawn-failed-workers`, `--respawn-interval`, `--workers-lifetime`, `--workers-kill-timeout`, `--workers-max-rss`, `--rss-sample-interval`, `--rss-samples` |
| Reload | `--reload`, `--reload-paths` (`--reload-include` alias), `--reload-ignore-dirs` (`--reload-exclude` alias), `--reload-ignore-patterns`, `--reload-ignore-paths`, `--reload-tick` |
| Operations | `--uds`, `--process-name`, `--pid-file`, `--working-dir`, `--env-files`, `--metrics`, `--metrics-address`, `--metrics-port`, `--metrics-scrape-interval` |
| Static mounts | repeatable `--static-path-route` and `--static-path-mount`, plus `--static-path-dir-to-file` and `--static-path-expires` |

`--static-path-route` and `--static-path-mount` pair by position. Pass both;
0.15.0 removed the implicit `/static` route. `--static-path-expires` accepts
durations such as `1h` and `1d`; pass `0` to disable caching.

When Litestar's `PrometheusPlugin` is registered, the tagged 0.15.0
implementation enables Granian metrics whenever the parsed metrics value is
false. This includes an explicit `--no-metrics`; 0.15.0 has no CLI opt-out from
that auto-detection while the plugin remains registered.

<workflow>

## Workflow

### Step 1: Match the project's deployment stack

Use `GranianPlugin` when the project already uses `litestar-granian` or needs
its Granian-specific CLI, HTTP/2, runtime, worker-lifecycle, metrics, or static
mount controls.

Keep the project's existing ASGI server when its deployment platform, process
manager, observability, or operational runbooks depend on that server. Do not
replace an established server solely because Granian is available.

Use the bare `granian` CLI only when deployment tooling intentionally invokes
Granian directly. Its CLI is a separate surface; consult the matching Granian
release instead of copying `litestar run` options.

### Step 2: Install and register

```bash
pip install "litestar-granian==0.15.0"
```

Add `GranianPlugin()` to `Litestar(plugins=[...])`, then run the application
through `litestar --app <module>:<app> run`.

### Step 3: Choose direct or subprocess mode

Subprocess mode is the default:

```bash
litestar --app app:app run --in-subprocess
```

It invokes `python -m granian` in a child process. The child does not inherit
the parent's Python logging configuration. Pass `--use-litestar-logger` to
serialize and forward the Litestar logging configuration, or pass an explicit
JSON `--log-config`.

Direct mode runs Granian in the Litestar CLI process:

```bash
litestar --app app:app run --no-subprocess
```

Direct mode passes the selected logging dict directly to Granian instead of
serializing it to a temporary file. Pass `--use-litestar-logger` in either mode
when Granian should derive its dict configuration from Litestar.
`--reload --no-subprocess` is supported in 0.15.0.

### Step 4: Configure the deployment

Measure the application before changing workers, runtime threads, or
backpressure. Preserve the `auto` runtime defaults unless load tests justify a
specific runtime mode.

Terminate TLS at the platform proxy when that is the project's established
boundary. For Granian-managed TLS, pass both the certificate and key:

```bash
litestar --app app:app run \
    --ssl-certificate /etc/ssl/certs/app.crt \
    --ssl-keyfile /etc/ssl/private/app.key
```

### Step 5: Verify the effective command

```bash
litestar --app app:app run --help
```

Confirm the required options appear, start the service in the selected process
mode, exercise health and WebSocket endpoints, and load-test production
capacity settings.

</workflow>

<guardrails>

## Guardrails

- **Use the runtime-specific thread controls.** The 0.15.0 command exposes
  `--runtime-threads`, `--runtime-blocking-threads`, and `--runtime-mode`.
- **Use the namespaced access-log controls.** The 0.15.0 command exposes
  `--granian-access-log` and `--granian-access-log-fmt`.
- **Do not treat the plugin CLI as the bare Granian CLI.** The option names
  overlap but are not identical.
- **Do not claim that registering the plugin changes every deployment.**
  `GranianPlugin` replaces Litestar's `run` command; an external ASGI command
  still controls its own server lifecycle.
- **Do not force Granian into an established deployment stack.** Match the
  server to the project's platform and operational requirements.
- **Do not enable HTTP/2-only mode for a WebSocket endpoint.** The 0.15.0
  launcher disables WebSockets when `--http http2` is selected.
- **Do not rely on an implicit static route.** Pair every repeatable
  `--static-path-route` with a `--static-path-mount`.
- **Do not assume subprocess mode inherits Litestar logging.** Use
  `--use-litestar-logger` or `--log-config`.
- **Do not treat `--no-metrics` as a `PrometheusPlugin` override.** The tagged
  0.15.0 implementation auto-enables Granian metrics after parsing that flag.
- **Do not perform blocking I/O in an async handler.** It blocks the worker's
  async runtime.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] The project intentionally selected Granian over its existing ASGI server.
- [ ] `GranianPlugin()` is registered when deployment uses `litestar run`.
- [ ] Every documented option appears in `litestar run --help`.
- [ ] Direct or subprocess mode is selected explicitly in deployment
      documentation.
- [ ] Subprocess logging uses `--use-litestar-logger` or an intentional Granian
      log configuration.
- [ ] HTTP/2-only mode is not used for required WebSocket endpoints.
- [ ] Static routes and mounts have equal counts and are paired in order.
- [ ] Granian metrics exposure accounts for `PrometheusPlugin` auto-detection.
- [ ] Worker, thread, and capacity changes are backed by load-test results.
- [ ] TLS terminates at the documented platform or Granian boundary.

</validation>

<example>

## Example

**Task:** Run an existing Litestar application with Granian in direct mode,
enable access logs, and expose Granian metrics to a local collector.

```python
from litestar import Litestar, get
from litestar_granian import GranianPlugin


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[health],
    plugins=[GranianPlugin()],
)
```

```bash
litestar --app app:app run \
    --host 0.0.0.0 \
    --no-subprocess \
    --granian-access-log \
    --metrics \
    --metrics-address 127.0.0.1 \
    --metrics-port 9090
```

When Litestar's `PrometheusPlugin` is registered, 0.15.0 automatically enables
Granian metrics at the configured metrics address and port.

</example>

## References Index

- [litestar](../litestar/SKILL.md) — application initialization and plugin
  registration.
- [litestar-deployment](../litestar-deployment/SKILL.md) — deployment target,
  proxy, container, and process-manager selection.
- [litestar-plugins](../litestar-plugins/SKILL.md) — Litestar plugin protocols
  and initialization behavior.

## Official References

- [litestar-granian v0.15.0 source](https://github.com/cofin/litestar-granian/tree/v0.15.0)
- [v0.15.0 CLI implementation](https://github.com/cofin/litestar-granian/blob/v0.15.0/litestar_granian/cli.py)
- [v0.15.0 plugin implementation](https://github.com/cofin/litestar-granian/blob/v0.15.0/litestar_granian/plugin.py)
- [v0.15.0 changelog](https://github.com/cofin/litestar-granian/blob/v0.15.0/docs/changelog.rst)
- [litestar-granian 0.15.0 on PyPI](https://pypi.org/project/litestar-granian/0.15.0/)

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
