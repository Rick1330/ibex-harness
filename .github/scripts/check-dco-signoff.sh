#!/usr/bin/env bash
# Require Developer Certificate of Origin (Signed-off-by) on every commit in a PR.
# See CONTRIBUTING.md § Developer Certificate of Origin.
set -euo pipefail

BASE_SHA="${1:-${GITHUB_EVENT_PULL_REQUEST_BASE_SHA:-}}"
HEAD_SHA="${2:-${GITHUB_EVENT_PULL_REQUEST_HEAD_SHA:-}}"

if [[ -z "$BASE_SHA" || -z "$HEAD_SHA" ]]; then
  echo "DCO check skipped (missing base/head SHA)"
  exit 0
fi

missing=0
while IFS= read -r sha; do
  [[ -z "$sha" ]] && continue
  # GitHub "Update branch" merge commits are not contributor work; skip DCO on them.
  parent_count="$(git rev-list --parents -n 1 "$sha" | awk '{print NF - 1}')"
  if [[ "$parent_count" -gt 1 ]]; then
    continue
  fi
  author_email="$(git log -1 --format='%ae' "$sha")"
  author_name="$(git log -1 --format='%an' "$sha")"
  # Automation commits (release bot, dependabot, benchmark publisher) are exempt.
  case "$author_email" in
    *@users.noreply.github.com)
      if [[ "$author_name" == "github-actions[bot]" \
         || "$author_name" == "dependabot[bot]" \
         || "$author_name" == "ibex-harness-benchmark[bot]" ]]; then
        continue
      fi
      ;;
    *) ;;
  esac
  if ! git log -1 --format='%B' "$sha" | grep -qiE '^Signed-off-by:'; then
    echo "Missing Signed-off-by on commit ${sha:0:7} ($author_name <$author_email>)"
    missing=1
  fi
done < <(git rev-list "${BASE_SHA}..${HEAD_SHA}")

if [[ "$missing" -ne 0 ]]; then
  echo ""
  echo "Add Signed-off-by to each commit message, or amend/squash with sign-off."
  echo "See CONTRIBUTING.md (Developer Certificate of Origin)."
  exit 1
fi

echo "DCO Signed-off-by present on all non-bot PR commits"
