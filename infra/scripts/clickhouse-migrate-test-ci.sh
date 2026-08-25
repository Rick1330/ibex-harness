#!/usr/bin/env bash
# Run ClickHouse migration tests from repo root (paths are repo-relative).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

go test -count=1 ./infra/migrations/clickhouse/...
