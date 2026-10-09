#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_MIGRATE="$ROOT_DIR/infra/scripts/db-migrate.sh"
CH_MIGRATE="$ROOT_DIR/infra/scripts/clickhouse-migrate.sh"
PROTO_DIR="$ROOT_DIR/packages/proto"
DEV_COMPOSE="$ROOT_DIR/infra/compose/dev/docker-compose.yml"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"
TEST_COMPOSE="$ROOT_DIR/infra/compose/test/docker-compose.yml"
TEST_ENV="$ROOT_DIR/infra/compose/test/.env.example"
OBS_COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
OBS_ENV="$ROOT_DIR/infra/compose/observability/.env.example"
MANIFEST="$ROOT_DIR/infra/tool-versions.conf"
PROTO_BREAKING_AGAINST="${PROTO_BREAKING_AGAINST:-https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto}"

source "$MANIFEST"

if command -v cygpath >/dev/null 2>&1 && [[ -n "${LOCALAPPDATA:-}" ]]; then
  export PATH="$(cygpath -u "$LOCALAPPDATA")/Microsoft/WinGet/Links:$PATH"
fi

require_tool() {
  local tool="$1" message="$2"
  command -v "$tool" >/dev/null 2>&1 || { echo "$message" >&2; exit 1; }
}

runtime() {
  local requested="${IBEX_RUNTIME:-auto}"
  case "$requested" in
    docker)
      require_tool docker 'Docker CLI is missing. Install Docker Desktop/Engine and Compose v2.'
      docker compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 is unavailable.' >&2; exit 1; }
      echo docker ;;
    podman)
      require_tool podman 'Podman is missing. Install Podman and podman-compose.'
      if podman compose version >/dev/null 2>&1; then echo podman
      elif command -v podman-compose >/dev/null 2>&1; then echo podman-compose
      else echo 'Podman Compose is missing. Install podman-compose.' >&2; exit 1; fi ;;
    auto)
      if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then echo docker
      elif command -v podman >/dev/null 2>&1 && (podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1); then
        if podman compose version >/dev/null 2>&1; then echo podman; else echo podman-compose; fi
      else echo 'No supported container runtime found. Install Docker Compose v2 or Podman + podman-compose.' >&2; exit 1; fi ;;
    *) echo "IBEX_RUNTIME must be docker, podman, or auto (got $requested)" >&2; exit 2 ;;
  esac
}

compose() {
  case "$(runtime)" in
    docker) docker compose "$@" ;;
    podman)
      local podman_bin=(podman)
      if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]] || {
        [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)" == true ]] &&
        sudo -n podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -qx false
      }; then
        podman_bin=(sudo -n podman)
      fi
      "${podman_bin[@]}" compose "$@" ;;
    podman-compose) podman-compose "$@" ;;
    *) echo "unsupported container runtime: $(runtime)" >&2; return 2 ;;
  esac
}

compose_files() {
  local kind="$1"
  case "$kind" in
    dev) printf '%s\n' -f "$DEV_COMPOSE" --env-file "$DEV_ENV" ;;
    test) printf '%s\n' -f "$TEST_COMPOSE" --env-file "$TEST_ENV" ;;
    observability) printf '%s\n' -f "$OBS_COMPOSE" --env-file "$OBS_ENV" ;;
    *) echo "unknown compose stack: $kind" >&2; return 2 ;;
  esac
}

compose_with_mode() {
  local kind="$1"; shift
  local args=()
  if [[ "${IBEX_NETWORK:-bridge}" == host ]]; then
    local overlay="$ROOT_DIR/infra/compose/overlays/host/${kind}.yml"
    [[ -f "$overlay" ]] || { echo "missing host-network overlay: $overlay" >&2; exit 1; }
    args+=( -f "$overlay" --env-file "$ROOT_DIR/infra/compose/${kind}/.env.example" )
  elif [[ "${IBEX_NETWORK:-bridge}" != bridge ]]; then
    echo 'IBEX_NETWORK must be bridge or host' >&2; exit 2
  else
    while IFS= read -r arg; do args+=("$arg"); done < <(compose_files "$kind")
  fi
  compose "${args[@]}" "$@"
}

version_ok() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" || "$actual" == "$expected".* || "$actual" == "$expected"-* ]]; then
    printf 'PASS  %-20s %s\n' "$label" "$actual"; return 0
  fi
  printf 'FAIL  %-20s found=%s expected=%s\n' "$label" "$actual" "$expected"
  return 1
}

