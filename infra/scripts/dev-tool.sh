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
V1_COMPOSE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"
# The supported profile uses its own operator-owned .env (0600) under
# infra/compose/v1-single-node so development credentials cannot leak in.
V1_ENV="$ROOT_DIR/infra/compose/v1-single-node/.env"
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
      if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then echo docker
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
    v1) printf '%s\n' -f "$V1_COMPOSE" --env-file "$V1_ENV" ;;
    *) echo "unknown compose stack: $kind" >&2; return 2 ;;
  esac
}

compose_with_mode() {
  local kind="$1"; shift
  local args=()
  if [[ "$kind" == v1 && "${IBEX_NETWORK:-bridge}" == host ]]; then
    echo 'IBEX_NETWORK=host is not supported for v1-single-node: the profile publishes only the edge HTTPS port' >&2
    exit 2
  fi
  if [[ "$kind" == v1 && ! -f "$V1_ENV" ]]; then
    echo "missing $V1_ENV; run: make v1-secrets" >&2
    exit 1
  fi
  if [[ "$kind" == v1 ]]; then
    # The bootstrap PAT bind mount must exist and be operator-owned before the
    # runtime creates it; otherwise a root-owned directory blocks the one-shot.
    local bootstrap_dir="$ROOT_DIR/infra/compose/v1-single-node/bootstrap"
    if [[ ! -d "$bootstrap_dir" ]]; then
      mkdir -p "$bootstrap_dir" && chmod 0700 "$bootstrap_dir"
    fi
  fi
  if [[ "${IBEX_NETWORK:-bridge}" == host ]]; then
    local overlay="$ROOT_DIR/infra/compose/overlays/host/${kind}.yml"
    [[ -f "$overlay" ]] || { echo "missing host-network overlay: $overlay" >&2; exit 1; }
    args+=( -p "ibex-${kind}" -f "$overlay" --env-file "$ROOT_DIR/infra/compose/${kind}/.env.example" )
  elif [[ "${IBEX_NETWORK:-bridge}" != bridge ]]; then
    echo 'IBEX_NETWORK must be bridge or host' >&2; exit 2
  else
    while IFS= read -r arg; do args+=("$arg"); done < <(compose_files "$kind")
  fi
  compose "${args[@]}" "$@"
}

v1_wait_healthy() {
  local attempts="${IBEX_V1_HEALTH_ATTEMPTS:-180}" i ids statuses rt
  local required="postgres redis auth proxy api memory embedder worker context console edge tei"
  rt="$(runtime)"
  for ((i = 1; i <= attempts; i++)); do
    ids="$(compose_with_mode v1 ps -q 2>/dev/null || true)"
    if [[ -n "$ids" ]]; then
      # `ps --format json` differs between Docker Compose and podman-compose,
      # and podman-compose omits health from it entirely. Asking the runtime
      # keeps one code path for both providers.
      # shellcheck disable=SC2086
      statuses="$("$rt" inspect --format '{{.Name}}|{{index .Config.Labels "com.docker.compose.service"}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $ids 2>/dev/null || true)"
      if V1_STATUSES="$statuses" V1_REQUIRED="$required" python3 - <<'PY'
import os
import sys

required = os.environ.get("V1_REQUIRED", "").split()
lines = [line for line in os.environ.get("V1_STATUSES", "").splitlines() if line.strip()]
if not lines:
    sys.exit(1)


def service_name(container: str) -> str:
    parts = container.lstrip("/").split("-")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return parts[-1] if parts else container


seen = {}
for line in lines:
    name, _, rest = line.partition("|")
    label, _, health = rest.partition("|")
    seen[label.strip() or service_name(name)] = health.strip().lower()
if any(seen.get(service) != "healthy" for service in required):
    sys.exit(1)
PY
      then
        echo 'v1-single-node services are healthy'
        return 0
      fi
    fi
    sleep 2
  done
  echo 'v1-single-node services did not all become healthy' >&2
  compose_with_mode v1 ps >&2 || true
  return 1
}

