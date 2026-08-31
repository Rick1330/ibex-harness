#!/usr/bin/env bash
# Run services/worker Redis integration tests (requires live Redis).
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

cd "$WORKER_DIR"
bash "$ROOT/infra/scripts/worker-uv-sync.sh"
.venv/bin/pytest -q -m integration
