#!/usr/bin/env bash
# Validate JUnit XML before uploading to Trunk.
# Usage: trunk-validate-junit.sh <junit-paths-glob>
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <junit-paths-glob>" >&2
  exit 2
fi

junit_paths="$1"
repo_root="$(git rev-parse --show-toplevel)"
cli="${TRUNK_ANALYTICS_CLI:-$repo_root/trunk-analytics-cli}"

if [ ! -x "$cli" ]; then
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os-$arch" in
    Linux-x86_64) sku="trunk-analytics-cli-x86_64-unknown-linux.tar.gz" ;;
    Linux-aarch64|Linux-arm64) sku="trunk-analytics-cli-aarch64-unknown-linux.tar.gz" ;;
    Darwin-arm64) sku="trunk-analytics-cli-aarch64-apple-darwin.tar.gz" ;;
    Darwin-x86_64) sku="trunk-analytics-cli-x86_64-apple-darwin.tar.gz" ;;
    *)
      echo "unsupported platform for auto-download: $os $arch" >&2
      echo "set TRUNK_ANALYTICS_CLI to a downloaded trunk-analytics-cli binary" >&2
      exit 1
      ;;
  esac
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  curl -fL --retry 3 \
    "https://github.com/trunk-io/analytics-cli/releases/latest/download/${sku}" \
    | tar -xz -C "$tmpdir"
  cli="$tmpdir/trunk-analytics-cli"
  chmod +x "$cli"
fi

"$cli" validate --junit-paths "$junit_paths"
