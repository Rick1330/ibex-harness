#!/usr/bin/env bash
# Evaluate the memory benchmark aggregate gate.
#
# Usage: evaluate-memory-benchmark-gate.sh <bench_active:true|false> <detector_result> <result>...
#
# `memory-benchmark.yml` used to be path-filtered at the trigger, so a pull request that did
# not touch the memory-bench paths produced no run and no status. It now runs unconditionally
# and this script decides the outcome, which is what lets `ci-gate-memory-benchmark` be a
# required check without ever leaving it "Expected".
#
# Rules:
#   - The change detector must succeed. Without its verdict the gate cannot know whether the
#     collectors were due, so an unknown is a failure rather than a pass.
#   - bench_active=false: the collectors were not due. The gate passes; their `skipped`
#     results are expected and carry no information.
#   - bench_active=true: every collector must have run and passed. `skipped` is a failure
#     here, because it means a collector was due and did not run.
set -euo pipefail

bench_active="${1:?bench_active required (true|false)}"
detector_result="${2:?detector_result required (must be success)}"
shift 2

if [[ "$detector_result" != "success" ]]; then
  echo "Gate blocked: memory-bench change detector result=${detector_result}" >&2
  exit 1
fi

case "$bench_active" in
  true|false) ;;
  *)
    echo "Invalid bench_active=${bench_active}; expected true or false" >&2
    exit 2
    ;;
esac

if [[ "$bench_active" != "true" ]]; then
  echo "Memory benchmark paths unchanged; gate passes without running the collectors."
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  echo "No collector results supplied" >&2
  exit 1
fi

failed=0
for result in "$@"; do
  if [[ "$result" != "success" ]]; then
    echo "Gate blocked: collector result=${result} (bench_active=true)" >&2
    failed=1
  fi
done

exit "$failed"
