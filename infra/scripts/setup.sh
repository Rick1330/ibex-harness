#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == --check ]]; then
  exec bash "$ROOT_DIR/infra/scripts/dev-tool.sh" check-tools
fi

bash "$ROOT_DIR/infra/scripts/dev-tool.sh" check-tools
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" env-doctor

if ! command -v pnpm >/dev/null 2>&1; then
  echo 'setup: pnpm is missing; install it using the OS recipe in web/engineering/TOOLCHAIN.md' >&2
  exit 1
fi
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter web run postinstall

for sync in infra/scripts/*-uv-sync.sh; do
  [[ -x "$sync" ]] || chmod +x "$sync"
  bash "$sync"
done

bash "$ROOT_DIR/infra/scripts/dev-tool.sh" proto-gen
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" compose-dev-up
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" compose-test-up
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" db-migrate
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" clickhouse-migrate
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" stack-init
bash "$ROOT_DIR/infra/scripts/dev-tool.sh" readiness

if ! git diff --quiet -- go.sum; then
  echo 'setup: refusing to leave go.sum modified; restoring it' >&2
  git checkout -- go.sum
  exit 1
fi

echo 'setup: complete'
