#!/usr/bin/env bash
# Run Go tests via gotestsum and write JUnit XML for Trunk Flaky Tests.
# Usage: go-test-gotestsum.sh <junit-out> -- [go test args...]
# Callers must pass -count=1 (no retries) for accurate flake detection.
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
  echo "usage: $0 <junit-out> -- [go test args...]" >&2
  exit 2
fi

junit_out="$1"
shift 2

mkdir -p "$(dirname "$junit_out")"

if ! command -v gotestsum >/dev/null 2>&1; then
  echo "gotestsum not found; install with: go install gotest.tools/gotestsum@latest" >&2
  exit 127
fi

gotestsum --junitfile="$junit_out" --format standard-verbose -- "$@"
