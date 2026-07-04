#!/usr/bin/env bash
# Reject manual benchmark-data.json edits that do not match the CI artifact.
set -euo pipefail

BASE_REF="${1:-}"
COMMITTED_PATH="docs/app/public/benchmarks/benchmark-data.json"

if [[ -z "$BASE_REF" ]]; then
  echo "usage: verify_pr_benchmark_integrity.sh <base-ref>" >&2
  exit 1
fi

if [[ ! "$BASE_REF" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,255}$ ]] || [[ "$BASE_REF" == *".."* ]]; then
  echo "verify_pr_benchmark_integrity: invalid base ref" >&2
  exit 1
fi

git fetch origin "$BASE_REF"

set +e
git diff --quiet "origin/${BASE_REF}...HEAD" -- "$COMMITTED_PATH"
diff_rc=$?
set -e

if [[ "$diff_rc" -eq 0 ]]; then
  echo "benchmark-data.json unchanged on branch; publish will apply the workflow artifact."
  exit 0
fi

if [[ "$diff_rc" -gt 1 ]]; then
  echo "verify_pr_benchmark_integrity: could not diff against origin/${BASE_REF}; checking artifact match."
fi

if python benchmarks/scripts/compare_pr_benchmark_json.py; then
  exit 0
fi

if [[ "${ALLOW_PUBLISH_RECONCILE:-}" == "true" ]]; then
  echo "Committed benchmark data differs from the workflow artifact; publish-benchmark-data will update the branch."
  exit 0
fi

exit 1
