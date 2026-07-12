#!/usr/bin/env bash
# Apply .github/branch-protection-main.json to the main branch (Scorecard Branch-Protection check).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO="${GITHUB_REPOSITORY:-Rick1330/ibex-harness}"

echo "Applying branch protection to ${REPO}@main from ${ROOT}/.github/branch-protection-main.json"
gh api --method PUT "repos/${REPO}/branches/main/protection" \
  --input "${ROOT}/.github/branch-protection-main.json"
echo "Done."
