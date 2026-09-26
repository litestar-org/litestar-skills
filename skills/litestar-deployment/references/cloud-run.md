# Google Cloud Run

Serverless container deployment for Litestar applications. Cloud Run runs your container on demand, scaling from zero to N instances based on HTTP traffic.

## Deploy with gcloud CLI

```bash
# Build and push to Artifact Registry
docker build -f Dockerfile.distroless -t us-docker.pkg.dev/my-project/repo/app:v1.0.0 .
docker push us-docker.pkg.dev/my-project/repo/app:v1.0.0

# Deploy
gcloud run deploy my-app \
    --image us-docker.pkg.dev/my-project/repo/app:v1.0.0 \
    --platform managed \
    --region us-central1 \
    --port 8000 \
    --min-instances 1 \
    --max-instances 10 \
    --concurrency 80 \
    --cpu 1 \
    --memory 512Mi \
    --timeout 300 \
    --set-env-vars "LITESTAR_APP=app.server.asgi:create_app" \
    --set-secrets "DATABASE_URL=database-url:latest,SECRET_KEY=secret-key:latest" \
    --service-account app-sa@my-project.iam.gserviceaccount.com \
    --allow-unauthenticated
```

## service.yaml

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: my-app
  annotations:
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/cpu-throttling: "false"
        run.googleapis.com/startup-cpu-boost: "true"
    spec:
      containerConcurrency: 80
      timeoutSeconds: 300
      serviceAccountName: app-sa@my-project.iam.gserviceaccount.com
      containers:
        - image: us-docker.pkg.dev/my-project/repo/app:v1.0.0
          ports:
            - containerPort: 8000
          resources:
            limits:
              cpu: "1"
              memory: 512Mi
          env:
            - name: LITESTAR_APP
              value: app.server.asgi:create_app
          startupProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 2
            periodSeconds: 3
            failureThreshold: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 15
```

## Cloud SQL connection

Cloud Run connects to Cloud SQL (managed PostgreSQL) via the built-in Cloud SQL connector — no sidecar proxy needed:

```bash
gcloud run deploy my-app \
    --add-cloudsql-instances my-project:us-central1:my-instance \
    --set-env-vars "DATABASE_URL=postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/my-project:us-central1:my-instance"
```

The Cloud SQL connector mounts a Unix socket at `/cloudsql/<instance-connection-name>`. Use the `?host=` query parameter to point asyncpg at the socket.

For Python-native connection (without Unix socket), use the `cloud-sql-python-connector` library:

```python
from google.cloud.sql.connector import Connector

connector = Connector()


async def get_connection() -> object:
    """Create an asyncpg connection to Cloud SQL via the Python Connector."""
    return await connector.connect_async(
        "my-project:us-central1:my-instance",
        "asyncpg",
        user="app",
        password="secret",
        db="appdb",
    )
```

## Key Cloud Run settings

| Setting | Recommended | Rationale |
| --- | --- | --- |
| `min-instances` | 1+ | Avoids cold start on first request. Set to 0 for cost savings in dev. |
| `max-instances` | 10-100 | Prevents runaway scaling. |
| `concurrency` | 80 | Granian handles concurrent requests well. Match to worker count. |
| `cpu-throttling: false` | Yes | Keeps CPU allocated even when idle. Needed for background processing. |
| `startup-cpu-boost` | Yes | Extra CPU during startup for faster cold starts. |
| `timeout` | 300s | Max request duration. Increase for long-running API calls. |
| `LITESTAR_TRUSTED_PROXIES` | `"*"` | Allows `litestar-vite` `ProxyHeadersMiddleware` to trust `X-Forwarded-Proto` / `X-Forwarded-Host` from the Cloud Run load balancer. |

## Background Tasks on Cloud Run (Match-Your-Stack)

Cloud Run Services scale based on incoming HTTP traffic and scale to zero when idle, so continuous polling daemons (`litestar workers run` or `litestar queues run`) should not run inside a scale-to-zero HTTP Service.

### Option A: `litestar-queues` on Cloud Run Jobs (Recommended for Serverless)

`litestar-queues` natively supports **one-shot serverless execution** via `CloudRunExecutionConfig` and `litestar queues run-task`:

1. Configure `QueueConfig(execution_mode="cloud_run", cloud_run=CloudRunExecutionConfig(project_id=..., region=..., job_name="my-app-tasks"))` on the web service.
2. Deploy a **Cloud Run Job** using the same container image with `litestar queues run-task` as its entrypoint:

```bash
gcloud run jobs create my-app-tasks \
    --image us-docker.pkg.dev/my-project/repo/app:v1.0.0 \
    --region us-central1 \
    --command "litestar" \
    --args "queues,run-task" \
    --set-env-vars "LITESTAR_APP=app.server.asgi:create_app" \
    --set-secrets "DATABASE_URL=database-url:latest,SECRET_KEY=secret-key:latest" \
    --service-account app-sa@my-project.iam.gserviceaccount.com
```

When the web application enqueues a task, `litestar-queues` dispatches a Cloud Run Job execution passing `LITESTAR_QUEUES_TASK_NAME`, `LITESTAR_QUEUES_TASK_ID`, and `LITESTAR_QUEUES_PAYLOAD_B64`; the container processes that single task and exits immediately. For scheduled lease recovery and history pruning, trigger a second Cloud Run Job (`--args "queues,run-maintenance"`) via Cloud Scheduler. See [`../../litestar-queues/SKILL.md`](../../litestar-queues/SKILL.md).

### Option B: Long-Running Workers (`litestar-saq` or `litestar-queues` Daemon)

If you use `litestar-saq` (`litestar workers run`) or continuous `litestar queues run` / `run-consumer` workers, deploy them on **GKE**, **Compute Engine**, or a dedicated Cloud Run Worker Pool / Service with `min-instances: 1` and `cpu-throttling: false`.

## IAP (Identity-Aware Proxy)

Cloud Run services behind IAP receive the `X-Goog-IAP-JWT-Assertion` header. See the [litestar app deployment reference](litestar-app.md) for IAP middleware integration.

```bash
# Enable IAP on Cloud Run
gcloud run services update my-app \
    --set-env-vars "AUTH_IAP_ENABLED=true,IAP_AUDIENCE=/projects/PROJECT_NUMBER/apps/PROJECT_ID"
```
