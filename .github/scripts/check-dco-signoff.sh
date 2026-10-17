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
  esac
  [[ "$email" == *+*\[bot\]@users.noreply.github.com ]] && return 0
  return 1
}

# has_bot_coauthor <message>: commit trailer crediting a "[bot]" co-author.
has_bot_coauthor() {
  grep -qiE '^Co-authored-by:.*\[bot\]' <<<"$1"
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
  message="$(git log -1 --format='%B' "$sha")"
  # Bot/automation commits are exempt from sign-off. A commit qualifies when its
  # author is a known automation account, when the author email is a "[bot]"
  # noreply identity, or when it credits a "[bot]" as a co-author (how GitHub
  # code-review apps such as greptile-apps commit suggestions on a user's behalf).
  # Author fields are spoofable, so this stays scoped to explicit bot markers.
  if is_bot_identity "$author_name" "$author_email" || has_bot_coauthor "$message"; then
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