check_tools() {
  local failures=0 actual
  actual="$(go version 2>/dev/null | sed -n 's/.*go\([0-9.]*\).*/\1/p')"; version_ok GO_VERSION "$actual" "$GO_VERSION" || failures=$((failures+1))
  actual="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"; version_ok NODE_MAJOR "$actual" "$NODE_MAJOR" || failures=$((failures+1))
  actual="$(pnpm --version 2>/dev/null || true)"; version_ok PNPM_VERSION "$actual" "$PNPM_VERSION" || failures=$((failures+1))
  actual="$(python3 --version 2>/dev/null | awk '{print $2}' | cut -d. -f1-2)"; version_ok PYTHON_VERSION "$actual" "$PYTHON_VERSION" || failures=$((failures+1))
  actual="$(uv --version 2>/dev/null | awk '{print $2}' || true)"; version_ok UV_VERSION "$actual" "$UV_VERSION" || failures=$((failures+1))
  actual="$(buf --version 2>/dev/null || true)"; version_ok BUF_VERSION "$actual" "$BUF_VERSION" || failures=$((failures+1))
  actual="$(gitleaks version 2>/dev/null | head -1 | tr -d '[:space:]')"; version_ok GITLEAKS_VERSION "$actual" "$GITLEAKS_VERSION" || failures=$((failures+1))
  actual="$(golangci-lint version 2>/dev/null | sed -n 's/.*version \([^ ]*\).*/\1/p' | head -1)"; version_ok GOLANGCI_LINT_VERSION "$actual" "$GOLANGCI_LINT_VERSION" || failures=$((failures+1))
  actual="$(gotestsum --version 2>/dev/null | sed -n 's/.*v\([0-9.]*\).*/\1/p')"; version_ok GOTESTSUM_VERSION "$actual" "$GOTESTSUM_VERSION" || failures=$((failures+1))
  if [[ "${IBEX_TEST_MODE:-0}" != 1 ]]; then
    if runtime >/dev/null 2>&1; then
      printf 'PASS  %-20s %s\n' CONTAINER_RUNTIME "$(runtime)"
    else
      echo 'FAIL  CONTAINER_RUNTIME no supported runtime'
      failures=$((failures+1))
    fi
  fi
  if (( failures )); then
    cat >&2 <<'EOF'
check-tools: one or more tools do not match infra/tool-versions.conf.
Remediation: follow the OS-specific installation recipes in web/engineering/TOOLCHAIN.md,
then rerun `make check-tools`. Do not silently upgrade lockfiles or go.mod.
EOF
    return 1
  fi
  echo 'check-tools: all required tools match the manifest'
}

unset_external_otel() {
  [[ "${IBEX_ALLOW_EXTERNAL_OTEL:-0}" == 1 ]] && return 0
  while IFS='=' read -r name _; do
    case "$name" in OTEL_EXPORTER_OTLP_*|OTEL_SERVICE_NAME|OTEL_RESOURCE_ATTRIBUTES|OTEL_*_EXPORTER) unset "$name";; esac
  done < <(env)
}

