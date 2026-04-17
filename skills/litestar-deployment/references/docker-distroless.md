# Docker Distroless Production Build

Preferred production Dockerfile using Google's distroless base image. No shell, no package manager, minimal attack surface. Supports multi-architecture builds (amd64 + arm64).

## Complete Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.13
ARG DEBIAN_VERSION=bookworm
ARG BUILDER_IMAGE=python:${PYTHON_VERSION}-slim-${DEBIAN_VERSION}
ARG RUN_IMAGE=gcr.io/distroless/cc-debian12:nonroot

# =============================================================================
# Stage 1: Python Base
# =============================================================================
FROM ${BUILDER_IMAGE} AS python-base

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        tini \
        unzip \
        ca-certificates \
    && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* /var/log/* /tmp/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun

# =============================================================================
# Stage 2: Builder
# =============================================================================
FROM python-base AS builder

ARG UV_INSTALL_ARGS="--no-dev"

ENV GRPC_PYTHON_BUILD_WITH_CYTHON=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PATH="/workspace/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    # Prevent connection attempts during build
    DATABASE_POOL_DISABLED=true \
    SAQ_USE_SERVER_LIFESPAN=false \
    SAQ_WEB_ENABLED=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* /var/log/* /tmp/*

WORKDIR /workspace/app

# Dependency files first (layer caching)
COPY pyproject.toml uv.lock README.md ./
COPY src/js/web/package.json src/js/web/bun.lock ./src/js/web/

WORKDIR /workspace/app/src/js/web
RUN bun install --frozen-lockfile
WORKDIR /workspace/app

# Python deps (no project source yet)
RUN uv venv \
    && uv sync ${UV_INSTALL_ARGS} --frozen --no-install-project --no-editable \
    && uv export ${UV_INSTALL_ARGS} --frozen --no-hashes --no-emit-project \
       --output-file=requirements.txt

# Copy source and build
COPY src/ ./src/

RUN uv run app assets build \
    && uv sync ${UV_INSTALL_ARGS} --frozen --no-editable \
    && uv build --wheel

# =============================================================================
# Stage 3: Runtime Preparation
# =============================================================================
FROM python-base AS runtime-prep

ARG TARGETARCH

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Non-root user matching distroless nonroot
RUN groupadd --system --gid 65532 nonroot \
    && useradd --no-create-home --system --uid 65532 --gid 65532 nonroot \
    && mkdir -p /workspace/app \
    && chown -R nonroot:nonroot /workspace

# Create venv with copied Python (not symlinked — distroless has no system Python)
RUN python -m venv --copies /workspace/app/.venv

COPY --from=builder --chown=65532:65532 /workspace/app/requirements.txt /tmp/requirements.txt
COPY --from=builder --chown=65532:65532 /workspace/app/dist/*.whl /tmp/

WORKDIR /workspace/app

RUN uv pip install \
        --quiet --no-cache-dir --no-deps \
        --requirement=/tmp/requirements.txt \
    && uv pip install \
        --quiet --no-cache-dir --no-deps \
        /tmp/*.whl \
    && rm -rf /tmp/*

# Architecture-aware library copying for distroless
RUN ARCH_DIR=$([ "$TARGETARCH" = "arm64" ] && echo "aarch64-linux-gnu" \
              || echo "x86_64-linux-gnu") \
    && mkdir -p /runtime-libs/lib /runtime-libs/usr/lib \
    && cp -a /lib/${ARCH_DIR} /runtime-libs/lib/ \
    && cp -a /usr/lib/${ARCH_DIR} /runtime-libs/usr/lib/ \
    && echo "${ARCH_DIR}" > /runtime-libs/arch

# =============================================================================
# Stage 4: Distroless Runtime
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
    LITESTAR_APP="${LITESTAR_APP}"

# Copy Python interpreter + stdlib
COPY --from=runtime-prep /usr/local/lib/ /usr/local/lib/
COPY --from=runtime-prep /usr/local/bin/python /usr/local/bin/python
COPY --from=runtime-prep /etc/ld.so.cache /etc/ld.so.cache

# Tini for signal handling
COPY --from=runtime-prep /usr/bin/tini /usr/local/bin/tini

# Shared libraries (arch-aware) and TLS certs
COPY --from=runtime-prep /runtime-libs/lib/ /lib/
COPY --from=runtime-prep /runtime-libs/usr/lib/ /usr/lib/
COPY --from=runtime-prep /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Application venv
WORKDIR /workspace/app
COPY --from=runtime-prep --chown=65532:65532 /workspace/app/.venv /workspace/app/.venv

STOPSIGNAL SIGINT
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/tini", "--"]
CMD ["app", "run", "--host", "0.0.0.0"]
```

## Why distroless

| Property | `python:slim` | `distroless/cc-debian12` |
| --- | --- | --- |
| Shell | Yes (`/bin/sh`, `/bin/bash`) | **None** |
| Package manager | Yes (apt) | **None** |
| CVE surface | Moderate | **Minimal** |
| Image size | ~150-200MB | **~80-120MB** |
| Debug access | `docker exec bash` | Requires debug image variant |
| Health probes | exec or HTTP | **HTTP only** (no shell for exec) |

## Why 4 stages (not 3)

Distroless has no Python interpreter. Stage 3 (`runtime-prep`) creates a self-contained venv with a **copied** Python binary (not symlinked) and gathers architecture-specific shared libraries. Stage 4 copies only what is needed into the distroless base.

## Multi-architecture build

```bash
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -f Dockerfile.distroless \
    -t ghcr.io/myorg/myapp:v1.0.0 \
    --push .
```

The `TARGETARCH` ARG is automatically set by BuildKit. The runtime-prep stage uses it to copy the correct `lib/x86_64-linux-gnu` or `lib/aarch64-linux-gnu` directory.

## Build-time env vars

```dockerfile
DATABASE_POOL_DISABLED=true
SAQ_USE_SERVER_LIFESPAN=false
SAQ_WEB_ENABLED=false
```

These prevent the application from attempting database or Redis connections during `uv run app assets build`. Without them, the build fails if no database is reachable.

## Railway compatibility

This Dockerfile avoids `--mount=type=cache` (Railway's builder does not support BuildKit cache mounts). All `apt-get` and `uv` operations run without cache mounts.
