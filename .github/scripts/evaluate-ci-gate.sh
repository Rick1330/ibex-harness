#!/usr/bin/env bash
# Evaluate a CI area gate. Usage: evaluate-ci-gate.sh <run_area:true|false> <result>...
set -euo pipefail

run_area="${1:?run_area required (true|false)}"
shift

if [[ "$run_area" != "true" ]]; then
  echo "Area inactive; gate passes without running child jobs."
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  echo "No child job results supplied"
  exit 1
fi

failed=0
for result in "$@"; do
  case "$result" in
    success|skipped) ;;
    cancelled|failure)
      echo "Gate blocked: child job result=${result}"
      failed=1
      ;;
    *)
      echo "Gate blocked: unexpected child job result=${result}"
      failed=1
      ;;
  esac
done

exit "$failed"
