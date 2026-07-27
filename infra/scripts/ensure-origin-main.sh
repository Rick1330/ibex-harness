#!/usr/bin/env bash
# Ensure refs/remotes/origin/main is present and current for golangci
# issues.new-from-rev (complexity config). Always attempt a refresh so local
# clones do not compare against a stale baseline.
set -euo pipefail

if ! git fetch --no-tags origin main:refs/remotes/origin/main; then
  echo "ensure-origin-main: fetch failed (offline?); using existing origin/main if present" >&2
fi

if ! git rev-parse --verify refs/remotes/origin/main >/dev/null 2>&1; then
  echo "lint-go: refs/remotes/origin/main missing; cannot establish new-from-rev baseline" >&2
  exit 1
fi
