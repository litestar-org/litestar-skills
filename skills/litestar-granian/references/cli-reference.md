# Granian & litestar-granian CLI Reference

Complete reference for CLI options available in `litestar run` (provided by
`litestar-granian` 0.16.0). The standalone `granian` CLI is a separate surface.

## `litestar run` Options Matrix

When `GranianPlugin` is registered, Litestar's `run` command provides the following options:

### Sockets and Network Binding

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `-H`, `--host` | `LITESTAR_HOST` / `GRANIAN_HOST` | `TEXT` | `127.0.0.1` | Host address to bind to. |
| `-p`, `--port` | `LITESTAR_PORT` / `GRANIAN_PORT` | `INTEGER` | `8000` | Port to bind to. |
| `-U`, `--uds`, `--unix-domain-socket` | `LITESTAR_UNIX_DOMAIN_SOCKET` / `GRANIAN_UDS` | `PATH` | `None` | Unix Domain Socket path to bind to (POSIX only). |
| `--uds-permissions` | `GRANIAN_UDS_PERMISSIONS` | `OCTAL` | `None` | Unix Domain Socket file permissions (e.g. `660`). |
| `-F`, `--fd`, `--file-descriptor` | `LITESTAR_FILE_DESCRIPTOR` / `GRANIAN_FILE_DESCRIPTOR` | `INTEGER` | `None` | Inherited pre-bound file descriptor (POSIX only; socket activation). |
| `--url-path-prefix` | `GRANIAN_URL_PATH_PREFIX` | `TEXT` | `None` | URL path prefix the application is mounted behind. |

### Concurrency and Runtime Model

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `-W`, `--wc`, `--web-concurrency`, `--workers` | `LITESTAR_WEB_CONCURRENCY` / `WEB_CONCURRENCY` / `GRANIAN_WORKERS` | `INTEGER >= 1` | `1` | Number of workers (processes on GIL builds; threads on free-threaded builds). |
| `--runtime-mode` | `GRANIAN_RUNTIME_MODE` | `auto`, `mt`, `st` | `auto` | Runtime threading mode (`auto`, multi-threaded `mt`, single-threaded `st`; `auto` resolves to `mt` on ASGI). |
| `--runtime-threads` | `GRANIAN_RUNTIME_THREADS` | `INTEGER >= 1` | `1` | Number of Rust network-I/O threads per worker. |
| `--runtime-blocking-threads` | `GRANIAN_RUNTIME_BLOCKING_THREADS` | `INTEGER >= 1` | `None` (`512` in Granian) | Number of runtime I/O blocking threads per worker. |
| `--blocking-threads` | `GRANIAN_BLOCKING_THREADS` | `INTEGER >= 1` | `None` (`1` on ASGI) | Number of Python-interpreter threads per worker; fixed to `1` on ASGI/RSGI (`> 1` raises `ConfigurationError`). |
| `--blocking-threads-idle-timeout` | `GRANIAN_BLOCKING_THREADS_IDLE_TIMEOUT` | `DURATION` (5-600s) | `30` | Idle timeout in seconds before terminating unused blocking threads. |
| `--loop` | `GRANIAN_LOOP` | `auto`, `asyncio`, `rloop`, `uvloop`, `winloop` | `auto` | Event loop implementation. |
| `--task-impl` | `GRANIAN_TASK_IMPL` | `asyncio`, `rust` | `asyncio` | Async task scheduling implementation (`rust` is experimental and falls back to `asyncio` on Python >= 3.12). |
| `--backlog` | `GRANIAN_BACKLOG` | `INTEGER >= 128` | `1024` | Global connection backlog queue capacity. |
| `--backpressure` | `GRANIAN_BACKPRESSURE` | `INTEGER >= 1` | `backlog / workers` | Maximum accepted connections per worker before the accept loop pauses. |

