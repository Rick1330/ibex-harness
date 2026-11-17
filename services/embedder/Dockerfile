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
FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

# --------------------------------------------------------------------------- #
# Stage 2 — dependency install (wheels only; no sdist setup.py execution)     #
# --------------------------------------------------------------------------- #
FROM python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 AS deps

# UV_HTTP_TIMEOUT bounds a slow registry fetch; it does not change what is installed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1 \
    UV_HTTP_TIMEOUT=300

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Copy only lockfile + project manifest first for layer cache efficiency.
COPY services/embedder/pyproject.toml services/embedder/uv.lock ./

# Install third-party dependencies from lockfile (wheels only — Sonar S8541).
RUN uv sync --frozen --no-build --no-install-project

# --------------------------------------------------------------------------- #
# Stage 3 — runtime image                                                      #
# --------------------------------------------------------------------------- #
FROM python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Debian security patches come from the pinned base digest, not from an in-build
# blanket upgrade: that step is a no-op on this base and only makes the build
# resolve against a mutable package index. Refresh the base digest to take new
# fixes; see engineering/quality/base-images.md. apt-get update stays for the
# libpcre2 pin below.
RUN python -m pip uninstall --yes setuptools wheel || true \
    && rm -rf /usr/local/lib/python3.*/site-packages/pip* \
       /usr/local/lib/python3.*/ensurepip \
       /usr/local/bin/pip* \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpcre2-8-0=10.42-1+deb12u2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

# Copy virtualenv from build stage.
COPY --from=deps /app/.venv ./.venv

# Copy application source last (cache busting only when code changes).
COPY services/embedder/app ./app

USER 10001:10001

EXPOSE 8004

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
