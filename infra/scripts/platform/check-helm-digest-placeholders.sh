#!/usr/bin/env bash
# Fail if staging/prod Helm *merged* renders still carry placeholder digests.
# Checking overlay files alone is insufficient: Helm inherits images.* from values.yaml.
#
# Sentinels rejected (must not ship to a cluster):
#   - sha256:0000… (zero-filled)
#   - sha256:<same hex digit repeated> e.g. aaaa… / bbbb… / 1111… (CI stub alphabet)
# Real docker-publish digests are mixed hex and pass.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="$ROOT/infra/helm/ibex-harness"
fail=0

# Zero-filled OR a single hex digit repeated ≥16 times (covers a{64}, 1{64}, …).
SENTINEL_RE='sha256:(0{16,}|([0-9a-f])\2{15,})'

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
  if echo "$rendered" | grep -nE "$SENTINEL_RE"; then
    echo "ERROR: merged $label render contains sentinel digests (zeros or repeated hex)" >&2
    echo "       Inject real docker-publish digests into $overlay (or --set-string) before deploy." >&2
    fail=1
  else
    echo "OK: merged $label render has no sentinel digests"
  fi
}

check_merged "$CHART/values-staging.yaml" "staging"
check_merged "$CHART/values-prod.yaml" "prod"

if grep -nE "$SENTINEL_RE" "$CHART/values.yaml" >/dev/null; then
  echo "NOTE: values.yaml still contains sentinel digests (dev stubs). Staging/prod must override with real pins."
fi

exit "$fail"
