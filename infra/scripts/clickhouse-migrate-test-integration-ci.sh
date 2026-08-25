#!/usr/bin/env bash
# Run ClickHouse migration integration tests from repo root (requires ClickHouse).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

go test -tags=integration -count=1 ./infra/migrations/clickhouse/...
