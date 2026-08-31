# IBEX Worker service — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-worker:local -f services/worker/Dockerfile .
#
# Run:
#   docker run --rm \
#     -e REDIS_URL=redis://redis:6379/0 \
#     -e REDIS_DB_QUEUE=1 \
#     -e REDIS_DB_RESULTS=3 \
#     ibex-worker:local

FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app/services/worker

COPY services/worker/pyproject.toml services/worker/uv.lock ./

RUN uv sync --frozen --no-build --no-install-project

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

COPY --from=deps /app/services/worker/.venv ./.venv
COPY services/worker/app ./app
COPY services/worker/scripts ./scripts

RUN chmod +x scripts/healthcheck.sh

USER ibex

HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=3 \
    CMD ["./scripts/healthcheck.sh"]

CMD ["celery", "-A", "app.celery_app:celery_app", "worker", \
     "-Q", "extraction,embedding,maintenance,mcp_audit", \
     "--loglevel=info"]
