# IBEX Management API — multi-stage, non-root, uv-managed.
#
# Build:
#   docker build -t ibex-api:local -f services/api/Dockerfile .
#
# Run:
#   docker run --rm -p 8010:8010 \
#     -e IBEX_API_DATABASE_URL=postgresql+asyncpg://ibex:ibex@postgres:5432/ibex \
#     ibex-api:local

FROM ghcr.io/astral-sh/uv@sha256:2fd1b38e3398a256d6af3f71f0e2ba6a517b249998726a64d8cfbe55ab34af5e AS uv

FROM python@sha256:b64e9d3a71eddaa1b3f80c04abf292b3139e3b7c4dd272d19c31dc1f91194d1b AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_NO_BUILD=1

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app/services/api

COPY packages/authclient /app/packages/authclient
COPY packages/ibex_async_db /app/packages/ibex_async_db
COPY packages/apierror_py /app/packages/apierror_py
# Trusted monorepo wheel only — UV_NO_BUILD=1 blocks uv build globally (Sonar S8541).
RUN mkdir -p /wheels && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/authclient \
    && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/ibex_async_db \
    && UV_NO_BUILD=0 uv build --wheel --out-dir /wheels /app/packages/apierror_py
COPY services/api/pyproject.toml services/api/uv.lock ./

RUN uv sync --frozen --no-build --no-install-project --find-links /wheels \
    --no-install-package authclient --no-install-package ibex-async-db --no-install-package apierror-py \
    && uv pip install --no-index --find-links /wheels \
    "authclient==0.1.3" "ibex-async-db==0.1.0" "apierror-py==0.1.0"

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

COPY --from=deps /app/services/api/.venv ./.venv

COPY services/api/app ./app

USER ibex

EXPOSE 8010

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