v1_bootstrap_pat() {
  # The PAT is written by the one-shot into a host bind mount, so it outlives
  # the container. Reading the host file avoids `cp` (which streams a tar
  # archive) and any rootful/rootless container-store mismatch.
  local path="$ROOT_DIR/infra/compose/v1-single-node/bootstrap/bootstrap.pat" mode
  if [[ ! -f "$path" ]]; then
    echo "no bootstrap PAT at $path; a first install writes it once during make v1-up" >&2
    return 1
  fi
  mode="$(stat -c %a "$path")"
  if [[ "$mode" != "600" ]]; then
    echo "refusing to print $path: mode $mode, expected 600" >&2
    return 1
  fi
  echo "bootstrap PAT (store it in your secret manager, then delete $path):" >&2
  cat "$path"
}

v1_down() {
  compose_with_mode v1 down "$@" || {
    echo 'v1 down reported a runtime cleanup error; retrying' >&2
    compose_with_mode v1 down "$@"
  }
}

v1_env_value() {
  python3 "$ROOT_DIR/infra/scripts/lib/dotenv.py" "$V1_ENV" "$1"
}

v1_url() {
  local port="${IBEX_EDGE_PORT:-}" ca attempt
  if [[ -z "$port" ]]; then
    port="$(v1_env_value IBEX_EDGE_PORT)"
  fi
  port="${port:-443}"
  ca="$ROOT_DIR/infra/compose/v1-single-node/secrets/ca.crt"
  for _ in $(seq 1 30); do
    if curl -fsS --cacert "$ca" "https://localhost:${port}/_edge/health" >/dev/null 2>&1; then
      printf 'v1-single-node is up: https://localhost:%s\n' "$port"
      printf '%s\n' 'bootstrap PAT (first install only): make v1-bootstrap-pat'
      return 0
    fi
    sleep 2
  done
  echo 'v1-single-node edge did not answer over the profile CA; run: make v1-logs' >&2
  return 1
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
Remediation: follow the OS-specific installation recipes in engineering/TOOLCHAIN.md,
then rerun `make check-tools`. Do not silently upgrade lockfiles or go.mod.
EOF
    return 1
  fi
  echo 'check-tools: all required tools match the manifest'
}

unset_external_otel() {
  [[ "${IBEX_ALLOW_EXTERNAL_OTEL:-0}" == 1 ]] && return 0
  while IFS='=' read -r name _; do
    case "$name" in
      OTEL_*) unset "$name" ;;
      *) : ;;
    esac
  done < <(env)
}