case "${1:-help}" in
  help)
    printf '%s\n' 'IBEX Harness commands:' \
      '  setup                  Provision dependencies, stacks, migrations, and readiness' \
      '  check-tools            Verify installed versions against infra/tool-versions.conf' \
      '  env-doctor             Diagnose runtime, network, ports, DNS, and OTEL variables' \
      '  stack-init             Wait for services and create required object-store buckets' \
      '  readiness              Run stack-init readiness probes' \
      '  lint-docs              Run markdownlint' '  security-scan          Run gitleaks locally' \
      '  repo-guards            Run repository layout and hygiene guards' '  proto-lint              Run Buf lint' \
      '  proto-breaking         Run Buf breaking checks' '  proto-gen               Generate protobuf stubs' \
      '  proto-test              Run protobuf contract tests' '  test-integration         Run Go integration tests' \
      '  compose-dev-up/down/reset/logs/ps  Manage development stack' \
      '  compose-test-up/down   Manage test stack' '  observability-up/down/smoke  Manage observability' \
      '  db-migrate/down/version/seed  Manage Postgres migrations' \
      '  clickhouse-migrate/down/version  Manage ClickHouse migrations' \
      '  test-embedder/test-memory/test-memory-integration/test-worker/test-worker-integration/test-mcp-memory' \
      '  test-clickhouse-migrate/test-clickhouse-migrate-integration' \
      '  dev-smoke/dev-smoke-live/e2e-wave2b-token-fks/verify-phase15/verify-phase25/e2e-phase25/e2e-smoke-p3-memory/mcp-conformance' ;;
  setup) bash "$ROOT_DIR/infra/scripts/setup.sh" "${2:-}" ;;
  check-tools) check_tools ;;
  env-doctor) bash "$ROOT_DIR/infra/scripts/env-doctor.sh" ;;
  stack-init|readiness) bash "$ROOT_DIR/infra/scripts/stack-init.sh" ;;
  lint-docs)
    cd "$ROOT_DIR"
    markdownlint="$ROOT_DIR/.github/markdownlint/node_modules/.bin/markdownlint-cli2"
    if [[ ! -x "$markdownlint" ]]; then
      echo 'markdownlint-cli2 is not installed; run npm ci --prefix .github/markdownlint --ignore-scripts' >&2
      exit 1
    fi
    "$markdownlint" "**/*.md" "#node_modules"
    ;;
  security-scan) cd "$ROOT_DIR"; require_tool gitleaks 'gitleaks is required for security-scan'; gitleaks detect --source . --config .gitleaks.toml --redact --verbose ;;
  repo-guards) cd "$ROOT_DIR"; bash .github/scripts/check-repo-layout.sh; bash .github/scripts/check-landing-assets.sh; bash .github/scripts/check-static-export.sh; bash .github/scripts/validate-action-pins.sh; python3 infra/scripts/check_roadmap_status.py ;;
  proto-lint) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf lint ;;
  proto-breaking) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf breaking --against "$PROTO_BREAKING_AGAINST" ;;
  proto-gen) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf generate ;;
  proto-test) cd "$ROOT_DIR"; go test ./packages/proto/... ;;
  proto-test-integration) cd "$PROTO_DIR"; buf generate; cd "$ROOT_DIR"; go test -tags=integration ./packages/proto/... ;;
  test-integration) cd "$ROOT_DIR"; unset_external_otel; export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/14}"; go test -tags=integration -race -timeout=120s -p "${GO_TEST_P:-1}" ./... ;;
  compose-dev-up) compose_with_mode dev up -d ;;
  compose-dev-down) compose_with_mode dev down ;;
  compose-dev-reset) compose_with_mode dev down -v; compose_with_mode dev up -d ;;
  compose-dev-logs) compose_with_mode dev logs -f ;;
  compose-dev-ps) compose_with_mode dev ps ;;
  compose-test-up) compose_with_mode test up -d; echo 'compose-test Redis: REDIS_URL=redis://127.0.0.1:6380/14' ;;
  compose-test-down) compose_with_mode test down ;;
  observability-up) compose_with_mode observability up -d ;;
  observability-down) compose_with_mode observability down ;;
  observability-smoke) bash "$ROOT_DIR/infra/scripts/observability-smoke.sh" ;;
  db-migrate) bash "$DB_MIGRATE" up ;;
  db-migrate-down) bash "$DB_MIGRATE" down ;;
  db-version) bash "$DB_MIGRATE" version ;;
  db-seed) bash "$ROOT_DIR/infra/scripts/db-seed.sh" ;;
  db-repair-token-fks) bash "$ROOT_DIR/infra/scripts/db-repair-token-fks.sh" ;;
  clickhouse-migrate) bash "$CH_MIGRATE" up ;;
  clickhouse-migrate-down) bash "$CH_MIGRATE" down ;;
  clickhouse-version) bash "$CH_MIGRATE" version ;;
  test-clickhouse-migrate) bash "$ROOT_DIR/infra/scripts/clickhouse-migrate-test-ci.sh" ;;
  test-clickhouse-migrate-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/clickhouse-migrate-test-integration-ci.sh" ;;
  test-embedder) unset_external_otel; bash "$ROOT_DIR/infra/scripts/embedder-test-ci.sh" ;;
  test-memory) unset_external_otel; bash "$ROOT_DIR/infra/scripts/memory-test-ci.sh" ;;
  test-memory-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/memory-integration-test-ci.sh" ;;
  test-worker) unset_external_otel; bash "$ROOT_DIR/infra/scripts/worker-test-ci.sh" ;;
  test-worker-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/worker-integration-test-ci.sh" ;;
  dev-smoke) bash "$ROOT_DIR/infra/scripts/smoke_local.sh" ;;
  dev-smoke-live) bash "$ROOT_DIR/infra/scripts/smoke_live_openrouter.sh" ;;
  e2e-wave2b-token-fks) bash "$ROOT_DIR/infra/scripts/e2e_compose_dev_wave2b.sh" ;;
  verify-phase15) bash "$ROOT_DIR/infra/scripts/verify_phase15.sh" ;;
  verify-phase25) bash "$ROOT_DIR/infra/scripts/verify_phase25.sh" ;;
  e2e-phase25) bash "$ROOT_DIR/infra/scripts/e2e_phase25.sh" ;;
  e2e-smoke-p3-memory) bash "$ROOT_DIR/infra/scripts/verify_phase3_memory_e2e.sh" ;;
  mcp-conformance) bash "$ROOT_DIR/infra/scripts/mcp-conformance.sh" ;;
  *) echo "unknown command: $1" >&2; echo 'run: make help' >&2; exit 2 ;;
esac
