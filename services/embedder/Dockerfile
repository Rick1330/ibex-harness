# IBEX Embedder service — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-embedder:local -f services/embedder/Dockerfile .
#
# Run (compose network; TEI HTTP only with ALLOW_INSECURE):
#   docker run --rm -p 8004:8004 --network <compose-network> \
#     -e IBEX_EMBEDDING_PROFILE=gpu \
#     -e IBEX_EMBEDDING_TEI_BASE_URL=http://tei:80 \
#     -e IBEX_EMBEDDING_TEI_ALLOW_INSECURE=true \
#     -e IBEX_EMBEDDING_API_TOKEN=<shared-token> \
#     ibex-embedder:local

# --------------------------------------------------------------------------- #
# Stage 1 — copy pinned uv binary (no pip install / setup.py execution)       #
# --------------------------------------------------------------------------- #
FROM ghcr.io/astral-sh/uv:0.7.20@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — dependency install (wheels only; no sdist setup.py execution)     #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Copy only lockfile + project manifest first for layer cache efficiency.
COPY services/embedder/pyproject.toml services/embedder/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project

# --------------------------------------------------------------------------- #
# Stage 3 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Apply Debian security patches, then drop to a non-root user.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

# Copy virtualenv from build stage.
COPY --from=deps /app/.venv ./.venv

# Copy application source last (cache busting only when code changes).
COPY services/embedder/app ./app

USER ibex

EXPOSE 8004

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
