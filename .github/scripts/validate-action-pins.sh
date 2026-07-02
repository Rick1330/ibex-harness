#!/usr/bin/env bash
# Validates GitHub Action pins in workflow files:
# 1) external actions must use full 40-char commit SHAs (not tags)
# 2) each pinned SHA must resolve in the action repository
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail=0

while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  if [[ ! "$ref" =~ ^[a-f0-9]{40}$ ]]; then
    echo "Unpinned or invalid action ref (expected 40-char SHA): ${ref}"
    fail=1
  fi
done < <(
  grep -rhoE 'uses:[[:space:]]*[^[:space:]]+' .github/workflows/ \
    | sed -E 's#^uses:[[:space:]]*##' \
    | grep -v '^\./' \
    | grep -v '/\.github/workflows/' \
    | sed -E 's#^[^@]+@##' \
    | sort -u
)

if ! command -v gh >/dev/null 2>&1; then
  echo "validate-action-pins: gh CLI not installed; SHA existence check skipped"
  exit "$fail"
fi

declare -A seen=()

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ -n "${seen[$line]+x}" ]]; then
    continue
  fi
  seen[$line]=1

  key="${line%%@*}"
  sha="${line##*@}"
  owner="${key%%/*}"
  repo="${key#*/}"

  if ! gh api "repos/${owner}/${repo}/commits/${sha}" --jq .sha >/dev/null 2>&1; then
    echo "Invalid action pin: ${key}@${sha}"
    fail=1
  fi
done < <(
  grep -rhoE '[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[a-f0-9]{40}' .github/workflows/ \
    | sort -u
)

exit "$fail"
