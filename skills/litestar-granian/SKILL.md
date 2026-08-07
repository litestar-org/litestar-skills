---
name: litestar-granian
description: "Auto-activate for litestar_granian, GranianPlugin, litestar run Granian options, runtime threads, HTTP/2, TLS, access logs, metrics, static mounts, or Granian worker lifecycle. Not for another ASGI server's native CLI — use that server's documentation."
---

# litestar-granian

`litestar-granian` 0.16.0 replaces Litestar's `run` command with a Granian-backed
command and integrates Granian loggers with Litestar logging. It requires
Granian 2.7 or later.

## Code Style Rules

- Keep handlers async when they perform I/O.
- Configure the server at the command line. `GranianPlugin` takes only an
  optional `static` mode keyword argument.
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

### Defaults in 0.16.0

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
| Process mode | Supervised (always) |
| Reload | Disabled |
| Metrics | Disabled; `127.0.0.1:9090` when enabled with `--metrics` |
| Static-file cache | `86400` seconds; no implicit route or mount |
| Minimum TLS protocol | TLS 1.3 |

Release 0.15.0 changed `--runtime-mode` from `st` to `auto`. Pin
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
| Litestar logging | `--log-config` (formatter matching is automatic) |
| TLS | `--ssl-certificate` (`--ssl-certfile` alias), `--ssl-keyfile`, `--ssl-keyfile-password`, `--ssl-protocol-min`, `--ssl-ca`, `--ssl-crl`, `--ssl-client-verify` |
| Worker lifecycle | `--respawn-failed-workers`, `--respawn-interval`, `--workers-lifetime`, `--workers-kill-timeout`, `--workers-max-rss`, `--rss-sample-interval`, `--rss-samples` |
| Reload | `--reload`, `--reload-paths` (`--reload-include` alias), `--reload-ignore-dirs` (`--reload-exclude` alias), `--reload-ignore-patterns`, `--reload-ignore-paths`, `--reload-tick` |
| Operations | `--uds`, `--process-name`, `--pid-file`, `--working-dir`, `--env-files`, `--metrics`, `--metrics-address`, `--metrics-port`, `--metrics-scrape-interval` |
| Static mounts | repeatable `--static-path-route` and `--static-path-mount`, plus `--static-path-dir-to-file` and `--static-path-expires` |

`--static-path-route` and `--static-path-mount` pair by position. Pass both;
Release 0.15.0 removed the implicit `/static` route. `--static-path-expires` accepts
durations such as `1h` and `1d`; pass `0` to disable caching.

### Supervision and Litestar CLI parity

`litestar run` has one execution model: the Litestar parent enters server
lifespans once and supervises a fresh Granian child process group.

- POSIX starts Granian in a new session and forwards signals to the process
  group. Windows uses a new process group and `CTRL_BREAK_EVENT` for graceful
  shutdown, escalating to list-based `taskkill` only if needed.
- The first termination signal is forwarded once and starts a deadline of
  `--workers-kill-timeout` plus five seconds. A second signal or an expired
  deadline kills the process group.
- Litestar's server lifespans stay active until Granian exits, and are still
  unwound after forced termination.
- Server-lifespan sidecars receive the resolved `LITESTAR_APP`,
  `LITESTAR_HOST`, and `LITESTAR_PORT`, which is how frontend dev-server
  sidecars learn the real bind.

0.16.0 restored these Litestar-compatible options:

| Option | Purpose |
| --- | --- |
| `-I` / `--reload-include`, `-E` / `--reload-exclude` | Litestar glob behavior; reload directories and filters enable reload automatically |
| `-F` / `--fd` / `--file-descriptor` | Inherited socket support (POSIX) |
| `-U` / `--unix-domain-socket` | Alias for Granian's native `--uds` |
| `--pdb` / `--use-pdb`, `LITESTAR_PDB=true` | Propagates Litestar's `pdb_on_exception` into Granian workers |

The deprecated `InitPluginProtocol` base is replaced by `InitPlugin`. The
deprecated `--in-subprocess` and `--use-litestar-logger` switches are planned
for removal in 0.17.

### Native static discovery

`GranianPlugin(static=...)` is the plugin's only constructor option:

```python
app = Litestar(route_handlers=[health], plugins=[GranianPlugin(static="auto")])
```

`"off"` (the default) keeps Litestar's static routing. `"auto"` lets Granian
serve exactly one compatible static provider natively when its configuration is
safe, and falls back to Litestar otherwise. Explicit `--static-path-*` CLI
mounts always take precedence over either mode. Any other value raises
`ValueError` at construction.

