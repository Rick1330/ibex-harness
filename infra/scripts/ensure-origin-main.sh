#!/usr/bin/env bash
# Ensure refs/remotes/origin/main exists for golangci issues.new-from-rev.
set -euo pipefail

if ! git rev-parse --verify refs/remotes/origin/main >/dev/null 2>&1; then
  echo "Fetching origin/main for golangci new-from-rev baseline..."
  git fetch --no-tags origin main:refs/remotes/origin/main
fi

if ! git rev-parse --verify refs/remotes/origin/main >/dev/null 2>&1; then
  echo "lint-go: refs/remotes/origin/main missing after fetch" >&2
  exit 1
fi
