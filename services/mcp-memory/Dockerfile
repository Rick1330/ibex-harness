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
FROM ghcr.io/astral-sh/uv:0.7.20 AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — dependency install (wheels only; no sdist setup.py execution)     #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY services/mcp-memory/pyproject.toml services/mcp-memory/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project

# --------------------------------------------------------------------------- #
# Stage 3 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

COPY --from=deps /app/.venv ./.venv
COPY services/mcp-memory/app ./app

USER ibex

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
