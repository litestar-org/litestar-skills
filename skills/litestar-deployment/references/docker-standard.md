# Docker Standard Multi-Stage Build

Standard multi-stage Dockerfile for Litestar applications using `python:slim` as the runtime base. Use this when you need a shell in the production container (debugging, exec probes) or when distroless is incompatible with your environment.

For production, prefer [docker-distroless.md](docker-distroless.md) instead.

## Complete Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.13
ARG DEBIAN_VERSION=bookworm
ARG BUILDER_IMAGE=python:${PYTHON_VERSION}-slim-${DEBIAN_VERSION}

# =============================================================================
# Stage 1: Python Base
# =============================================================================
FROM ${BUILDER_IMAGE} AS python-base

RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
    && rm -rf /var/log/* /tmp/* \
    && mkdir -p /workspace/app

# uv for Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Bun for frontend asset builds
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
    LC_ALL=C.UTF-8

RUN --mount=type=cache,id=apt-cache-builder,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib-builder,target=/var/lib/apt,sharing=locked \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/log/* /tmp/*

WORKDIR /workspace/app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock README.md ./
COPY src/js/web/package.json src/js/web/bun.lock ./src/js/web/

# Install JS dependencies
WORKDIR /workspace/app/src/js/web
RUN bun install --frozen-lockfile
WORKDIR /workspace/app

# Install Python dependencies (no project yet)
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv venv \
    && uv sync ${UV_INSTALL_ARGS} --frozen --no-install-project --no-editable \
    && uv export ${UV_INSTALL_ARGS} --frozen --no-hashes --no-emit-project \
       --output-file=requirements.txt

# Copy source
COPY src/ ./src/

# Build frontend assets + wheel
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv run app assets build \
    && uv sync ${UV_INSTALL_ARGS} --frozen --no-editable \
    && uv build

# =============================================================================
# Stage 3: Runtime
# =============================================================================
FROM python-base AS runtime

ARG LITESTAR_APP="app.server.asgi:create_app"

ENV PATH="/workspace/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    LITESTAR_APP="${LITESTAR_APP}"

# Non-root user
RUN groupadd --system --gid 65532 nonroot \
    && useradd --no-create-home --system --uid 65532 --gid 65532 nonroot \
    && mkdir -p /workspace/app \
    && chown -R nonroot:nonroot /workspace

# Install wheel from builder
COPY --from=builder --chown=65532:65532 /workspace/app/dist/*.whl /tmp/

WORKDIR /workspace/app

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv pip install --quiet --no-cache-dir /tmp/*.whl \
    && rm -rf /tmp/* \
    && chown -R nonroot:nonroot /workspace/app

USER nonroot

STOPSIGNAL SIGINT
EXPOSE 8000

ENTRYPOINT ["tini", "--"]
CMD ["litestar", "run", "--host", "0.0.0.0", "--port", "8000"]
```

## Key decisions

| Decision | Rationale |
|---|---|
| `--mount=type=cache` on apt + uv | Faster rebuilds. Not available on Railway (use distroless variant). |
| `uv build` creates a wheel | Runner installs a wheel, not an editable install. Smaller image, faster startup. |
| `UV_COMPILE_BYTECODE=1` | Pre-compiles .pyc. Saves 200-500ms on cold start. |
| `UV_LINK_MODE=copy` | Overlay filesystems do not support hardlinks. Always copy. |
| `tini` as PID 1 | Proper signal forwarding and zombie reaping. |
| `STOPSIGNAL SIGINT` | Granian handles SIGINT for graceful shutdown. |
| Non-root UID 65532 | Matches distroless `nonroot`. Consistent across all image variants. |

## When to use standard vs distroless

| Need | Standard | Distroless |
|---|---|---|
| Shell access (`docker exec bash`) | Yes | No |
| exec-based health probes | Yes | No |
| Minimal CVE surface | Good | Best |
| Image size | ~150-200MB | ~80-120MB |
| Production recommended | Acceptable | **Preferred** |
