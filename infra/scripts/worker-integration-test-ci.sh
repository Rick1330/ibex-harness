#!/usr/bin/env bash
# Run services/worker integration tests (Redis + Postgres + optional CH/MinIO multistore).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKER_DIR="$ROOT/services/worker"

if [[ ! -f "$WORKER_DIR/pyproject.toml" ]]; then
  echo "services/worker not present — worker integration tests required in CI" >&2
  exit 1
fi

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export REDIS_DB_QUEUE="${REDIS_DB_QUEUE:-1}"
export REDIS_DB_RESULTS="${REDIS_DB_RESULTS:-3}"
export IBEX_WORKER_INTEGRATION_TESTS="${IBEX_WORKER_INTEGRATION_TESTS:-1}"

if [[ -z "${POSTGRES_TEST_DSN:-}" ]]; then
  echo "POSTGRES_TEST_DSN required for worker dead-letter integration tests" >&2
  exit 1
fi

export POSTGRES_DSN="${POSTGRES_TEST_DSN}"
export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_TEST_DSN}}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

# Multi-store org-deletion absence tests (pytest skips if env incomplete).
if [[ -n "${CLICKHOUSE_DSN:-}" ]]; then
  if [[ -z "${CLICKHOUSE_MIGRATE_DSN:-}" ]]; then
    if [[ -n "${CLICKHOUSE_NATIVE_DSN:-}" ]]; then
      export CLICKHOUSE_MIGRATE_DSN="${CLICKHOUSE_NATIVE_DSN}"
    elif [[ "${CLICKHOUSE_DSN}" == http* ]] || [[ "${CLICKHOUSE_DSN}" == https* ]]; then
      echo "CLICKHOUSE_MIGRATE_DSN (native) required when CLICKHOUSE_DSN is HTTP" >&2
      exit 1
    else
      export CLICKHOUSE_MIGRATE_DSN="${CLICKHOUSE_DSN}"
    fi
  fi
  bash "$ROOT/infra/scripts/clickhouse-migrate.sh" up
  export IBEX_ORG_DELETION_MULTISTORE_TEST="${IBEX_ORG_DELETION_MULTISTORE_TEST:-1}"
  export IBEX_ORG_DELETION_DEPLOYED_STORES="${IBEX_ORG_DELETION_DEPLOYED_STORES:-postgres,clickhouse,redis,objectstore}"
fi

if [[ -n "${S3_ENDPOINT:-}" ]]; then
  export S3_ALLOW_INSECURE_HTTP="${S3_ALLOW_INSECURE_HTTP:-1}"
  export S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
  export S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
  export S3_BUCKET_SESSIONS="${S3_BUCKET_SESSIONS:-ibex-sessions}"
  export S3_REGION="${S3_REGION:-us-east-1}"
  if [[ -z "${S3_MASTER_KEY_B64:-}" ]]; then
    S3_MASTER_KEY_B64="$(python3 -c 'import base64,os; print(base64.b64encode(os.urandom(32)).decode())')"
    export S3_MASTER_KEY_B64
  fi
fi

cd "$WORKER_DIR"
bash "$ROOT/infra/scripts/worker-uv-sync.sh"
.venv/bin/pytest -q -m integration
