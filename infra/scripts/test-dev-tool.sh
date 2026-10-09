#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/infra/tool-versions.env"

out="$(IBEX_TEST_MODE=1 bash "$ROOT_DIR/infra/scripts/dev-tool.sh" check-tools 2>&1)" || {
  echo "$out"
  exit 1
}
grep -q 'GO_VERSION' <<<"$out"
grep -q 'PASS' <<<"$out"

if OTEL_EXPORTER_OTLP_ENDPOINT=http://injected.example \
   bash -c 'source "$1"; test -z "${OTEL_EXPORTER_OTLP_ENDPOINT:-}"' _ "$ROOT_DIR/infra/scripts/test-env.sh"; then
  :
else
  echo 'telemetry isolation test failed' >&2
  exit 1
fi

echo 'dev-tool tests: PASS'
