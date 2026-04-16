---
name: litestar-granian
description: "Auto-activate for litestar_granian imports, GranianPlugin, granian CLI commands, ASGI server config in a Litestar app. The litestar-granian plugin: zero-config replacement for `litestar run` that uses Granian (Rust-based ASGI server) instead of uvicorn. Produces GranianPlugin configurations, GranianConfig tuning (workers/threads/HTTP/SSL/backpressure), and Litestar app lifespan integration. Use when: serving a Litestar app in dev or production, replacing uvicorn, configuring workers/threads, enabling HTTP/2 or SSL, or tuning backpressure. Not for FastAPI, Django, or non-Litestar apps — use plain `granian` CLI for those. Not for uvicorn — Granian is preferred for all Litestar deployments."
---

# litestar-granian

`litestar-granian` is the first-party plugin that integrates the [Granian](https://github.com/emmett-framework/granian) Rust-based ASGI server with Litestar. Adding `GranianPlugin()` to a Litestar app makes `litestar run` launch Granian instead of uvicorn — same CLI, much higher throughput, native HTTP/2, and lower memory.

For Litestar apps, **always prefer `litestar-granian` over plain `granian` CLI**: the plugin wires Granian into Litestar's lifespan, signal handling, CLI flags, and dev-mode reload logic.

## Code Style Rules

- Use PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar apps that wire `GranianPlugin` MAY use `from __future__ import annotations` — canonical Litestar apps do.
- Async all I/O — sync handlers block Granian's async runtime and starve workers.

## Quick Reference

### Zero-config plugin install

```python
from litestar import Litestar
from litestar_granian import GranianPlugin

app = Litestar(
    route_handlers=[...],
    plugins=[GranianPlugin()],
)
```

```bash
# Same CLI as before; now backed by Granian
litestar --app app:app run --host 0.0.0.0 --port 8000

# Dev with reload
litestar --app app:app run --reload
```

### Tuned plugin install

```python
from litestar_granian import GranianPlugin, GranianConfig

app = Litestar(
    route_handlers=[...],
    plugins=[
        GranianPlugin(
            config=GranianConfig(
                workers=8,
                threads=2,
                threading_mode="runtime",   # async-friendly
                http="auto",                # HTTP/1.1 + HTTP/2
                backpressure=2000,
                log_access=True,
                log_access_format="json",
            ),
        ),
    ],
)
```

### Production with SSL

```python
GranianConfig(
    workers=8,
    threads=2,
    threading_mode="runtime",
    http="auto",
    ssl_certificate="/etc/ssl/certs/app.crt",
    ssl_key="/etc/ssl/private/app.key",
    backpressure=2000,
)
```

### Granian vs Uvicorn for Litestar

| Feature | Granian (`litestar-granian`) | Uvicorn |
|---|---|---|
| Core | Rust (hyper + tokio) | Python |
| HTTP/2 | Native | Requires `h2` |
| Throughput | Higher | Moderate |
| Memory | Lower | Higher |
| Litestar plugin | First-party (`GranianPlugin`) | None — generic ASGI |
| `litestar run` integration | Yes — drop-in replacement | Default if no plugin |
| Production default | **Preferred** | Fallback only |

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-granian
```

### Step 2: Register the Plugin

Add `GranianPlugin()` to the `Litestar(plugins=[...])` list. No other code change is required for dev — `litestar run` now uses Granian.

### Step 3: Tune for Deployment

Pass a `GranianConfig` to the plugin for production. Match `workers` to CPU cores, set `threading_mode="runtime"` for async workloads, enable `http="auto"`, set `backpressure` to bound queue depth.

### Step 4: Add SSL or Reverse Proxy

Either terminate TLS at Granian (`ssl_certificate` / `ssl_key`) or behind a load balancer. Inside a container without an external proxy, prefer Granian-native SSL.

### Step 5: Verify

Run the app, confirm the startup banner mentions Granian, and load-test before going live. Tune `workers` / `backpressure` to match peak load without exhausting memory.

</workflow>

<guardrails>

## Guardrails

- **Use `litestar-granian` for Litestar apps**, not the bare `granian` CLI — the plugin integrates with Litestar lifespan, dev-reload, signal handling, and CLI flags.
- **Never mix `GranianPlugin` with manual `granian` invocations** — the plugin owns the server lifecycle. Pick one.
- **Match `workers` to CPU cores** for production. Under-provisioned wastes hardware; over-provisioned bloats memory.
- **Use `threading_mode="runtime"`** for async (Litestar) workloads. `workers` mode is for CPU-bound sync code.
- **Set `http="auto"`** unless you have a documented reason to restrict HTTP version. Pure HTTP/2 breaks HTTP/1.1 clients.
- **Set `backpressure`** in production — without a bound, traffic spikes lead to unbounded queuing and OOM.
- **Use `GranianPlugin` over `uvicorn`** for all Litestar deployments — higher throughput, native HTTP/2, lower memory.
- **Never `async def` blocked by sync I/O** — Granian's event loop must stay free; sync DB/HTTP calls inside `async def` starve workers.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering a Litestar + Granian deployment, verify:

- [ ] `GranianPlugin` is in `app.plugins`
- [ ] No competing manual `granian app:app` invocations in scripts/Dockerfile
- [ ] `GranianConfig.workers` matches CPU cores (or has a documented deviation)
- [ ] `threading_mode="runtime"` is set
- [ ] `http="auto"` is set
- [ ] `backpressure` is set for production
- [ ] SSL flags or a documented reverse proxy handle TLS for any public service
- [ ] No `uvicorn` in production deps (or a justification is documented)

</validation>

<example>

## Example

**Task:** Production Litestar app with `GranianPlugin`, tuned for an 8-core host with SSL and structured access logging.

```python
# app.py
from litestar import Litestar, get
from litestar_granian import GranianPlugin, GranianConfig


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[health],
    plugins=[
        GranianPlugin(
            config=GranianConfig(
                workers=8,
                threads=2,
                threading_mode="runtime",
                http="auto",
                backpressure=2000,
                ssl_certificate="/etc/ssl/certs/app.crt",
                ssl_key="/etc/ssl/private/app.key",
                log_access=True,
                log_access_format="json",
            ),
        ),
    ],
)
```

```bash
# Production launch — same CLI, now Granian-backed
litestar --app app:app run --host 0.0.0.0 --port 8443
```

For Dockerfile / process manager invocations, prefer the same Litestar CLI command rather than calling `granian` directly.

</example>

---

## Reference: Granian CLI (when not using the plugin)

If you need to run Granian directly (e.g., for non-Litestar code paths), the standard CLI flags map 1:1 to `GranianConfig` fields:

```bash
granian app:main \
  --interface asgi \
  --host 0.0.0.0 \
  --port 8443 \
  --workers 8 \
  --threads 2 \
  --threading-mode runtime \
  --http auto \
  --backpressure 2000 \
  --ssl-certfile /etc/ssl/certs/app.crt \
  --ssl-keyfile /etc/ssl/private/app.key \
  --log-level info \
  --access-log \
  --log-access-fmt json
```

For Litestar apps, prefer the plugin path described above.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app initialization, plugins, and lifespan.

## Official References

- <https://github.com/litestar-org/litestar-granian>
- <https://github.com/emmett-framework/granian>
- <https://pypi.org/project/granian/>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../../../.agents/code-styleguides/general.md)
- [Python](../../../.agents/code-styleguides/python.md)
- [Litestar](../../../.agents/code-styleguides/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
