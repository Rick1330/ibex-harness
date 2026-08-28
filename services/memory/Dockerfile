# IBEX Memory service — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-memory:local -f services/memory/Dockerfile .
#
# Run:
#   docker run --rm -p 8005:8005 \
#     -e IBEX_MEMORY_DATABASE_URL=postgresql+asyncpg://ibex:ibex@postgres:5432/ibex \
#     ibex-memory:local

FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app/services/memory

COPY packages/authclient /app/packages/authclient
COPY services/memory/pyproject.toml services/memory/uv.lock ./

RUN uv sync --frozen --no-install-project

FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /sbin/nologin ibex

WORKDIR /app

COPY --from=deps /app/services/memory/.venv ./.venv

COPY services/memory/app ./app

USER ibex

EXPOSE 8005

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8005/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
