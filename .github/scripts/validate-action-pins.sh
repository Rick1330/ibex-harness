#!/usr/bin/env bash
# Validates GitHub Action pins in workflow files:
# 1) external actions must use full 40-char commit SHAs (not tags)
# 2) each pinned SHA must resolve in the action repository (when gh is available)
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
  grep -rhoE '(^|[[:space:]])uses:[[:space:]]*[^#[:space:]]+' .github/workflows/ \
    | sed -E 's#(^|[[:space:]])uses:[[:space:]]*##' \
    | grep -v '^\./' \
    | grep -v '/\.github/workflows/' \
    | sed -E 's#^[^@]+@##' \
    | sed 's/[[:space:]]*$//' \
    | sort -u
)

if ! command -v gh >/dev/null 2>&1; then
  echo "validate-action-pins: gh CLI not installed; SHA existence check skipped"
  exit "$fail"
fi

declare -A seen=()

while IFS= read -r pinned; do
  [[ -z "$pinned" ]] && continue
  if [[ -n "${seen[$pinned]+x}" ]]; then
    continue
  fi
  seen[$pinned]=1

  action="${pinned%@*}"
  sha="${pinned##*@}"
  owner="${action%%/*}"
  repo="${action#*/}"
  repo="${repo%%/*}"

  if [[ -z "$owner" || -z "$repo" || -z "$sha" ]]; then
    echo "Unable to parse action pin: ${pinned}"
    fail=1
    continue
  fi

  if ! gh api "repos/${owner}/${repo}/commits/${sha}" --jq .sha >/dev/null 2>&1; then
    echo "Invalid action pin: ${action}@${sha}"
    fail=1
  fi
done < <(
  grep -rhoE '(^|[[:space:]])uses:[[:space:]]*[^#[:space:]]+@[a-f0-9]{40}' .github/workflows/ \
    | sed -E 's#(^|[[:space:]])uses:[[:space:]]*##' \
    | grep -v '^\./' \
    | grep -v '/\.github/workflows/' \
    | sed 's/[[:space:]]*$//' \
    | sort -u
)

exit "$fail"
