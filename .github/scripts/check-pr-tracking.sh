#!/usr/bin/env bash
# Require tracked issues on pull requests: close keyword, template sections, bidirectional link.
# See CONTRIBUTING.md § Issue-tracked pull requests.
set -euo pipefail

PR_NUMBER="${GITHUB_EVENT_PULL_REQUEST_NUMBER:-${1:-}}"
REPO="${GITHUB_REPOSITORY:-}"

if [[ -z "$PR_NUMBER" || -z "$REPO" ]]; then
  echo "PR tracking check skipped (not a pull_request event)"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI required for PR tracking check"
  exit 1
fi

pr_json="$(gh pr view "$PR_NUMBER" --repo "$REPO" --json author,headRefName,body,title)"
author_login="$(echo "$pr_json" | jq -r '.author.login')"
head_ref="$(echo "$pr_json" | jq -r '.headRefName')"
body="$(echo "$pr_json" | jq -r '.body // ""' | tr -d '\r')"

if [[ "$author_login" == "dependabot[bot]" \
   || "$author_login" == "github-actions[bot]" \
   || "$author_login" == "ibex-harness-benchmark[bot]" \
   || "$author_login" == "app/ibex-harness-benchmark" ]]; then
  echo "PR tracking check skipped for bot author: $author_login"
  exit 0
fi

if [[ "$head_ref" == release-please--* \
   || "$head_ref" == dependabot/* \
   || "$head_ref" == chore/bench-data-* ]]; then
  echo "PR tracking check skipped for automation branch: $head_ref"
  exit 0
fi

if [[ -z "$body" ]]; then
  echo "PR #$PR_NUMBER has an empty body; fill .github/pull_request_template.md"
  exit 1
fi

if ! grep -qiE '(closes|fixes|resolves)[[:space:]]+#[0-9]+' <<<"$body"; then
  echo "PR #$PR_NUMBER must include a GitHub close keyword in the body, e.g. Closes #123"
  echo "See CONTRIBUTING.md (Issue-tracked pull requests)."
  exit 1
fi

issue_num="$(grep -oiE '(closes|fixes|resolves)[[:space:]]+#[0-9]+' <<<"$body" | head -1 | grep -oE '[0-9]+')"
if [[ -z "$issue_num" ]]; then
  echo "Could not parse issue number from close keyword"
  exit 1
fi

if ! gh issue view "$issue_num" --repo "$REPO" --json state -q .state >/dev/null 2>&1; then
  echo "Linked issue #$issue_num does not exist"
  exit 1
fi

issue_state="$(gh issue view "$issue_num" --repo "$REPO" --json state -q .state)"
if [[ "$issue_state" == "CLOSED" ]]; then
  echo "Linked issue #$issue_num is already closed; open a new issue or re-open before linking"
  exit 1
fi

issue_body="$(gh issue view "$issue_num" --repo "$REPO" --json body -q .body | tr -d '\r')"
issue_comments="$(gh api "repos/${REPO}/issues/${issue_num}/comments" --jq '[.[].body] | join("\n")' 2>/dev/null || true)"
issue_text="${issue_body}"$'\n'"${issue_comments}"

if ! grep -qiE "(pull/${PR_NUMBER}([^0-9]|$)|PR[[:space:]]*#${PR_NUMBER}([^0-9]|$)|#${PR_NUMBER}([^0-9]|$))" <<<"$issue_text"; then
  echo "Issue #$issue_num must reference PR #$PR_NUMBER (e.g. Implementation PR: #${PR_NUMBER})"
  echo "Add it to the issue body or a comment so the tracker links both ways."
  exit 1
fi

if grep -qiE '^##[[:space:]]+Problem' <<<"$issue_body"; then
  for section in 'Proposed solution' 'Acceptance criteria'; do
    if ! grep -qiE "^##[[:space:]]+${section}" <<<"$issue_body"; then
      echo "Issue #$issue_num missing ## ${section} (use feature_request template)"
      exit 1
    fi
  done
elif grep -qiE '^##[[:space:]]+Summary' <<<"$issue_body"; then
  for section in 'Expected behavior' 'Actual behavior' 'Reproduction steps'; do
    if ! grep -qiE "^##[[:space:]]+${section}" <<<"$issue_body"; then
      echo "Issue #$issue_num missing ## ${section} (use bug_report template)"
      exit 1
    fi
  done
else
  echo "Issue #$issue_num must use a repo issue template (## Problem or ## Summary)"
  exit 1
fi

required_pr_sections=(
  'What and Why'
  'How'
  'Testing'
  'Performance'
  'Security'
  'Migrations / Ops'
  'Docs'
)
for section in "${required_pr_sections[@]}"; do
  if ! grep -qiE "^##[[:space:]]+${section}" <<<"$body"; then
    echo "PR #$PR_NUMBER missing required section: ## ${section}"
    echo "Use .github/pull_request_template.md"
    exit 1
  fi
done

echo "PR #$PR_NUMBER tracks issue #$issue_num (close keyword, templates, bidirectional link)"
