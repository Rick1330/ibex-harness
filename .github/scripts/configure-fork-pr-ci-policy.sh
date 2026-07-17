#!/usr/bin/env bash
# Set GitHub fork PR workflow approval policy (repo admin required).
# See CONTRIBUTING.md § Fork pull request workflows.
set -euo pipefail

REPO="${1:-${GITHUB_REPOSITORY:-}}"
POLICY="${2:-first_time_contributors_new_to_github}"

if [[ -z "$REPO" ]]; then
  echo "Usage: $0 <owner/repo> [approval_policy]"
  echo "Policies: first_time_contributors_new_to_github | first_time_contributors | all_external_contributors"
  exit 1
fi

case "$POLICY" in
  first_time_contributors_new_to_github|first_time_contributors|all_external_contributors) ;;
  *)
    echo "Invalid approval_policy: $POLICY"
    exit 1
    ;;
esac

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI required"
  exit 1
fi

printf '{"approval_policy":"%s"}' "$POLICY" | gh api --method PUT \
  "repos/${REPO}/actions/permissions/fork-pr-contributor-approval" --input -

echo "Fork PR contributor approval policy for ${REPO}:"
gh api "repos/${REPO}/actions/permissions/fork-pr-contributor-approval" --jq .
