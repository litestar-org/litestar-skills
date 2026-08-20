# Granian Embedded Runtime, Supervisor, and Lifecycle

Detailed guide covering programmatic embedded Granian execution, parent supervisor lifecycle management, signal forwarding, native static provider discovery, and logging serialization.

## Embedded Programmatic Runtime

In addition to the `litestar run` CLI, Granian can be instantiated and executed programmatically within Python scripts, integration test runners, or custom deployment harnesses.

```python
from pathlib import Path
from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes
from granian.http import HTTP1Settings, HTTP2Settings


def start_server() -> None:
    """Run an embedded Granian instance programmatically."""
    server = Granian(
        target="app.server:app",
        address="0.0.0.0",
        port=8000,
        interface=Interfaces.ASGI,
        workers=2,
        runtime_mode=RuntimeModes.auto,
        runtime_threads=1,
        loop=Loops.auto,
        http=HTTPModes.auto,
        websockets=True,
        backlog=1024,
        backpressure=512,
        http1_settings=HTTP1Settings(keep_alive=True),
        http2_settings=HTTP2Settings(adaptive_window=True),
        log_enabled=True,
        log_access=True,
        log_access_format='[%(time)s] "%(method)s %(path)s" %(status)d %(dt_ms).3f',
        ssl_cert=Path("/etc/ssl/certs/app.crt"),
        ssl_key=Path("/etc/ssl/private/app.key"),
        metrics_enabled=False,
    )
    server.serve()


if __name__ == "__main__":
    start_server()
```

### Interface Types (`granian.constants.Interfaces`)

- `Interfaces.ASGI` (`"asgi"`): Standard Asynchronous Server Gateway Interface consumed by Litestar.
- `Interfaces.RSGI` (`"rsgi"`): Granian's native Rust Server Gateway Interface for zero-copy buffer transfers and optimized asynchronous Python execution.
- `Interfaces.WSGI` (`"wsgi"`): Synchronous Web Server Gateway Interface.
- `Interfaces.ASGINL` (`"asginl"`): ASGI No-Lifespan variant for environments where lifespan events are handled externally.

---

## Supervisor and Process Lifecycle

When executing `litestar run` with `GranianPlugin`, the execution model consists of a supervising parent process and a supervised child process group.

```text
┌────────────────────────────────────────────────────────┐
│  Litestar CLI Parent Process                           │
│  1. Parses CLI arguments and validates TLS/options     │
│  2. Serializes active logging formatter to JSON config │
│  3. Discovers static mounts (if static="auto")         │
│  4. Enters Litestar Server Lifespans                   │
│     - Sidecar environment variables injected:          │
│       * LITESTAR_APP = "app:app"                       │
│       * LITESTAR_HOST = "127.0.0.1"                    │
│       * LITESTAR_PORT = "8000"                         │
│  5. Spawns Granian child process group / session       │
│  6. Installs signal forwarder (SIGINT, SIGTERM, etc.)  │
│  7. Monitors child and enforces shutdown deadlines     │
│  8. Exits lifespan context cleanly after child exit    │
└──────────────────────────┬─────────────────────────────┘
                           │ Supervised child group
┌──────────────────────────▼─────────────────────────────┐
│  Granian Child Process Group (granian CLI / _runner)   │
│  - Master process manages worker pool                  │
│  - Worker 1 .. Worker N execute ASGI application       │
└────────────────────────────────────────────────────────┘
```

### Signal Handling and Termination Deadlines

1. **Process Isolation:**
   - **POSIX:** Spawns Granian with `start_new_session=True`. Signals sent to the parent process are forwarded to the entire child process group using `os.killpg(process.pid, signum)`.
   - **Windows:** Spawns Granian with `CREATE_NEW_PROCESS_GROUP`. Termination is signaled via `CTRL_BREAK_EVENT`.

2. **Two-Stage Graceful Shutdown:**
   - **Stage 1 (Graceful Request Drain):** When the first `SIGINT` (Ctrl+C) or `SIGTERM` arrives, the supervisor forwards the signal to the child group and arms a deadline timer calculated as `workers_kill_timeout + 5.0` seconds (10 seconds with the CLI defaults).
   - **Stage 2 (Forced Termination):** If a second termination signal arrives before the child exits, or if the deadline timer expires, the supervisor immediately kills the process group with `SIGKILL` (POSIX) or `taskkill /PID <pid> /T /F` (Windows).

3. **Normalized Exit Status:**
   If the child process terminates due to a signal, the supervisor translates negative return codes into standard POSIX shell exit statuses: `128 + signum`.

4. **Lifespan Unwinding:**
   Litestar server lifespans (e.g. database connection pools, queue consumers, background task schedulers) remain active for the duration of Granian's execution and are unwound in the parent process during exit stack cleanup, even after forced termination.

---

## Native Static Provider Discovery (`static="auto"`)

The `GranianPlugin(static="auto")` feature enables Granian's Rust core to serve static files directly from the filesystem, bypassing Python ASGI event loop dispatch.

### Discovery Protocol

When `static="auto"` is configured:

1. `litestar-granian` inspects all plugins registered on the `Litestar` application.
2. It filters for plugins implementing the `get_static_server_config()` protocol (such as `litestar-vite`).
3. If **exactly one** valid static provider is found, its configuration is validated:
   - Placement must be `"native"`.
   - Mount routes must be local absolute URL paths (e.g. `/static/web/`).
   - Directories must exist on disk and contain at least one file.
   - All mounts must share a consistent directory index (e.g. `index.html`).
4. If validation succeeds, Granian natively configures `--static-path-route`, `--static-path-mount`, and `--static-path-expires`.
5. If zero or multiple static providers exist, or if validation fails, the supervisor logs an informational message (`"Using Litestar for static files"`) and falls back to Litestar's standard ASGI static routing.

### Explicit CLI Precedence

Explicit CLI options (`--static-path-route` and `--static-path-mount`) always override and supersede automatic provider discovery. When passing explicit flags, routes and mounts must be paired positional tuples with matching lengths.

---

## Logging Serialization Bridge

Granian runs in child worker processes and cannot share Python logger locks, stream handlers, or memory references with the parent process.

To provide consistent log formatting without cross-process corruption:

1. `litestar_granian.logging.build_logging_config` inspects the parent application's logging configuration (standard library `logging` or `StructlogPlugin`).
2. It extracts and pickles the active `Formatter` instance.
3. It generates a temporary JSON configuration file with `load_serialized_formatter` instructions for Granian worker processes.
4. Granian workers reconstruct identical formatting instances locally in child processes.
5. Providing an explicit `--log-config /path/to/config.json` CLI option overrides this bridge completely.

---

## Observability and Prometheus Metrics

Granian includes a native Prometheus metrics exporter:

```bash
litestar --app app:app run \
    --metrics \
    --metrics-address 0.0.0.0 \
    --metrics-port 9090 \
    --metrics-scrape-interval 15
```

### Metrics Scope and Behavior

- **Exposed Data:** Rust runtime performance, TCP connection counts, in-flight backpressure queues, HTTP/1 & HTTP/2 stream counts, and worker memory metrics.
- **Endpoint:** Serves Prometheus metrics on `http://<metrics-address>:<metrics-port>/metrics`.
- **Application Request Metrics:** `--metrics` exports server-level metrics only. For Litestar route-level metrics (status codes, handler durations, route labels), register Litestar's `PrometheusPlugin` on the `Litestar` application.