case "${1:-help}" in
  help)
    printf '%s\n' 'IBEX Harness commands:' \
      '  setup                  Provision dependencies, stacks, migrations, and readiness' \
      '  check-tools            Verify installed versions against infra/tool-versions.conf' \
      '  env-doctor             Diagnose runtime, network, ports, DNS, and OTEL variables' \
      '  stack-init [dev|test]  Wait for a stack and create required object-store buckets' \
      '  readiness              Run stack-init readiness probes' \
      '  lint-docs              Run markdownlint' '  security-scan          Run gitleaks locally' \
      '  repo-guards            Run repository layout and hygiene guards' '  proto-lint              Run Buf lint' \
      '  proto-breaking         Run Buf breaking checks' '  proto-gen               Generate protobuf stubs' \
      '  proto-test              Run protobuf contract tests' '  test-integration         Run Go integration tests' \
      '  test-integration-auth   Run AuthService-backed proxy integration tests' \
      '  compose-dev-up/down/reset/logs/ps  Manage development stack' \
      '  compose-test-up/down   Manage test stack' '  observability-up/down/smoke  Manage observability' \
      '  v1-secrets             Generate the v1-single-node .env and file secrets' \
      '  v1-up/down/migrate/logs/ps  Manage the v1-single-node profile (infra/compose/v1-single-node/.env)' \
      '  db-migrate/down/version/seed  Manage Postgres migrations' \
      '  clickhouse-migrate/down/version  Manage ClickHouse migrations' \
      '  test-embedder/test-memory/test-memory-integration/test-worker/test-worker-integration/test-mcp-memory' \
      '  test-clickhouse-migrate/test-clickhouse-migrate-integration' \
      '  dev-smoke/dev-smoke-live/e2e-wave2b-token-fks/verify-phase15/verify-phase25/e2e-phase25/e2e-smoke-p3-memory/mcp-conformance' ;;
  setup) bash "$ROOT_DIR/infra/scripts/setup.sh" "${2:-}" ;;
  check-tools) check_tools ;;
  env-doctor) bash "$ROOT_DIR/infra/scripts/env-doctor.sh" ;;
  stack-init|readiness) bash "$ROOT_DIR/infra/scripts/stack-init.sh" "${2:-dev}" ;;
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
  repo-guards) cd "$ROOT_DIR"; bash .github/scripts/check-repo-layout.sh; bash .github/scripts/check-landing-assets.sh; bash .github/scripts/validate-action-pins.sh ;;
  proto-lint) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf lint ;;
  proto-breaking) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf breaking --against "$PROTO_BREAKING_AGAINST" ;;
  proto-gen) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf generate ;;
  proto-test) cd "$ROOT_DIR"; go test ./packages/proto/... ;;
  proto-test-integration) cd "$PROTO_DIR"; buf generate; cd "$ROOT_DIR"; go test -tags=integration ./packages/proto/... ;;
  test-integration) cd "$ROOT_DIR"; unset_external_otel; export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/14}"; export POSTGRES_TEST_DSN="${POSTGRES_TEST_DSN:-postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable}"; export CLICKHOUSE_TEST_DSN="${CLICKHOUSE_TEST_DSN:-clickhouse://default:ibextest@127.0.0.1:8124/ibex}"; export CLICKHOUSE_TEST_NATIVE_DSN="${CLICKHOUSE_TEST_NATIVE_DSN:-clickhouse://default:ibextest@127.0.0.1:9000?database=ibex}"; export CLICKHOUSE_MIGRATE_DSN="${CLICKHOUSE_MIGRATE_DSN:-${CLICKHOUSE_TEST_NATIVE_DSN}}"; export CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8124}"; export CLICKHOUSE_DB="${CLICKHOUSE_DB:-ibex}"; export CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"; export CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-ibextest}"; export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"; export IBEX_TEST_FAST_ARGON2="${IBEX_TEST_FAST_ARGON2:-1}"; bash "$CH_MIGRATE" up; go test -tags=integration -race -timeout=300s -p "${GO_TEST_P:-1}" -parallel "${GO_TEST_PARALLEL:-1}" ./... ;;
  test-integration-auth) cd "$ROOT_DIR"; unset_external_otel; export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/14}"; export POSTGRES_TEST_DSN="${POSTGRES_TEST_DSN:-postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable}"; export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"; export IBEX_TEST_FAST_ARGON2="${IBEX_TEST_FAST_ARGON2:-1}"; go test -tags=integration -race -timeout=120s -p 1 -parallel "${GO_TEST_PARALLEL:-1}" ./services/auth/... ./services/proxy/... ;;
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
  v1-up) compose_with_mode v1 up -d ;;
  v1-down) compose_with_mode v1 down ;;
  v1-migrate) compose_with_mode v1 run --rm migrate ;;
  v1-logs) compose_with_mode v1 logs -f ;;
  v1-ps) compose_with_mode v1 ps ;;
  v1-secrets) bash "$ROOT_DIR/infra/scripts/gen-v1-secrets.sh" ;;
  v1)
    sub="${2:-}"
    if [[ -n "$sub" ]]; then shift 2; fi
    case "$sub" in
      build) compose_with_mode v1 build "$@" ;;
      up) compose_with_mode v1 up "$@" ;;
      down) v1_down "$@" ;;
      wait) v1_wait_healthy ;;
      url) v1_url ;;
      secrets) bash "$ROOT_DIR/infra/scripts/gen-v1-secrets.sh" ;;
      bootstrap-pat) v1_bootstrap_pat ;;
      migrate) compose_with_mode v1 build migrate && compose_with_mode v1 run --rm migrate "$@" ;;
      logs) compose_with_mode v1 logs -f "$@" ;;
      ps) compose_with_mode v1 ps "$@" ;;
      *) echo "unknown v1 command: ${sub:-<missing>}" >&2; echo 'use: v1-up|v1-down|v1-migrate|v1-logs|v1-ps|v1-bootstrap-pat or v1 build|up|down|wait|url|secrets|bootstrap-pat|migrate|logs|ps' >&2; exit 2 ;;
    esac ;;
  *) echo "unknown command: $1" >&2; echo 'run: make help' >&2; exit 2 ;;
esac
