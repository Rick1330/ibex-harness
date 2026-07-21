#!/usr/bin/env bash
# Install a Go CLI from .github/tools/go.mod + go.sum (Sonar: lock-file enforced).
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "usage: install-go-ci-tool.sh <module/path> [<module/path> ...]" >&2
  exit 1
fi

tools_dir="$(cd "$(dirname "$0")/../tools" && pwd)"
install_dir="${GOBIN:-${RUNNER_TEMP:-/tmp}/go-ci-bin}"
mkdir -p "$install_dir"
export GOBIN="$install_dir"
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$install_dir" >> "$GITHUB_PATH"
else
  export PATH="$install_dir:$PATH"
fi

(
  cd "$tools_dir"
  for pkg in "$@"; do
    go install "$pkg"
  done
)
