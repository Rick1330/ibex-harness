#!/usr/bin/env bash
# Normalize the version release PR head branch to the IBEX canonical name.
# The upstream engine may recreate release-please--branches--main; we rename it to
# release--branches--main so open release PRs follow automatically.
set -euo pipefail

canonical="${VERSION_RELEASE_BRANCH:-release--branches--main}"
legacy="release-please--branches--main"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"

if [[ "$canonical" == "$legacy" ]]; then
  echo "Canonical branch matches legacy name; nothing to normalize."
  exit 0
fi

legacy_exists="$(gh api "repos/${repo}/git/ref/heads/${legacy}" --jq '.ref // empty' 2>/dev/null || true)"
if [[ -z "$legacy_exists" ]]; then
  echo "Legacy engine branch ${legacy} not present; nothing to normalize."
  exit 0
fi

canonical_exists="$(gh api "repos/${repo}/git/ref/heads/${canonical}" --jq '.ref // empty' 2>/dev/null || true)"
if [[ -n "$canonical_exists" ]]; then
  legacy_sha="$(gh api "repos/${repo}/git/ref/heads/${legacy}" --jq '.object.sha')"
  canonical_sha="$(gh api "repos/${repo}/git/ref/heads/${canonical}" --jq '.object.sha')"
  if [[ "$legacy_sha" == "$canonical_sha" ]]; then
    gh api --method DELETE "repos/${repo}/git/refs/heads/${legacy}" 2>/dev/null || true
    echo "Removed duplicate legacy branch ${legacy} (same SHA as ${canonical})."
    exit 0
  fi
  echo "Both ${legacy} and ${canonical} exist with different SHAs; manual reconcile required."
  exit 1
fi

gh api \
  --method POST \
  "repos/${repo}/branches/${legacy}/rename" \
  -f new_name="${canonical}"

echo "Renamed ${legacy} → ${canonical} (open release PRs retarget automatically)."
