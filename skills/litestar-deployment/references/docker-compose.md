# Docker Compose

Full Docker Compose stack for local development and staging. Runs the Litestar app, SAQ worker, database migrator, PostgreSQL, and Valkey (Redis-compatible cache).

## Application Stack (docker-compose.yml)

```yaml
services:
  cache:
    image: valkey/valkey:latest
    ports:
      - "16379:6379"
    hostname: cache
    command: redis-server --appendonly yes
    volumes:
      - cache-data:/data
    environment:
      ALLOW_EMPTY_PASSWORD: "yes"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      timeout: 3s
      retries: 30

  db:
    image: postgres:latest
    ports:
      - "15432:5432"
    hostname: db
    environment:
      POSTGRES_PASSWORD: "app"
      POSTGRES_USER: "app"
      POSTGRES_DB: "app"
    volumes:
      - db-data:/var/lib/postgresql
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "app"]
      interval: 2s
      timeout: 3s
      retries: 40

  app:
    build:
      context: .
      dockerfile: tools/deploy/docker/Dockerfile.distroless
    restart: always
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      VITE_DEV_MODE: "false"
      SAQ_USE_SERVER_LIFESPAN: "false"
    env_file:
      - .env.docker

  worker:
    build:
      context: .
      dockerfile: tools/deploy/docker/Dockerfile.distroless
    command: litestar workers run
    restart: always
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    env_file:
      - .env.docker

  migrator:
    build:
      context: .
      dockerfile: tools/deploy/docker/Dockerfile.distroless
    restart: "no"
    command: litestar database upgrade --no-prompt
    env_file:
      - .env.docker
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy

volumes:
  db-data: {}
  cache-data: {}
```

## Infrastructure-Only Stack (docker-compose.infra.yml)

For running only infrastructure services (database, cache, mail, object storage) while developing the app locally:

```yaml
services:
  cache:
    image: valkey/valkey:latest
    ports:
      - "16379:6379"
    hostname: cache
    command: redis-server --appendonly yes
    volumes:
      - cache-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      timeout: 3s
      retries: 30

  db:
    image: postgres:latest
    ports:
      - "15432:5432"
    hostname: db
    environment:
      POSTGRES_PASSWORD: "app"
      POSTGRES_USER: "app"
      POSTGRES_DB: "app"
    volumes:
      - db-data:/var/lib/postgresql
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "app"]
      interval: 2s
      timeout: 3s
      retries: 40

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "18025:8025"  # Web UI
      - "11025:1025"  # SMTP
    healthcheck:
      test: ["CMD", "sh", "-c", "wget --no-verbose --tries=1 --spider http://localhost:8025/livez || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  storage:
    image: rustfs/rustfs:latest
    ports:
      - "19000:9000"   # S3 API
      - "19001:9001"   # Web Console
    environment:
      RUSTFS_ACCESS_KEY: "app"
      RUSTFS_SECRET_KEY: "app"
      RUSTFS_VOLUMES: "/data"
      RUSTFS_CONSOLE_ENABLE: "true"
    volumes:
      - storage-data:/data

volumes:
  db-data: {}
  cache-data: {}
  storage-data: {}
```

Usage:

```bash
# Infrastructure only (run app locally with `litestar run`)
docker compose -f docker-compose.infra.yml up -d

# Full stack
docker compose up -d

# Run migrations
docker compose run --rm migrator
```

## Design decisions

| Decision | Rationale |
| --- | --- |
| Valkey over Redis | Drop-in Redis replacement, fully open-source (BSD license). |
| Port offsets (15432, 16379) | Avoid conflicts with locally installed PostgreSQL/Redis. |
| `condition: service_healthy` | App and worker wait for healthy database and cache before starting. |
| Separate `migrator` service | Runs once (`restart: "no"`), applies schema migrations, then exits. |
| `SAQ_USE_SERVER_LIFESPAN: "false"` | Worker and app manage SAQ lifecycle independently. |
| `.env.docker` file | All environment variables in one file. Never committed to git. |

## Example .env.docker

```bash
LITESTAR_APP=app.server.asgi:create_app
SECRET_KEY=change-me-in-production
DATABASE_URL=postgresql+asyncpg://app:app@db:5432/app
SAQ_REDIS_URL=redis://cache:6379/0
LITESTAR_HOST=0.0.0.0
LITESTAR_PORT=8000
LOG_LEVEL=DEBUG
```
