#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_MIGRATE="$ROOT_DIR/infra/scripts/db-migrate.sh"
PROTO_DIR="$ROOT_DIR/packages/proto"
DEV_COMPOSE="$ROOT_DIR/infra/compose/dev/docker-compose.yml"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"
TEST_COMPOSE="$ROOT_DIR/infra/compose/test/docker-compose.yml"
PROTO_BREAKING_AGAINST="${PROTO_BREAKING_AGAINST:-https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto}"

if command -v cygpath >/dev/null 2>&1 && [[ -n "${LOCALAPPDATA:-}" ]]; then
  export PATH="$(cygpath -u "$LOCALAPPDATA")/Microsoft/WinGet/Links:$PATH"
fi

require_tool() {
  local tool="$1"
  local message="$2"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$message"
    exit 1
  fi
}

case "${1:-help}" in
  help)
    printf "%s\n" \
      "IBEX Harness commands:" \
      "  help                   Show available commands" \
      "  lint-docs              Run markdownlint using the repo configuration" \
      "  security-scan          Run gitleaks locally if installed" \
      "  repo-guards            Run repository layout and hygiene guards" \
      "  proto-lint             Run Buf lint for protobuf contracts" \
      "  proto-breaking         Run Buf breaking checks against main" \
      "  proto-gen              Generate protobuf stubs locally (not committed)" \
      "  proto-test             Run protobuf contract unit tests" \
      "  proto-test-integration Run protobuf contract integration tests (requires buf)" \
      "  compose-dev-up         Start local development dependencies" \
      "  compose-dev-down       Stop local development dependencies" \
      "  compose-dev-logs       Tail local development dependency logs" \
      "  compose-dev-ps         Show local development dependency status" \
      "  compose-test-up        Start minimal test dependencies" \
      "  compose-test-down      Stop minimal test dependencies" \
      "  db-migrate             Apply all pending Postgres migrations" \
      "  db-migrate-down        Roll back one Postgres migration step" \
      "  db-version             Show current Postgres migration version"
    ;;
  lint-docs)
    cd "$ROOT_DIR"
    npx --yes markdownlint-cli2 "**/*.md" "#node_modules"
    ;;
  security-scan)
    cd "$ROOT_DIR"
    # Local security scan is optional; CI still runs a full scan.
    if ! command -v gitleaks >/dev/null 2>&1; then
      echo "gitleaks not installed; skipping local secret scan (CI still runs gitleaks)."
      exit 0
    fi
    gitleaks detect --source . --config .gitleaks.toml --redact --verbose
    ;;
  repo-guards)
    cd "$ROOT_DIR"
    bash .github/scripts/check-repo-layout.sh
    ;;
  proto-lint)
    require_tool buf "buf is required for proto-lint. Install Buf CLI: https://buf.build/docs/installation"
    cd "$PROTO_DIR"
    buf lint
    ;;
  proto-breaking)
    require_tool buf "buf is required for proto-breaking. Install Buf CLI: https://buf.build/docs/installation"
    cd "$PROTO_DIR"
    buf breaking --against "$PROTO_BREAKING_AGAINST"
    ;;
  proto-gen)
    require_tool buf "buf is required for proto-gen. Install Buf CLI: https://buf.build/docs/installation"
    cd "$PROTO_DIR"
    buf generate
    echo "proto-gen: output under packages/proto/gen/ (gitignored; do not commit)"
    ;;
  proto-test)
    cd "$ROOT_DIR"
    go test ./packages/proto/...
    ;;
  proto-test-integration)
    require_tool buf "buf is required for proto-test-integration. Install Buf CLI: https://buf.build/docs/installation"
    cd "$PROTO_DIR"
    buf generate
    cd "$ROOT_DIR"
    go test -tags=integration ./packages/proto/...
    ;;
  compose-dev-up)
    require_tool docker "docker is required for compose-dev-up."
    docker compose -f "$DEV_COMPOSE" --env-file "$DEV_ENV" up -d
    ;;
  compose-dev-down)
    require_tool docker "docker is required for compose-dev-down."
    docker compose -f "$DEV_COMPOSE" --env-file "$DEV_ENV" down
    ;;
  compose-dev-logs)
    require_tool docker "docker is required for compose-dev-logs."
    docker compose -f "$DEV_COMPOSE" --env-file "$DEV_ENV" logs -f
    ;;
  compose-dev-ps)
    require_tool docker "docker is required for compose-dev-ps."
    docker compose -f "$DEV_COMPOSE" --env-file "$DEV_ENV" ps
    ;;
  compose-test-up)
    require_tool docker "docker is required for compose-test-up."
    docker compose -f "$TEST_COMPOSE" up -d
    ;;
  compose-test-down)
    require_tool docker "docker is required for compose-test-down."
    docker compose -f "$TEST_COMPOSE" down
    ;;
  db-migrate)
    bash "$DB_MIGRATE" up
    ;;
  db-migrate-down)
    bash "$DB_MIGRATE" down
    ;;
  db-version)
    bash "$DB_MIGRATE" version
    ;;
  *)
    echo "unknown command: $1"
    echo "run: make help"
    exit 2
    ;;
esac
