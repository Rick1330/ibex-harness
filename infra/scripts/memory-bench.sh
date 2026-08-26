#!/usr/bin/env bash
# Run memory HNSW benches under benchmarks/memory/ (needs migrated pgvector Postgres).
# Extra args after the script are forwarded to hnsw_bench.py
# (e.g. --ef-search 40 --min-similarity 0.0 0.70).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"
BENCH_DIR="$ROOT/benchmarks/memory"
SIZES="${MEMORY_BENCH_SIZES:-10000 100000}"
OUTPUT="${MEMORY_BENCH_OUTPUT:-$BENCH_DIR/output/hnsw_recall_latency.json}"
PUBLISHED="${MEMORY_BENCH_PUBLISHED:-$ROOT/web/public/benchmarks/hnsw-benchmark-data.json}"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping memory benches"
  exit 0
fi

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${IBEX_MEMORY_DATABASE_URL:-${CANONICAL_DSN}}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$MEMORY_DIR"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"

# Bench code lives under benchmarks/memory; app imports resolve via services/memory.
# shellcheck disable=SC2086
PYTHONPATH="$MEMORY_DIR" .venv/bin/python "$BENCH_DIR/hnsw_bench.py" \
  --sizes ${SIZES} \
  --output "$OUTPUT" \
  "$@"

PYTHONPATH="$MEMORY_DIR" .venv/bin/python "$BENCH_DIR/build_published_data.py" \
  --raw "$OUTPUT" \
  --published "$PUBLISHED" \
  --sha "${GITHUB_SHA:-$(git -C "$ROOT" rev-parse HEAD)}" \
  --branch "${GITHUB_REF_NAME:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)}" \
  --run-number "${GITHUB_RUN_NUMBER:-0}" \
  --run-url "${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-Rick1330/ibex-harness}/actions/runs/${GITHUB_RUN_ID:-0}"
