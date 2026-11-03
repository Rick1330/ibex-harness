#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

fail=0
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  echo "Legacy benchmark path not allowed: $path (use site/public/benchmarks/)"
  fail=1
done < <(git ls-files 'docs/app/public/benchmarks/*' 'web/public/benchmarks/*' 2>/dev/null || true)

exit "$fail"
