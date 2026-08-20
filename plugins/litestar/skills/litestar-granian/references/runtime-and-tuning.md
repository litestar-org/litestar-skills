# Granian Runtime Architecture and Tuning Guide

Deep-dive into concurrency models, thread architectures, HTTP protocol tuning, memory recycling, and runtime optimization with `litestar-granian` 0.16.0 and `granian` 2.8.1.

## Concurrency and Process Model

Granian is built in Rust using Tokio, PyO3, and Hyper. It separates connection handling in Rust from Python application execution.

```text
[ Incoming Network Connections ]
               │
               ▼
┌──────────────────────────────────────────────┐
│  Granian Worker (Process)                   │
│  ┌────────────────────────────────────────┐  │
│  │ Rust Core (Tokio / Hyper / TLS)        │  │
│  │ - Accept sockets, TLS handshake        │  │
│  │ - HTTP/1 & HTTP/2 protocol parsing     │  │
│  │ - Connection backpressure regulation   │  │
│  └──────────────────┬─────────────────────┘  │
│                     │ Async dispatch         │
│  ┌──────────────────▼─────────────────────┐  │
│  │ Python Worker Runtime                  │  │
│  │ - Event Loop: uvloop / rloop / asyncio │  │
│  │ - Runtime Threads (1..N)               │  │
│  │ - Blocking Thread Pool (sync handlers) │  │
│  │ - Litestar ASGI Application            │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### Worker Allocation (`--workers`)

- **Default:** `1` worker.
- **Rule of thumb:** `(2 * CPU_CORES) + 1` for I/O-bound workloads, or `1 * CPU_CORES` in memory-constrained container environments (e.g. Cloud Run, Kubernetes pods with 1-2 vCPUs).
- **Scale out over scale up:** Multiple worker processes provide GIL isolation in standard CPython builds.

### Threading Architecture

Granian provides three distinct thread tuning knobs:

1. **`--runtime-threads` (default: 1 per worker):**
   Number of Rust network-I/O threads per worker. This does not set the
   number of Python application threads.

2. **`--runtime-blocking-threads` (default: automatically selected):**
   Rust runtime threads used for blocking operations such as filesystem I/O.

3. **`--blocking-threads` & `--blocking-threads-idle-timeout`:**
   Threads per worker that interact with the Python interpreter. This setting
   is primarily relevant to synchronous protocols; on asynchronous protocols
   the value is fixed to one. Unused threads are terminated after the idle
   timeout (default: 30s).

### Runtime Modes (`--runtime-mode`)

- **`auto` (default in 0.16.0):** Granian selects the optimal runtime configuration based on the installed Python build and operating system.
- **`mt` (Multi-Threaded):** Configures multi-threaded async execution across configured runtime threads.
- **`st` (Single-Threaded):** Pins single-threaded event loop execution. Use when third-party libraries require thread affinity.

### Event Loops and Task Implementations

- **`--loop`:**
  - `auto` (default): Uses Granian's standard loop selection. Optional loop
    implementations require their matching package extra and explicit selection.
  - `uvloop`: High-performance libuv-backed event loop.
  - `rloop`: Optional Rust-backed event loop installed with the `rloop` extra.
  - `asyncio`: Standard library asyncio event loop.
  - `winloop`: Windows-optimized event loop.
- **`--task-impl`:**
  - `asyncio` (default): Standard Python task scheduling.
  - `rust`: Delegates coroutine scheduling and wakeups directly to Granian's Rust core for reduced dispatch overhead.

---

## Capacity and Backpressure

### Backlog (`--backlog`)

Global socket backlog queue specifying how many unaccepted TCP connections the OS kernel holds before dropping incoming SYN packets (default: `1024`, minimum `128`).

### Backpressure (`--backpressure`)

Maximum number of concurrent in-flight requests a single worker process will accept before pausing TCP reads on the socket (default: `backlog / workers`).

When the accepted-connection count reaches the backpressure threshold:

1. The Rust core stops pulling data from TCP sockets for that worker.
2. The operating system holds client connections in the TCP queue.
3. Once in-flight requests complete, the worker resumes socket reading.

This prevents memory exhaustion and event loop starvation under sudden traffic spikes.

---

## HTTP Protocol Tuning

### HTTP Modes

- `--http auto` (default): Negotiates HTTP/1.1 and HTTP/2 via ALPN during TLS handshake; accepts HTTP/1.1 on cleartext TCP.
- `--http 1`: Forces HTTP/1.1 only.
- `--http 2`: Forces HTTP/2 only. **Note:** WebSockets are automatically disabled in HTTP/2-only mode.
- *Note on HTTP/3:* Granian 2.8.1 does not support HTTP/3 / QUIC. Deploy an edge reverse proxy (such as Cloudflare, NGINX, or Envoy) in front of Granian for HTTP/3 termination.

### HTTP/1 Performance Knobs

- `--http1-buffer-size` (default: `417792`, min `8192`): Maximum read buffer size per connection. Increase for requests with large headers or cookie jars.
- `--http1-header-read-timeout` (default: `30000` ms): Read timeout for request headers. Protects against Slowloris attacks.
- `--http1-keep-alive` / `--no-http1-keep-alive` (default: `True`): Persistent connections.
- `--http1-pipeline-flush` (default: `False`): Batches TCP socket flushes when handling pipelined requests (experimental).

### HTTP/2 Performance Knobs

- `--http2-max-concurrent-streams` (default: `200`, min `10`): Sets `SETTINGS_MAX_CONCURRENT_STREAMS`. Limits simultaneous multiplexed streams per connection.
- `--http2-initial-connection-window-size` (default: `1048576`, min `1024`): Connection-level flow control window.
- `--http2-initial-stream-window-size` (default: `1048576`, min `1024`): Stream-level flow control window (`SETTINGS_INITIAL_WINDOW_SIZE`).
- `--http2-adaptive-window` (default: `False`): Dynamically adjusts window sizes based on bandwidth-delay product.
- `--http2-keep-alive-interval` (default: None): Milliseconds between sending HTTP/2 PING frames to detect dead connections.
- `--http2-keep-alive-timeout` (default: `20` s): Time to wait for PING ACK before terminating the connection.
- `--http2-max-frame-size` (default: `16384`, min `1024`): Maximum size of HTTP/2 data frames.
- `--http2-max-headers-size` (default: `16777216`): Maximum allowable size of received headers across all continuation frames.
- `--http2-max-send-buffer-size` (default: `409600`, min `1024`): Maximum write buffer size per HTTP/2 stream.

---

## Worker Lifecycle and Memory Protection

Production services running long-term can protect against memory leaks or runaway resource consumption using Granian's built-in supervisor flags:

### Memory Limit Recycling (`--workers-max-rss`)

Sets the maximum resident memory (RSS in MiB) a worker may consume before Granian gracefully recycles it:

```bash
litestar --app app:app run \
    --workers 4 \
    --workers-max-rss 512 \
    --rss-sample-interval 15 \
    --rss-samples 2
