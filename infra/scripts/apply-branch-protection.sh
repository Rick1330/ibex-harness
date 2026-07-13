#!/usr/bin/env bash
# Apply .github/branch-protection-main.json to the main branch (Scorecard Branch-Protection check).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
  REPO="${GITHUB_REPOSITORY}"
elif command -v gh >/dev/null 2>&1; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
else
  echo "GITHUB_REPOSITORY is unset and gh is unavailable; refusing to guess repository" >&2
  exit 1
fi

if ! [[ "${REPO}" =~ ^[^/[:space:]]+/[^/[:space:]]+$ ]]; then
  echo "invalid repository slug: ${REPO}" >&2
  exit 1
fi

echo "Applying branch protection to ${REPO}@main from ${ROOT}/.github/branch-protection-main.json"
gh api --method PUT "repos/${REPO}/branches/main/protection" \
  --input "${ROOT}/.github/branch-protection-main.json"
echo "Done."
