#!/usr/bin/env bash
# Reject manual benchmark-data.json edits that do not match the CI artifact.
set -euo pipefail

BASE_REF="${1:-}"
COMMITTED_PATH="web/public/benchmarks/benchmark-data.json"

if [[ -z "$BASE_REF" ]]; then
  echo "usage: verify_pr_benchmark_integrity.sh <base-ref>" >&2
  exit 1
fi

if [[ ! "$BASE_REF" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,255}$ ]] || [[ "$BASE_REF" == *".."* ]]; then
  echo "verify_pr_benchmark_integrity: invalid base ref" >&2
  exit 1
fi

set +e
git diff --quiet "origin/${BASE_REF}...HEAD" -- "$COMMITTED_PATH"
diff_rc=$?
set -e

if [[ "$diff_rc" -eq 0 ]]; then
  echo "benchmark-data.json unchanged on branch; docs-build overlays the workflow artifact on PRs."
  exit 0
fi

if [[ "$diff_rc" -gt 1 ]]; then
  echo "verify_pr_benchmark_integrity: could not diff against origin/${BASE_REF}; checking artifact match."
fi

if python - "$BENCHMARK_PR_NUMBER" "$COMMITTED_PATH" <<'PY'
import json
import sys
from pathlib import Path

pr_number = int(sys.argv[1])
path = Path(sys.argv[2])
payload = json.loads(path.read_text(encoding="utf-8"))
runs = payload.get("runs", [])
if not isinstance(runs, list):
    sys.exit(1)
for run in runs:
    if isinstance(run, dict) and run.get("pr_number") == pr_number:
        sys.exit(0)
sys.exit(1)
PY
then
  python benchmarks/scripts/compare_pr_benchmark_json.py
  exit $?
fi

echo "Branch does not claim this PR in benchmark-data.json; artifact is the PR preview source."
exit 0
