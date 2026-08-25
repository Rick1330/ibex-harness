#!/usr/bin/env bash
# Phase 2.5 exit gate verification (Tracks A–F unit/package checks + optional live e2e).
#
# Usage:
#   make verify-phase25
#   IBEX_VERIFY_PHASE25_E2E=1 make verify-phase25   # also run e2e-phase25 + observability-smoke
#
# Exit criteria mapping: web/content/roadmap/.../2.5.g7-phase25-exit-gate.mdx
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
section() { echo ""; echo "=== $* ==="; }

# Proto stubs are gitignored; generate when missing so proxy/auth unit smoke can compile.
if [[ ! -d packages/proto/gen/go/ibex/auth/v1 ]]; then
  section "Generate protobuf stubs (ephemeral)"
  if ! command -v buf >/dev/null 2>&1; then
    fail "buf CLI required to generate packages/proto/gen (install: https://buf.build/docs/installation)"
  fi
  (cd packages/proto && buf generate) || fail "buf generate failed"
  pass "protobuf stubs generated"
fi

section "Exit #1–3: provider / capability registry"
go test ./packages/provider/... ./packages/permissions/... -count=1
pass "provider + permissions packages"

section "Exit #4: response pipeline"
go test ./packages/responsepipeline/... -count=1
bash infra/scripts/coverage-responsepipeline-gate_test.sh
pass "responsepipeline"

section "Exit #2–3 / Track B: tokenizer"
go test ./packages/tokenizer/... -count=1
pass "tokenizer"

section "Exit #6: postgres migration files present (14–16)"
for f in \
  infra/migrations/postgres/000014_create_memories_temporal.up.sql \
  infra/migrations/postgres/000015_create_memory_labels.up.sql \
  infra/migrations/postgres/000016_create_memory_relationships.up.sql
do
  [[ -f "$f" ]] || fail "missing $f"
done
pass "schema migrations 14–16 on disk"

section "Exit #5: embedder unit/contract suite"
bash infra/scripts/embedder-test-ci.sh
pass "embedder tests"

section "Exit #7 (unit evidence): mcp-memory suite"
bash infra/scripts/mcp-memory-test-ci.sh
pass "mcp-memory tests"

section "Exit #8: proxy + auth unit smoke"
go test ./services/proxy/... ./services/auth/... -count=1
pass "proxy + auth unit"

section "ClickHouse MCP audit migration present"
[[ -f infra/migrations/clickhouse/000002_create_mcp_tool_calls.up.sql ]] \
  || fail "missing mcp_tool_calls migration"
bash infra/scripts/clickhouse-migrate-test-ci.sh
pass "clickhouse migrate unit"

section "Observability artifacts (ADR-0051)"
[[ -f infra/compose/observability/docker-compose.yml ]] || fail "missing observability compose"
[[ -f infra/monitoring/prometheus/prometheus.yml ]] || fail "missing prometheus.yml"
[[ -f infra/monitoring/grafana/dashboards/proxy-critical-path.json ]] || fail "missing Proxy Critical Path dashboard"
[[ -f web/content/docs/adr/0051-local-lgtm-observability-stack.mdx ]] || fail "missing ADR-0051"
pass "observability configs present"

if [[ "${IBEX_VERIFY_PHASE25_E2E:-0}" == "1" ]]; then
  section "Live e2e + MCP conformance + observability smoke"
  bash infra/scripts/mcp-conformance.sh
  bash infra/scripts/e2e_phase25.sh
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ibex-obs-grafana; then
    bash infra/scripts/observability-traffic.sh || true
    # Fail closed when series are required; do not fall back to a health-only smoke.
    IBEX_OBS_REQUIRE_IBEX_SERIES=1 bash infra/scripts/observability-smoke.sh
  else
    echo "WARN: observability stack not up; skipping observability-smoke (make observability-up)"
    echo "NOTE: for live Grafana series under demo ports, run make observability-live-verify"
  fi
  pass "live e2e path"
else
  echo ""
  echo "NOTE: set IBEX_VERIFY_PHASE25_E2E=1 to run multi-service e2e + conformance + obs smoke"
fi

echo ""
echo "verify-phase25 passed"
