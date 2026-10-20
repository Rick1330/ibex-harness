# IBEX MCP operator gateway — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-mcp-operator:local -f services/mcp-operator/Dockerfile .
#
# Run (gateway is inert unless explicitly enabled):
#   docker run --rm -p 8091:8091 \
#     -e IBEX_ENV=development \
#     -e IBEX_MCP_OPERATOR_ENABLED=true \
#     -e IBEX_MCP_OPERATOR_DATABASE_URL=postgresql+asyncpg://ibex_app:...@postgres:5432/ibex \
#     -e IBEX_AUTH_GRPC_ADDR=auth:9091 \
#     -e IBEX_MCP_OPERATOR_RESOURCE_URL=http://127.0.0.1:8091/mcp \
#     ibex-mcp-operator:local

# --------------------------------------------------------------------------- #
# Stage 1 — copy pinned uv binary (no pip install / setup.py execution)        #
# --------------------------------------------------------------------------- #
FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — dependency install (wheels only; no sdist setup.py execution)      #
# --------------------------------------------------------------------------- #
FROM python@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app/services/mcp-operator

COPY packages/authclient /app/packages/authclient
COPY packages/mcp_gateway /app/packages/mcp_gateway
COPY packages/ibex_async_db /app/packages/ibex_async_db
# Trusted monorepo wheels only — UV_NO_BUILD=1 blocks uv build globally (Sonar S8541).
RUN mkdir -p /wheels \
    && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/authclient \
    && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/mcp_gateway \
    && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/ibex_async_db
COPY services/mcp-operator/pyproject.toml services/mcp-operator/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project --find-links /wheels \
        --no-install-package authclient \
        --no-install-package mcp-gateway \
        --no-install-package ibex-async-db \
    && uv pip install --no-cache --force-reinstall --no-index --no-deps --find-links /wheels \
        "authclient" "mcp-gateway" "ibex-async-db"

# --------------------------------------------------------------------------- #
# Stage 3 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    IBEX_MCP_OPERATOR_HOST=0.0.0.0 \
    IBEX_MCP_OPERATOR_PORT=8091

RUN python -m pip uninstall --yes setuptools wheel || true \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libpcre2-8-0=10.42-1+deb12u2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

COPY --from=deps /app/.venv ./.venv
COPY services/mcp-operator/app ./app

USER 10001:10001

EXPOSE 8091

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health')"]

CMD ["sh", "-c", "exec uvicorn app.main:app --host \"${IBEX_MCP_OPERATOR_HOST}\" --port \"${IBEX_MCP_OPERATOR_PORT}\""]
