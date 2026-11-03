#!/usr/bin/env bash
# Require Developer Certificate of Origin (Signed-off-by) on every commit in a PR.
# See CONTRIBUTING.md § Developer Certificate of Origin.
set -euo pipefail

BASE_SHA="${GITHUB_EVENT_PULL_REQUEST_BASE_SHA:-}"
HEAD_SHA="${GITHUB_EVENT_PULL_REQUEST_HEAD_SHA:-}"

if [[ -z "$BASE_SHA" || -z "$HEAD_SHA" ]]; then
  echo "DCO check skipped (missing base/head SHA)"
  exit 0
fi

# is_bot_identity <author_name> <author_email>: known automation accounts, or any
# GitHub "[bot]" noreply email.
is_bot_identity() {
  local name="$1" email="$2"
  case "$name" in
    "github-actions[bot]" | "dependabot[bot]" | "ibex-harness-benchmark[bot]" | \
      "greptile-apps[bot]" | "coderabbitai[bot]" | "renovate[bot]")
      [[ "$email" == *@users.noreply.github.com ]] && return 0
      ;;
    *)
      # Not a known automation account; fall through to the [bot] email check.
      ;;
  esac
  [[ "$email" == *+*\[bot\]@users.noreply.github.com ]] && return 0
  return 1
}

# is_github_applied <committer_name> <committer_email>: commits created through
# GitHub itself (web editor, suggested changes, review apps) are committed by
# GitHub <noreply@github.com>. The author owns the content but cannot add a local
# sign-off, so treat those as automation.
is_github_applied() {
  local committer_name="$1" committer_email="$2"
  [[ "$committer_name" == "GitHub" && "$committer_email" == "noreply@github.com" ]] && return 0
  return 1
}

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
  committer_email="$(git log -1 --format='%ce' "$sha")"
  committer_name="$(git log -1 --format='%cn' "$sha")"
  # Bot/automation commits are exempt from sign-off: known automation authors (or
  # any "[bot]" noreply author), and commits applied by GitHub itself. This is
  # keyed off the author/committer identity only, so a co-author trailer cannot
  # bypass the human sign-off requirement.
  if is_bot_identity "$author_name" "$author_email" ||
    is_github_applied "$committer_name" "$committer_email"; then
    continue
  fi
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
