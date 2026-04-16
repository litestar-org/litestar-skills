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

async def get_connection():
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
|---|---|---|
| `min-instances` | 1+ | Avoids cold start on first request. Set to 0 for cost savings in dev. |
| `max-instances` | 10-100 | Prevents runaway scaling. |
| `concurrency` | 80 | Granian handles concurrent requests well. Match to worker count. |
| `cpu-throttling: false` | Yes | Keeps CPU allocated even when idle. Needed for background processing. |
| `startup-cpu-boost` | Yes | Extra CPU during startup for faster cold starts. |
| `timeout` | 300s | Max request duration. Increase for long-running API calls. |

## Workers on Cloud Run

SAQ workers do not work well on Cloud Run because:

1. Cloud Run scales based on HTTP traffic — workers receive none.
2. Cloud Run can scale to zero — workers must always be running.

Deploy workers on **GKE**, **Compute Engine**, or **Cloud Run Jobs** (for batch-style processing) instead. If you must use Cloud Run, set `min-instances: 1` and use Cloud Run's always-on CPU allocation.

## IAP (Identity-Aware Proxy)

Cloud Run services behind IAP receive the `X-Goog-IAP-JWT-Assertion` header. See the [litestar deployment reference](../litestar/references/deployment.md) for IAP middleware integration.

```bash
# Enable IAP on Cloud Run
gcloud run services update my-app \
    --set-env-vars "AUTH_IAP_ENABLED=true,IAP_AUDIENCE=/projects/PROJECT_NUMBER/apps/PROJECT_ID"
```
