#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
WEB="$ROOT/web"

fail=0

if [[ ! -f "$WEB/scripts/sanitize-rsc-txt.mjs" ]]; then
  echo "Missing web/scripts/sanitize-rsc-txt.mjs"
  fail=1
fi

if ! grep -q "sanitizeRscTxtFiles" "$WEB/scripts/next-build.mjs"; then
  echo "next-build.mjs must invoke sanitizeRscTxtFiles after static export"
  fail=1
fi

if ! grep -q "text/x-component" "$WEB/public/_headers"; then
  echo "web/public/_headers must set Content-Type for RSC .txt stubs"
  fail=1
fi

if grep -q "loadPublishedBenchmarkData" "$WEB/src/app/(site)/benchmarks/layout.tsx"; then
  echo "benchmarks layout must not embed benchmark JSON in server RSC payload"
  fail=1
fi

exit "$fail"
