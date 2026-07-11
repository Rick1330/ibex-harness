#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="benchmarks/output"
mkdir -p "${OUT_DIR}"

if [[ ! -f "${OUT_DIR}/prev-go-bench.txt" ]]; then
  echo "No previous Go benchmark file found; skipping benchstat compare." > "${OUT_DIR}/benchstat.txt"
  exit 0
fi

if ! command -v benchstat >/dev/null 2>&1; then
  GOBIN="$(go env GOPATH)/bin"
  export PATH="${GOBIN}:${PATH}"
  go install golang.org/x/perf/cmd/benchstat@v0.0.0-20240801233422-863df1f04912
fi

benchstat "${OUT_DIR}/prev-go-bench.txt" "${OUT_DIR}/go-bench.txt" > "${OUT_DIR}/benchstat.txt"
if benchstat -format=json "${OUT_DIR}/go-bench.txt" > "${OUT_DIR}/benchstat.json" 2>/dev/null; then
  echo "Wrote benchstat JSON to ${OUT_DIR}/benchstat.json"
else
  echo '{}' > "${OUT_DIR}/benchstat.json"
fi
