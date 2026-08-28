# IBEX MCP Memory service — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-mcp-memory:local -f services/mcp-memory/Dockerfile .
#
# Run:
#   docker run --rm -p 8090:8090 \
#     -e IBEX_AUTH_GRPC_ADDR=auth:9091 \
#     -e IBEX_MCP_RESOURCE_URL=http://127.0.0.1:8090/mcp \
#     ibex-mcp-memory:local

# --------------------------------------------------------------------------- #
# Stage 1 — copy pinned uv binary (no pip install / setup.py execution)       #
# --------------------------------------------------------------------------- #
FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — dependency install (wheels only; no sdist setup.py execution)     #
# --------------------------------------------------------------------------- #
FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app/services/mcp-memory

COPY packages/authclient /app/packages/authclient
# Trusted monorepo wheel only — UV_NO_BUILD=1 blocks uv build globally (Sonar S8541).
RUN mkdir -p /wheels && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/authclient
COPY services/mcp-memory/pyproject.toml services/mcp-memory/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project --find-links /wheels --no-install-package authclient \
    && uv pip install --no-index --find-links /wheels "authclient==0.1.0"

# --------------------------------------------------------------------------- #
# Stage 3 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    IBEX_MCP_HOST=0.0.0.0 \
    IBEX_MCP_PORT=8090

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

COPY --from=deps /app/services/mcp-memory/.venv ./.venv
COPY services/mcp-memory/app ./app

USER ibex

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')"

CMD ["sh", "-c", "uvicorn app.main:app --host \"${IBEX_MCP_HOST}\" --port \"${IBEX_MCP_PORT}\""]
