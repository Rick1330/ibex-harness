#!/usr/bin/env bash
# Generate sustained probe traffic against the memory service for Grafana/Prometheus.
# Use after: make compose-test-up && memory service on :8005 && make observability-up
set -euo pipefail

MEMORY_ADDR="${IBEX_MEMORY_ADDR:-http://127.0.0.1:8005}"
DURATION_SEC="${IBEX_MEMORY_TRAFFIC_DURATION_SEC:-120}"
INTERVAL_SEC="${IBEX_MEMORY_TRAFFIC_INTERVAL_SEC:-1}"

if ! curl -fsS --connect-timeout 2 --max-time 5 "${MEMORY_ADDR}/health" >/dev/null 2>&1; then
  echo "observability-memory-traffic: memory not reachable at ${MEMORY_ADDR}" >&2
  echo "Start it with IBEX_MEMORY_DATABASE_URL=... uv run uvicorn app.main:app --host 127.0.0.1 --port 8005" >&2
  exit 1
fi

echo "observability-memory-traffic: hitting ${MEMORY_ADDR} for ${DURATION_SEC}s (every ${INTERVAL_SEC}s)"
end=$((SECONDS + DURATION_SEC))
count=0
while (( SECONDS < end )); do
  curl -fsS --connect-timeout 2 --max-time 5 "${MEMORY_ADDR}/health" >/dev/null || true
  curl -fsS --connect-timeout 2 --max-time 5 "${MEMORY_ADDR}/ready" >/dev/null || true
  curl -fsS --connect-timeout 2 --max-time 5 "${MEMORY_ADDR}/metrics" >/dev/null || true
  count=$((count + 3))
  sleep "$INTERVAL_SEC"
done

echo "observability-memory-traffic: done (${count} requests). Open Grafana → IBEX Memory Service (last 15m)."
