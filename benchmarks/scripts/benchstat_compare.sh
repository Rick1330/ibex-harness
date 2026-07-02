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
  go install golang.org/x/perf/cmd/benchstat@latest
fi

benchstat "${OUT_DIR}/prev-go-bench.txt" "${OUT_DIR}/go-bench.txt" > "${OUT_DIR}/benchstat.txt"
