#!/usr/bin/env bash
# Upload JUnit XML test results to Trunk Flaky Tests.
# Usage: trunk-upload-junit.sh <junit-paths-glob> <variant>
# Requires: TRUNK_API_TOKEN, TRUNK_ORG_URL_SLUG
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <junit-paths-glob> <variant>" >&2
  exit 2
fi

junit_paths="$1"
variant="$2"

if [ -z "${TRUNK_API_TOKEN:-}" ]; then
  echo "TRUNK_API_TOKEN is required" >&2
  exit 1
fi
if [ -z "${TRUNK_ORG_URL_SLUG:-}" ]; then
  echo "TRUNK_ORG_URL_SLUG is required" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cli="${TRUNK_ANALYTICS_CLI:-$repo_root/trunk-analytics-cli}"

if [ ! -x "$cli" ]; then
  sku="${TRUNK_ANALYTICS_CLI_SKU:-trunk-analytics-cli-x86_64-unknown-linux.tar.gz}"
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  curl -fL --retry 3 \
    "https://github.com/trunk-io/analytics-cli/releases/latest/download/${sku}" \
    | tar -xz -C "$tmpdir"
  cli="$tmpdir/trunk-analytics-cli"
  chmod +x "$cli"
fi

"$cli" upload \
  --junit-paths "$junit_paths" \
  --org-url-slug "$TRUNK_ORG_URL_SLUG" \
  --token "$TRUNK_API_TOKEN" \
  --variant "$variant" \
  --repo-root "$repo_root"