### Protocols and HTTP Tuning

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--http` | `GRANIAN_HTTP` | `auto`, `1`, `2` | `auto` | HTTP protocol version. |
| `--ws` / `--no-ws` | `GRANIAN_WEBSOCKETS` | `BOOLEAN` | `True` | WebSockets support (auto-disabled in HTTP/2-only mode). |
| `--http1-buffer-size` | `GRANIAN_HTTP1_BUFFER_SIZE` | `INTEGER >= 8192` | `417792` | Maximum buffer size for HTTP/1 connections. |
| `--http1-header-read-timeout` | `GRANIAN_HTTP1_HEADER_READ_TIMEOUT` | `INTEGER (1-60000ms)` | `30000` | Timeout in milliseconds to read HTTP/1 headers. |
| `--http1-keep-alive` / `--no-http1-keep-alive` | `GRANIAN_HTTP1_KEEP_ALIVE` | `BOOLEAN` | `True` | Enable HTTP/1 persistent connections. |
| `--http1-pipeline-flush` / `--no-http1-pipeline-flush` | `GRANIAN_HTTP1_PIPELINE_FLUSH` | `BOOLEAN` | `False` | Aggregate HTTP/1 flushes for pipelined responses (experimental). |
| `--http2-adaptive-window` / `--no-http2-adaptive-window` | `GRANIAN_HTTP2_ADAPTIVE_WINDOW` | `BOOLEAN` | `False` | Enable adaptive flow control for HTTP/2. |
| `--http2-initial-connection-window-size` | `GRANIAN_HTTP2_INITIAL_CONNECTION_WINDOW_SIZE` | `INTEGER >= 1024` | `1048576` | Connection-level flow control window size for HTTP/2. |
| `--http2-initial-stream-window-size` | `GRANIAN_HTTP2_INITIAL_STREAM_WINDOW_SIZE` | `INTEGER >= 1024` | `1048576` | Stream-level flow control window size (`SETTINGS_INITIAL_WINDOW_SIZE`). |
| `--http2-keep-alive-interval` | `GRANIAN_HTTP2_KEEP_ALIVE_INTERVAL` | `INTEGER (1-60000ms)` | `None` | Interval in milliseconds between HTTP/2 ping frames. |
| `--http2-keep-alive-timeout` | `GRANIAN_HTTP2_KEEP_ALIVE_TIMEOUT` | `DURATION >= 1s` | `20` | Timeout in seconds for HTTP/2 ping acknowledgement. |
| `--http2-max-concurrent-streams` | `GRANIAN_HTTP2_MAX_CONCURRENT_STREAMS` | `INTEGER >= 10` | `200` | Maximum concurrent streams per connection (`SETTINGS_MAX_CONCURRENT_STREAMS`). |
| `--http2-max-frame-size` | `GRANIAN_HTTP2_MAX_FRAME_SIZE` | `INTEGER >= 1024` | `16384` | Maximum frame size for HTTP/2. |
| `--http2-max-headers-size` | `GRANIAN_HTTP2_MAX_HEADERS_SIZE` | `INTEGER >= 1` | `16777216` | Maximum size of received header frames in bytes. |
| `--http2-max-send-buffer-size` | `GRANIAN_HTTP2_MAX_SEND_BUFFER_SIZE` | `INTEGER >= 1024` | `409600` | Maximum write buffer size per HTTP/2 stream. |

### TLS and SSL

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--ssl-certfile`, `--ssl-certificate` | `LITESTAR_SSL_CERT_PATH` / `GRANIAN_SSL_CERTIFICATE` | `FILE` | `None` | Path to SSL/TLS certificate chain file. |
| `--ssl-keyfile` | `LITESTAR_SSL_KEY_PATH` / `GRANIAN_SSL_KEYFILE` | `FILE` | `None` | Path to SSL/TLS private key file (PKCS#8 format only). |
| `--ssl-keyfile-password` | `GRANIAN_SSL_KEYFILE_PASSWORD` | `TEXT` | `None` | Password for encrypted private key file. |
| `--ssl-protocol-min` | `GRANIAN_SSL_PROTOCOL_MIN` | `tls1.2`, `tls1.3` | `tls1.3` | Minimum supported TLS protocol version. |
| `--ssl-ca` | `GRANIAN_SSL_CA` | `FILE` | `None` | Root CA certificate file for client verification (mTLS). |
| `--ssl-crl` | `GRANIAN_SSL_CRL` | `FILE` (repeatable) | `None` | Certificate Revocation List (CRL) files. |
| `--ssl-client-verify` / `--no-ssl-client-verify` | `LITESTAR_SSL_CLIENT_VERIFY` / `GRANIAN_SSL_CLIENT_VERIFY` | `BOOLEAN` | `False` | Enable client certificate verification (requires `--ssl-ca`). |
| `--create-self-signed-cert` | `LITESTAR_CREATE_SELF_SIGNED_CERT` | `BOOLEAN` | `False` | Generate ephemeral self-signed certificates when cert/key files are missing. |

### Logging

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--granian-log` / `--granian-no-log` | `GRANIAN_LOG_ENABLED` | `BOOLEAN` | `True` | Enable or disable Granian internal server logging. |
| `--granian-log-level` | `GRANIAN_LOG_LEVEL` | `critical`, `error`, `warning`, `warn`, `info`, `debug`, `notset` | `info` | Log level for Granian loggers. |
| `--granian-access-log` / `--granian-no-access-log` | `GRANIAN_LOG_ACCESS_ENABLED` | `BOOLEAN` | `False` | Enable access logging. |
| `--granian-access-log-fmt` | `GRANIAN_LOG_ACCESS_FMT` | `TEXT` | `None` | Custom access log format string (supports `%(addr)s`, `%(time)s`, `%(dt_ms).3f`, `%(status)d`, `%(path)s`, `%(query_string)s`, `%(method)s`, `%(scheme)s`, `%(protocol)s`, `%(header{Name})s`). |
| `--log-config` | `GRANIAN_LOG_CONFIG` | `FILE` | `None` | Explicit JSON logging configuration path (overrides automatic bridge). |

### Worker Lifecycle and Resilience

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--respawn-failed-workers` / `--no-respawn-failed-workers` | `GRANIAN_RESPAWN_FAILED_WORKERS` | `BOOLEAN` | `False` | Automatically respawn workers on unexpected exits. |
| `--respawn-interval` | `GRANIAN_RESPAWN_INTERVAL` | `FLOAT` | `3.5` | Sleep interval in seconds between worker respawns. |
| `--workers-lifetime` | `GRANIAN_WORKERS_LIFETIME` | `DURATION >= 60s` | `None` | Maximum runtime in seconds or duration string (e.g. `1h`) before graceful respawn. |
| `--workers-kill-timeout` | `GRANIAN_WORKERS_KILL_TIMEOUT` | `DURATION (1-1800s)` | `5` (plus 5 seconds in the Litestar supervisor) | Seconds to wait for graceful worker shutdown before forced termination. |
| `--workers-max-rss` | `GRANIAN_WORKERS_MAX_RSS` | `INTEGER >= 1` (MiB) | `None` | Maximum resident memory in MiB before recycling worker (not on free-threaded Python). |
| `--rss-sample-interval` | `GRANIAN_RSS_SAMPLE_INTERVAL` | `DURATION (1-300s)` | `30` | Memory sampling interval for resource monitor. |
| `--rss-samples` | `GRANIAN_RSS_SAMPLES` | `INTEGER >= 1` | `1` | Consecutive samples exceeding RSS limit required before respawn. |

### Development and Auto-Reload

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `-r`, `--reload` / `--no-reload` | `LITESTAR_RELOAD` / `GRANIAN_RELOAD` | `BOOLEAN` | `False` | Auto-reload on file changes (not on free-threaded Python). |
| `-R`, `--reload-dir`, `--reload-paths` | `LITESTAR_RELOAD_DIRS` / `GRANIAN_RELOAD_PATHS` | `PATH` (repeatable) | Working dir | Specific filesystem paths to watch for changes (implicitly enables reload). |
| `-I`, `--reload-include` | `LITESTAR_RELOAD_INCLUDES` / `GRANIAN_RELOAD_INCLUDE` | `TEXT` (repeatable) | `None` | Glob patterns to include in reload monitoring (e.g. `"*.py"`; implicitly enables reload). |
| `-E`, `--reload-exclude` | `LITESTAR_RELOAD_EXCLUDES` / `GRANIAN_RELOAD_EXCLUDE` | `TEXT` (repeatable) | `None` | Glob patterns or directories to exclude from reload monitoring (implicitly enables reload). |
| `--reload-ignore-dirs` | `GRANIAN_RELOAD_IGNORE_DIRS` | `TEXT` (repeatable) | `None` | Directory names to ignore during file watching. |
| `--reload-ignore-patterns` | `GRANIAN_RELOAD_IGNORE_PATTERNS` | `TEXT` (repeatable) | `None` | Regex patterns for file/directory names to ignore. |
| `--reload-ignore-paths` | `GRANIAN_RELOAD_IGNORE_PATHS` | `PATH` (repeatable) | `None` | Absolute paths to ignore. |
| `--reload-tick` | `GRANIAN_RELOAD_TICK` | `INTEGER (50-5000ms)` | `50` | Watcher poll interval in milliseconds. |
| `--reload-ignore-worker-failure` / `--no-reload-ignore-worker-failure` | `GRANIAN_RELOAD_IGNORE_WORKER_FAILURE` | `BOOLEAN` | `False` | Keep watcher alive if worker process fails during startup. |
| `-d`, `--debug` | `LITESTAR_DEBUG` | `BOOLEAN` | `False` | Enables Litestar debug exception pages. |
| `-P`, `--pdb`, `--use-pdb` | `LITESTAR_PDB` | `BOOLEAN` | `False` | Drop into PDB post-mortem debugger on unhandled exceptions. |

### Metrics and Static Serving

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--metrics` / `--no-metrics` | `GRANIAN_METRICS_ENABLED` | `BOOLEAN` | `False` | Enable Granian's Prometheus metrics endpoint. |
| `--metrics-scrape-interval` | `GRANIAN_METRICS_SCRAPE_INTERVAL` | `DURATION (1-60s)` | `15` | Metric scrape and collection interval in seconds. |
| `--metrics-address` | `GRANIAN_METRICS_ADDRESS` | `TEXT` | `127.0.0.1` | Exporter host address to bind Prometheus server to. |
| `--metrics-port` | `GRANIAN_METRICS_PORT` | `INTEGER (1-65535)` | `9090` | Exporter port to bind Prometheus server to. |
| `--static-path-route` | `GRANIAN_STATIC_PATH_ROUTE` | `TEXT` (repeatable) | `None` | Route prefix for native static serving (e.g. `/static`). |
| `--static-path-mount` | `GRANIAN_STATIC_PATH_MOUNT` | `DIRECTORY` (repeatable) | `None` | Filesystem directory to mount natively. |
| `--static-path-dir-to-file` | `GRANIAN_STATIC_PATH_DIR_TO_FILE` | `TEXT` | `None` | Index file served when a directory is requested (e.g. `index.html`). |
| `--static-path-expires` | `GRANIAN_STATIC_PATH_EXPIRES` | `DURATION` | `86400` | Cache-Control `max-age` in seconds or duration string (`0` to disable). |

### Operations and Process Management

| Option | Environment Variable | Type / Choices | Default | Description |
| --- | --- | --- | --- | --- |
| `--process-name` | `GRANIAN_PROCESS_NAME` | `TEXT` | `None` | Custom process name (requires `granian[pname]`). |
| `--pid-file` | `GRANIAN_PID_FILE` | `FILE` | `None` | Path to write supervisor PID file. |
| `--working-dir` | `GRANIAN_WORKING_DIR` | `DIRECTORY` | Current dir | Set server process working directory. |
| `--env-files` | `GRANIAN_ENV_FILES` | `FILE` (repeatable) | `None` | Dotenv environment files to load (requires `granian[dotenv]`). |

### Deprecated and Retired Flags

- **Deprecated in 0.16.0 (Ignored with Warning):**
  - `--in-subprocess` / `--no-subprocess` (`LITESTAR_GRANIAN_IN_SUBPROCESS` / `GRANIAN_IN_SUBPROCESS`): Supervised execution is always used.
  - `--use-litestar-logger` / `--no-litestar-logger` (`LITESTAR_GRANIAN_USE_LITESTAR_LOGGER` / `GRANIAN_USE_LITESTAR_LOGGER`): Formatter matching is automatic.
- **Retired Upstream (Do Not Use):**
  - Retired Granian flags: `--threads`, `--threading-mode`, `--log-access`, `--log-access-format`, `--log-access-fmt`.
  - Use `--runtime-threads`, `--runtime-mode`, `--granian-access-log`, and `--granian-access-log-fmt` instead.
  - Non-existent Uvicorn proxy flags (`--proxy-headers`, `--forwarded-allow-ips`): use `granian.utils.proxies.wrap_asgi_with_proxy_headers` in `Litestar(middleware=[...])`.
