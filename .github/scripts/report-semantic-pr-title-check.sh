#!/usr/bin/env bash
# Post the merge-gate semantic-pr-title check on a release PR head commit.
# Required because PRs opened/updated by GITHUB_TOKEN do not trigger pull_request_target workflows.
# Usage: report-semantic-pr-title-check.sh <pr_number>
set -euo pipefail

pr_number="${1:?pr_number required}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"
server="${GITHUB_SERVER_URL:-https://github.com}"

pr_json="$(gh pr view "$pr_number" --repo "$repo" --json title,headRefOid)"
title="$(jq -r '.title' <<<"$pr_json")"
head_sha="$(jq -r '.headRefOid' <<<"$pr_json")"

conclusion="success"
summary="PR title satisfies the semantic title policy."

semantic_pattern='^(feat|fix|chore|docs|test|perf|refactor|ci|build)(\([^)]+\))?: .+'
uppercase_subject_pattern='^[A-Z]'

if [[ ! "$title" =~ $semantic_pattern ]]; then
  conclusion="failure"
  summary="PR title must use a conventional type prefix (feat, fix, chore, docs, test, perf, refactor, ci, build)."
else
  subject="${title#*: }"
  if [[ "$subject" =~ $uppercase_subject_pattern ]]; then
    conclusion="failure"
    summary="PR title subject must not start with an uppercase letter."
  fi
fi

payload="$(jq -n \
  --arg name "semantic-pr-title" \
  --arg head_sha "$head_sha" \
  --arg conclusion "$conclusion" \
  --arg summary "$summary" \
  --arg details_url "${server}/${repo}/pull/${pr_number}" \
  '{
    name: $name,
    head_sha: $head_sha,
    status: "completed",
    conclusion: $conclusion,
    details_url: $details_url,
    output: {title: $name, summary: $summary}
  }')"

gh api "repos/${repo}/check-runs" --method POST --input - <<<"$payload"

echo "::notice title=semantic-pr-title check posted::PR #${pr_number} (${conclusion})"