```

- `--rss-sample-interval` (default: `30`s): Polling interval for memory usage.
- `--rss-samples` (default: `1`): Number of consecutive checks above `--workers-max-rss` before initiating graceful worker respawn.

### Worker Lifetime Recycling (`--workers-lifetime`)

Forces workers to respawn after a set duration, even if healthy (minimum `60` seconds):

```bash
litestar --app app:app run --workers-lifetime 4h
```

### Respawn and Termination Controls

- `--respawn-failed-workers`: Automatically starts a replacement worker if an existing worker exits unexpectedly.
- `--respawn-interval` (default: `3.5`s): Cooldown between respawning failed workers to prevent crash looping.
- `--workers-kill-timeout` (default: `5`s in the Litestar CLI): Grace period
  allowed for worker shutdown; the supervisor adds five seconds before forced
  termination.

---

## Python Runtime & Platform Constraints

### Free-Threaded Python (PEP 703 / Python 3.13+ GIL-Disabled)

When running on Python builds with the GIL disabled (`Py_GIL_DISABLED=1`):

- `--reload` is not supported and will raise a `UsageError`.
- `--workers-max-rss` is not supported and will raise a `UsageError`.
- On free-threaded Python, Granian workers are threads rather than processes;
  ASGI still runs one event loop per worker. Free-threaded support is
  experimental, so tune workers and threads against the actual workload.

### Windows Platform Differences

- `--fd` / `--file-descriptor` socket activation is not supported on Windows.
- Process termination uses `CTRL_BREAK_EVENT` with fallback to `taskkill /PID ... /T /F`.
