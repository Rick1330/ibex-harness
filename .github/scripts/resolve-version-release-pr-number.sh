#!/usr/bin/env bash
# Resolve the open version release PR number from release-please outputs.
# release-please-action exposes `pr` JSON, not `pr_number`.
set -euo pipefail

pr_number=""
if [ -n "${PR_JSON:-}" ] && [ "$PR_JSON" != "null" ]; then
  pr_number="$(jq -r '.number // empty' <<<"$PR_JSON")"
fi

if [ -z "$pr_number" ] && [ "${PRS_CREATED:-false}" = "true" ]; then
  pr_number="$(gh pr list \
    --repo "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}" \
    --head release-please--branches--main \
    --base main \
    --state open \
    --json number \
    -q '.[0].number // empty' 2>/dev/null || true)"
fi

{
  echo "number=${pr_number}"
  if [ -n "$pr_number" ]; then
    echo "resolved=true"
  else
    echo "resolved=false"
  fi
} >>"$GITHUB_OUTPUT"
