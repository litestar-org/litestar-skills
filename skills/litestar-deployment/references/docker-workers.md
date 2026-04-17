# Docker SAQ Worker Container

Dedicated container for SAQ background task processing. Uses the same multi-stage build as the web container but runs the worker command instead of the HTTP server.

## Key differences from web container

| Property | Web container | Worker container |
|---|---|---|
| CMD | `litestar run --host 0.0.0.0` | `app workers run` |
| EXPOSE | 8000 | None |
| Health probes | HTTP `/health` | Process restart only |
| Scaling trigger | HTTP request rate / CPU | Queue depth / CPU |
| `SAQ_USE_SERVER_LIFESPAN` | `false` | `false` |

## Worker Dockerfile

The worker Dockerfile is identical to the distroless Dockerfile through the runtime-prep stage. Only the final stage differs:

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
CMD ["app", "workers", "run"]
```

## SAQ_USE_SERVER_LIFESPAN

Set `SAQ_USE_SERVER_LIFESPAN=false` in worker containers. This tells SAQ to manage its own lifecycle (Redis connections, signal handling) rather than piggybacking on the Litestar server lifespan. Workers run independently of the HTTP server.

## Railway warning

Workers poll Redis for jobs — they do not receive HTTP requests. On Railway:

- **Do not enable serverless/sleep** for worker services. Railway can only wake services via HTTP requests. A sleeping worker cannot process queued jobs.
- Deploy the worker as a separate Railway service with `railway.worker.json`.

## Docker Compose worker service

```yaml
worker:
  build:
    context: .
    dockerfile: tools/deploy/docker/Dockerfile.worker
  command: app workers run
  restart: always
  depends_on:
    db:
      condition: service_healthy
    cache:
      condition: service_healthy
  env_file:
    - .env.docker
```

The worker reuses the same image but overrides CMD. No port mapping needed.

## Kubernetes worker deployment

Workers get their own Deployment with separate HPA scaling (based on CPU, not HTTP metrics):

```yaml
spec:
  containers:
    - name: worker
      image: {{ worker_image_repo }}:{{ image_tag }}
      # No command override — uses Dockerfile CMD
      env:
        - name: SAQ_USE_SERVER_LIFESPAN
          value: "false"
      # No ports, no HTTP probes
  terminationGracePeriodSeconds: 120  # Allow in-flight tasks to complete
```

Set `terminationGracePeriodSeconds` higher for workers (120s) than for web containers (60s) to allow in-flight tasks to complete before SIGKILL.
