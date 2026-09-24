#!/usr/bin/env bash
# Evaluate a CI area gate. Usage: evaluate-ci-gate.sh <run_area:true|false> <changes_result> <result>...
set -euo pipefail

run_area="${1:?run_area required (true|false)}"
changes_result="${2:?changes_result required (must be success)}"
shift 2

if [[ "$changes_result" != "success" ]]; then
  echo "Gate blocked: path-change detector result=${changes_result}" >&2
  exit 1
fi

if [[ "$run_area" != "true" && "$run_area" != "false" ]]; then
  echo "Invalid run_area=${run_area}; expected true or false" >&2
  exit 2
fi

if [[ "$run_area" != "true" ]]; then
  echo "Area inactive; gate passes without running child jobs."
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  echo "No child job results supplied"
  exit 1
fi

failed=0
seen_success=0
for result in "$@"; do
  case "$result" in
    success)
      seen_success=1
      ;;
    skipped) ;;
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

if [[ "$seen_success" -eq 0 ]]; then
  echo "Gate blocked: active area has no successful applicable child job"
  failed=1
fi

exit "$failed"