Metrics are off by default and are controlled only by `--metrics` /
`--no-metrics`; 0.16.0 removed the `PrometheusPlugin` auto-detection that
earlier releases applied. `--metrics` exposes Granian server and worker metrics
only. When no Litestar Prometheus middleware is detected, the command warns that
application-level request metrics are not being exported — register Litestar's
`PrometheusPlugin` as well when those are wanted.

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
pip install "litestar-granian==0.16.0"
```

Add `GranianPlugin()` to `Litestar(plugins=[...])`, then run the application
through `litestar --app <module>:<app> run`.

### Step 3: Configure logging

0.16.0 always uses supervised execution and matches Granian's formatter to
Litestar's automatically. There is no mode to choose:

```bash
litestar --app app:app run
```

`--in-subprocess` / `--no-subprocess` and `--use-litestar-logger` /
`--no-litestar-logger` are accepted for compatibility, but they are ignored and
print a deprecation warning. Remove them from deployment scripts.

Pass an explicit JSON `--log-config` only when overriding the automatic
formatter matching completely.

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

Confirm the required options appear, start the service, exercise health and
WebSocket endpoints, and load-test production capacity settings.

</workflow>

<guardrails>

## Guardrails

- **Use the runtime-specific thread controls.** The 0.16.0 command exposes
  `--runtime-threads`, `--runtime-blocking-threads`, and `--runtime-mode`.
- **Use the namespaced access-log controls.** The 0.16.0 command exposes
  `--granian-access-log` and `--granian-access-log-fmt`.
- **Do not treat the plugin CLI as the bare Granian CLI.** The option names
  overlap but are not identical.
- **Do not claim that registering the plugin changes every deployment.**
  `GranianPlugin` replaces Litestar's `run` command; an external ASGI command
  still controls its own server lifecycle.
- **Do not force Granian into an established deployment stack.** Match the
  server to the project's platform and operational requirements.
- **Do not enable HTTP/2-only mode for a WebSocket endpoint.** The 0.16.0
  launcher disables WebSockets when `--http http2` is selected.
- **Do not rely on an implicit static route.** Pair every repeatable
  `--static-path-route` with a `--static-path-mount`.
- **Do not pass the deprecated compatibility flags.** `--in-subprocess` /
  `--no-subprocess` and `--use-litestar-logger` / `--no-litestar-logger` are
  ignored in 0.16.0 and emit warnings.
- **Do not expect `--metrics` to export request metrics.** It exposes Granian
  server and worker metrics only; register Litestar's `PrometheusPlugin` for
  application-level request metrics.
- **Do not perform blocking I/O in an async handler.** It blocks the worker's
  async runtime.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] The project intentionally selected Granian over its existing ASGI server.
- [ ] `GranianPlugin()` is registered when deployment uses `litestar run`.
- [ ] Every documented option appears in `litestar run --help`.
- [ ] Deployment scripts no longer pass the deprecated `--in-subprocess` or
      `--use-litestar-logger` compatibility flags.
- [ ] Logging relies on automatic formatter matching or an intentional
      `--log-config` override.
- [ ] HTTP/2-only mode is not used for required WebSocket endpoints.
- [ ] Static routes and mounts have equal counts and are paired in order.
- [ ] `--metrics` is paired with Litestar's `PrometheusPlugin` when request metrics are required.
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
    --granian-access-log \
    --metrics \
    --metrics-address 127.0.0.1 \
    --metrics-port 9090
```

`--metrics` exposes Granian server and worker metrics at the configured address
and port. Register Litestar's `PrometheusPlugin` alongside it to also export
application-level request metrics.

</example>

## References Index

- [litestar](../litestar/SKILL.md) — application initialization and plugin
  registration.
- [litestar-deployment](../litestar-deployment/SKILL.md) — deployment target,
  proxy, container, and process-manager selection.
- [litestar-plugins](../litestar-plugins/SKILL.md) — Litestar plugin protocols
  and initialization behavior.

## Official References

- [litestar-granian v0.16.0 source](https://github.com/cofin/litestar-granian/tree/v0.16.0)
- [v0.16.0 CLI implementation](https://github.com/cofin/litestar-granian/blob/v0.16.0/litestar_granian/cli.py)
- [v0.16.0 plugin implementation](https://github.com/cofin/litestar-granian/blob/v0.16.0/litestar_granian/plugin.py)
- [v0.16.0 changelog](https://github.com/cofin/litestar-granian/blob/v0.16.0/docs/changelog.rst)
- [litestar-granian 0.16.0 on PyPI](https://pypi.org/project/litestar-granian/0.16.0/)

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
