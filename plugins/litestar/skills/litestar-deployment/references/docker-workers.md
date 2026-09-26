# Docker Background Worker Containers (`litestar-saq` & `litestar-queues`)

Dedicated container patterns for background task processing and event-stream consumers. Both `litestar-saq` and `litestar-queues` reuse the same multi-stage build as the web container and override only the final runtime command (`CMD`).

## Key differences from web container

| Property | Web container | `litestar-saq` worker | `litestar-queues` worker / consumer |
| --- | --- | --- | --- |
| CMD | `litestar run --host 0.0.0.0` | `litestar workers run` (or `app workers run`) | `litestar queues run` or `litestar queues run-consumer` |
| EXPOSE | 8000 | None | None |
| Health probes | HTTP `/health` | Process restart only | Process restart only |
| Scaling trigger | HTTP request rate / CPU | Redis queue depth / CPU | DB queue depth / broker lag / CPU |
| Lifespan env | `SAQ_USE_SERVER_LIFESPAN=false` | `SAQ_USE_SERVER_LIFESPAN=false` | Managed by `QueuePlugin` CLI |

## Worker Dockerfile

The worker Dockerfile is identical to the distroless Dockerfile through the `runtime-prep` stage. Only the final `CMD` differs based on your background task library:

```dockerfile
# =============================================================================
# Stage 4: Distroless Runtime (Worker)
# =============================================================================
FROM ${RUN_IMAGE} AS runtime

ARG LITESTAR_APP="app.server.asgi:create_app"

ENV PATH="/workspace/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    LITESTAR_APP="${LITESTAR_APP}" \
    SAQ_USE_SERVER_LIFESPAN=false

COPY --from=runtime-prep /usr/local/lib/ /usr/local/lib/
COPY --from=runtime-prep /usr/local/bin/python /usr/local/bin/python
COPY --from=runtime-prep /etc/ld.so.cache /etc/ld.so.cache
COPY --from=runtime-prep /usr/bin/tini /usr/local/bin/tini
COPY --from=runtime-prep /runtime-libs/lib/ /lib/
COPY --from=runtime-prep /runtime-libs/usr/lib/ /usr/lib/
COPY --from=runtime-prep /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

WORKDIR /workspace/app
COPY --from=runtime-prep --chown=65532:65532 /workspace/app/.venv /workspace/app/.venv

STOPSIGNAL SIGINT

# No EXPOSE - worker does not serve HTTP traffic

ENTRYPOINT ["/usr/local/bin/tini", "--"]

# Option A (litestar-saq):
CMD ["litestar", "workers", "run"]

# Option B (litestar-queues task worker):
# CMD ["litestar", "queues", "run", "--max-concurrency", "10", "--drain-timeout", "30.0"]

# Option C (litestar-queues event-stream consumer):
# CMD ["litestar", "queues", "run-consumer", "--backend", "pubsub", "--drain-timeout", "30.0"]
```

## Match-Your-Stack: Worker Commands

### Option A: `litestar-saq` (Redis / Valkey)

Set `SAQ_USE_SERVER_LIFESPAN=false` in both web and worker containers when running dedicated worker processes. This tells SAQ to manage its own lifecycle (Redis connections, signal handling) rather than piggybacking on the Litestar HTTP server lifespan. See [`../../litestar-saq/SKILL.md`](../../litestar-saq/SKILL.md).

### Option B: `litestar-queues` (SQLSpec / SQLAlchemy / Event Streams)

`litestar-queues` exposes four CLI entry points under `litestar queues`:

| Command | Deployment Role | Key Flags |
| --- | --- | --- |
| `litestar queues run` | Long-running queue worker polling SQLSpec / SQLAlchemy / Memory backends | `-q/--queues`, `--max-concurrency`, `--poll-interval`, `--lease-duration`, `--drain-timeout` |
| `litestar queues run-consumer` | Long-running event-stream consumer (`kafka`, `pubsub`, `rabbitmq`, `sqs`) | `-t/--topics`, `-g/--group`, `--backend`, `--max-concurrency`, `--drain-timeout` |
| `litestar queues run-task` | Serverless one-shot task execution (Cloud Run Jobs) | `--task-name`, `--task-id`, `--payload`, `--payload-base64`, `--attempt` |
| `litestar queues run-maintenance` | Scheduled maintenance (`CronJob` / K8s `CronJob`) for lease recovery and pruning | `--no-recover-leases`, `--no-prune-history`, `--no-prune-dlq` |

See [`../../litestar-queues/SKILL.md`](../../litestar-queues/SKILL.md) for backend and configuration details.

## Railway warning

Workers poll Redis, a database, or a message broker for jobs — they do not receive HTTP requests. On Railway:

- **Do not enable serverless/sleep** for worker services. Railway can only wake services via HTTP requests. A sleeping worker cannot process queued jobs.
- Deploy the worker as a separate Railway service with `railway.worker.json`.

## Docker Compose worker service

```yaml
worker:
  build:
    context: .
    dockerfile: tools/deploy/docker/Dockerfile.worker
  # Option A (litestar-saq): command: litestar workers run
  # Option B (litestar-queues): command: litestar queues run --max-concurrency 10
  command: litestar workers run
  restart: always
  depends_on:
    db:
      condition: service_healthy
    cache:
      condition: service_healthy
  env_file:
    - .env.docker
```

The worker reuses the same image but overrides `command`. No port mapping is needed.

## Kubernetes worker deployment & CronJob maintenance

Workers get their own Deployment with separate HPA scaling:

```yaml
spec:
  containers:
    - name: worker
      image: {{ worker_image_repo }}:{{ image_tag }}
      # Uses Dockerfile.worker CMD (litestar workers run OR litestar queues run)
      env:
        - name: SAQ_USE_SERVER_LIFESPAN
          value: "false"
      # No ports, no HTTP probes
  terminationGracePeriodSeconds: 120  # Allow in-flight tasks to complete
```

Set `terminationGracePeriodSeconds` higher for workers (`120`s) than for web containers (`60`s) to allow in-flight tasks to complete before `SIGKILL` (exceeding `--drain-timeout`). When using `litestar-queues`, pair the worker Deployment with a Kubernetes `CronJob` running `litestar queues run-maintenance` to recover expired leases and prune completed task history.
