# IBEX Context Assembly service — multi-stage, non-root, uv-managed.
#
# HEALTHCHECK is only emitted for a Docker-format build. Podman 5.7 defaults to
# OCI, which drops it: build with `--format docker` or declare an
# equivalent compose `healthcheck`.
#
# Build:
#   podman build -t ibex-context:local -f services/context/Dockerfile .
#
# Run (binds loopback only — ADR-0096; reach it from a sidecar sharing the
# network namespace, not from the host or another container):
#   podman run --rm \
#     -e IBEX_CONTEXT_MEMORY_BASE_URL=http://memory:8005 \
#     -e IBEX_CONTEXT_MEMORY_API_TOKEN=<memory API token> \
#     -e IBEX_CONTEXT_GRPC_SERVICE_TOKEN=<32-512 char token> \
#     ibex-context:local
#
# Required env at startup:
#   IBEX_CONTEXT_MEMORY_BASE_URL    memory service base URL (required)
#   IBEX_CONTEXT_MEMORY_API_TOKEN   memory API token (required for retrieval)
#   IBEX_CONTEXT_GRPC_SERVICE_TOKEN shared caller token (required, 32-512 chars;
#                                   must differ from the memory token)
# Optional:
#   IBEX_CONTEXT_GRPC_ADDR          loopback host:port (default 127.0.0.1:9092)

# --------------------------------------------------------------------------- #
# Stage 1 — copy pinned uv binary (no pip install / setup.py execution)       #
# --------------------------------------------------------------------------- #
FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — generate the Python protobuf stubs from the repository protos.    #
#                                                                              #
# grpcio-tools==1.83.1 is pinned through the `stubs` extra in                 #
# services/context/uv.lock, so the generator and its transitive dependencies  #
# come from the lockfile instead of resolving at build time. The stubs are    #
# generated here because packages/proto/gen/ is gitignored and not vendored.  #
# --------------------------------------------------------------------------- #
FROM python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 AS stubs

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY services/context/pyproject.toml services/context/uv.lock ./

RUN uv sync --frozen --extra stubs --no-install-project

COPY packages/proto/proto /src/packages/proto/proto

RUN mkdir -p /gen \
    && /app/.venv/bin/python -m grpc_tools.protoc \
      -I /src/packages/proto/proto \
      --python_out=/gen \
      --grpc_python_out=/gen \
      /src/packages/proto/proto/ibex/context/v1/context.proto \
      /src/packages/proto/proto/ibex/auth/v1/principal_context.proto

# --------------------------------------------------------------------------- #
# Stage 3 — dependency install (wheels only; no sdist setup.py execution)     #
# --------------------------------------------------------------------------- #
FROM python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Copy only lockfile + project manifest first for layer cache efficiency.
COPY services/context/pyproject.toml services/context/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project

# --------------------------------------------------------------------------- #
# Stage 4 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 AS runtime

# /gen holds the generated ibex.* stubs; /app holds the app package.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:/gen"

# Apply Debian security patches, then drop to a non-root user.
RUN python -m pip uninstall --yes setuptools wheel || true \
    && rm -rf /usr/local/lib/python3.*/site-packages/pip* \
       /usr/local/lib/python3.*/ensurepip \
       /usr/local/bin/pip* \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libpcre2-8-0=10.42-1+deb12u2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

# Copy virtualenv from build stage.
COPY --from=deps /app/.venv ./.venv

# Copy application source last (cache busting only when code changes).
COPY services/context/app ./app

# Generated gRPC/protobuf stubs (ibex.context.v1.*, ibex.auth.v1.*).
COPY --from=stubs /gen /gen

USER 10001:10001

EXPOSE 9092

# Readiness surface: the standard grpc.health.v1.Health service is registered
# and the server reports SERVING only after it has started, so the health
# surface is now real readiness rather than only a TCP listener. Health RPCs
# stay unauthenticated like the standard protocol. The HEALTHCHECK below stays
# a cheap TCP liveness probe. Resolve the host/port from
# IBEX_CONTEXT_GRPC_ADDR so a ::1 bind is probed on the address that was
# actually opened.
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, socket; addr = os.environ.get('IBEX_CONTEXT_GRPC_ADDR', '127.0.0.1:9092'); host, _, port = addr.rpartition(':'); host = host.strip('[]') or '127.0.0.1'; s = socket.create_connection((host, int(port)), timeout=2); s.close()"]

CMD ["python", "-m", "app"]
