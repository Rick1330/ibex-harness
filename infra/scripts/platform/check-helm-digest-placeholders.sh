#!/usr/bin/env bash
# Fail if staging/prod Helm *merged* renders still carry placeholder sha256:000… digests.
# Checking the overlay files alone is insufficient: Helm inherits images.* from values.yaml.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="$ROOT/infra/helm/ibex-harness"
fail=0

if ! command -v helm >/dev/null 2>&1; then
  echo "ERROR: helm required for digest placeholder guard" >&2
  exit 1
fi

check_merged() {
  local overlay="$1"
  local label="$2"
  local rendered
  if ! rendered="$(helm template "ibex-digest-guard-${label}" "$CHART" -f "$overlay" 2>/dev/null)"; then
    echo "ERROR: helm template failed for $label ($overlay)" >&2
    fail=1
    return
  fi
  if echo "$rendered" | grep -nE 'sha256:0{10,}'; then
    echo "ERROR: merged $label render contains placeholder sha256:000… digests" >&2
    echo "       Override every images.* entry in $overlay (or --set-string) before deploy." >&2
    fail=1
  else
    echo "OK: merged $label render has no sha256:000… placeholders"
  fi
}

check_merged "$CHART/values-staging.yaml" "staging"
check_merged "$CHART/values-prod.yaml" "prod"

# Default values.yaml may keep stubs for local kind; never use alone for staging/prod.
if grep -nE 'sha256:0{10,}' "$CHART/values.yaml" >/dev/null; then
  echo "NOTE: values.yaml still contains placeholder digests (dev stubs). Staging/prod must override."
fi

exit "$fail"
