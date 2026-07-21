#!/usr/bin/env bash
# Install a Go CLI from .github/tools/go.mod + go.sum (Sonar: lock-file enforced).
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: install-go-ci-tool.sh <module/path> [<module/path> ...]" >&2
  exit 1
fi

tools_dir="$(cd "$(dirname "$0")/../tools" && pwd)"
(
  cd "$tools_dir"
  for pkg in "$@"; do
    go install "$pkg"
  done
)
