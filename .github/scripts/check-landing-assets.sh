#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PUBLIC="$ROOT/web/public"

REQUIRED=(
  "ibex-ascii.webm"
  "ibex-ascii.mp4"
  "ibex-ascii-dark.webm"
  "ibex-ascii-dark.mp4"
  "ibex-ascii-poster.webp"
  "brand/ascii-tile.webp"
)

fail=0
for asset in "${REQUIRED[@]}"; do
  if [[ ! -f "$PUBLIC/$asset" ]]; then
    echo "Missing landing hero asset: web/public/$asset"
    fail=1
  fi
done

while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  echo "Legacy benchmark path not allowed: $path (use web/public/benchmarks/)"
  fail=1
done < <(git ls-files 'docs/app/public/benchmarks/*' 2>/dev/null || true)

exit "$fail"
