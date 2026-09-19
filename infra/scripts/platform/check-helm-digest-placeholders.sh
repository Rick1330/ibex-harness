#!/usr/bin/env bash
# Fail if staging/prod Helm values still carry placeholder sha256:000… digests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
fail=0
for f in \
  "$ROOT/infra/helm/ibex-harness/values-staging.yaml" \
  "$ROOT/infra/helm/ibex-harness/values-prod.yaml"
do
  if [[ ! -f "$f" ]]; then
    continue
  fi
  if grep -nE 'sha256:0{10,}' "$f"; then
    echo "ERROR: placeholder digest in $f — override with docker-publish digests before deploy" >&2
    fail=1
  fi
done
# Default values.yaml may keep stubs for local kind; document that they must never
# be used without --set-string / values-ci-lint / publish overlays.
if grep -nE 'sha256:0{10,}' "$ROOT/infra/helm/ibex-harness/values.yaml" >/dev/null; then
  echo "NOTE: values.yaml still contains placeholder digests (dev stubs). Staging/prod must override."
fi
exit "$fail"
