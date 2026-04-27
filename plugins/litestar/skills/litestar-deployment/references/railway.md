# Railway Deployment

Railway is a PaaS that deploys Docker containers from a git repo. Litestar apps deploy as two separate Railway services: one for the web API and one for the SAQ worker.

## Service configuration

### railway.app.json (web API)

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "tools/deploy/docker/Dockerfile.distroless"
  },
  "deploy": {
    "startCommand": "app run --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

### railway.worker.json (SAQ worker)

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "tools/deploy/docker/Dockerfile.worker"
  },
  "deploy": {
    "startCommand": "app workers run",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

Key differences:

- Worker has **no `healthcheckPath`** — it does not serve HTTP.
- Worker must **not** use Railway sleep/serverless — it polls Redis, not HTTP.
- Both services share the same Railway project environment variables.

## Environment setup

Create a `deploy.sh` script for Railway deployments:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "--- Railway Deploy ---"

# Run database migrations before starting the app
echo "Running database migrations..."
app database upgrade --no-prompt

echo "Migrations complete. Starting application..."
exec app run --host 0.0.0.0 --port "${PORT:-8000}"
```

For the worker service, use a simpler start:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec app workers run
```

## Environment variables on Railway

Set these in the Railway dashboard or via `railway variables set`:

```bash
# Required
LITESTAR_APP=app.server.asgi:create_app
SECRET_KEY=<generated-secret>
DATABASE_URL=postgresql+asyncpg://<railway-postgres-url>
SAQ_REDIS_URL=redis://<railway-redis-url>

# Railway provides
PORT=<auto-assigned>

# Build-time (prevent connection attempts)
DATABASE_POOL_DISABLED=true
SAQ_USE_SERVER_LIFESPAN=false
SAQ_WEB_ENABLED=false
```

## Provisioning databases on Railway

Railway provides managed PostgreSQL and Redis. Add them as services in your Railway project:

1. **PostgreSQL**: Add a Postgres service. Railway auto-injects `DATABASE_URL` as a reference variable.
2. **Redis**: Add a Redis service. Use `${{Redis.REDIS_URL}}` as a reference variable for `SAQ_REDIS_URL`.

Reference variables use Railway's template syntax: `${{ServiceName.VARIABLE_NAME}}`.

## Dockerfile considerations for Railway

- **No BuildKit cache mounts.** Railway's builder does not support `--mount=type=cache`. Use the distroless Dockerfile variant which avoids cache mounts.
- **PORT environment variable.** Railway assigns a random port via `$PORT`. Use `--port $PORT` in the start command.
- **Health checks.** Railway pings the `healthcheckPath` to determine readiness. Ensure `/health` returns 200 within `healthcheckTimeout` seconds.

## Deployment workflow

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and link project
railway login
railway link

# Deploy (from project root)
railway up

# Check logs
railway logs

# Set environment variable
railway variables set SECRET_KEY=my-secret
```

## Multi-service project layout

```text
railway-project/
  app-service/       -> railway.app.json (web API)
  worker-service/    -> railway.worker.json (SAQ worker)
  postgres-service/  -> managed by Railway
  redis-service/     -> managed by Railway
```

Each service in the Railway project points to the same git repo but uses a different config file and Dockerfile.
