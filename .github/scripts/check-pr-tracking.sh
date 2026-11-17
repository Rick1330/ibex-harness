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
   || "$head_ref" == release--* \
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

# A GitHub API hiccup must not be reported as "the issue does not exist": PR #1104 and
# PR #1108 were both failed by this check while the issue was open and linked, because `gh`
# exited non-zero during an API 502/timeout and the message blamed the data.
#
# Only transient failures are retried (AGENTS.md §8.3): a 5xx, a timeout, or a transport
# error. A "could not resolve" answer is a real answer about the data, so it is reported as
# such immediately rather than retried.
is_transient_gh_failure() {
  case "$1" in
    *"i/o timeout"* | *"timed out"* | *"timeout"* | *"connection reset"* | \
      *"Could not connect"* | *"Connection refused"* | *"EOF"* | *"TLS handshake"* | \
      *"502"* | *"503"* | *"504"* | *"Server Error"* | *"Bad Gateway"* | \
      *"Service Unavailable"* | *"Gateway Timeout"*)
      return 0
      ;;
  esac
  return 1
}

# Exit codes: 0 read, 1 transient failures exhausted, 2 non-transient failure.
# The payload for 2 is the gh error after the "FATAL:" prefix.
read_issue_state() {
  local issue="$1" attempt state error delay
  local error_file
  error_file="$(mktemp)"
  for attempt in 1 2 3; do
    if state="$(gh issue view "$issue" --repo "$REPO" --json state -q .state 2>"$error_file")"; then
      rm -f "$error_file"
      printf '%s' "$state"
      return 0
    fi
    error="$(cat "$error_file")"
    if ! is_transient_gh_failure "$error"; then
      rm -f "$error_file"
      printf 'FATAL:%s' "$error"
      return 2
    fi
    if [[ "$attempt" -lt 3 ]]; then
      # Exponential backoff with jitter, so retries do not line up across runs.
      delay=$((2 ** (attempt - 1)))
      sleep "$((delay + RANDOM % 2))"
    fi
  done
  rm -f "$error_file"
  return 1
}

set +e
issue_state="$(read_issue_state "$issue_num")"
read_status=$?
set -e

case "$read_status" in
  0) ;;
  2)
    echo "Could not read linked issue #$issue_num: ${issue_state#FATAL:}"
    echo "That is not a transient error, so it was not retried."
    exit 1
    ;;
  *)
    echo "Could not read linked issue #$issue_num after 3 attempts."
    echo "GitHub kept returning transient errors (5xx, timeout, or transport)."
    echo "That is not evidence that the issue is missing — re-run this job."
    exit 1
    ;;
esac

if [[ -z "$issue_state" ]]; then
  echo "Linked issue #$issue_num does not exist"
  exit 1
fi

if [[ "$issue_state" == "CLOSED" ]]; then
  echo "Linked issue #$issue_num is already closed; open a new issue or re-open before linking"
  exit 1
fi

# The link may be recorded as a comment, so when the issue body does not already
# name the PR the comments are read too. That read used to swallow its own failure:
# `|| true` turned a rate limit, a 5xx, or a token-scope error into an empty string,
# and the gate then blamed the data with "must reference PR #N" while the reference
# was there (PRs #1239, #1243, #1256). A failed read is a failure of this check, and
# it has to say so.
#
# Two failures have to stay distinct, and both are retried -- COMMENT_ATTEMPTS reads
# in total -- because neither is the data's fault:
#
#   1. the read itself failed -- a rate limit, a 5xx, a dropped connection;
#   2. the read succeeded but the comment had not propagated yet. GitHub does not
#      guarantee read-after-write for a comment created seconds earlier, so a 200
#      can legitimately omit it. Retrying the *comparison* is what covers that;
#      retrying only the read would still report a reference that exists as
#      missing.
#
# One loop drives both, so an attempt is exactly one read plus one comparison:
# three reads when the reference is genuinely absent, one when it is there.
#
# The issue body is checked first and needs no extra API call: an issue whose body
# names the PR passes even when the comments endpoint is unreachable.
COMMENT_ATTEMPTS=3

# Exponential backoff with jitter for the comment retries, in the same shape as the
# issue read: 1 s after the first attempt, 2 s after the second, plus 0-999 ms of
# jitter so concurrent runs do not retry in lockstep. Capped at 4 s, so no single
# retry waits longer than that.
comment_retry_delay() {
  local attempt="$1" delay=1 cap=4
  delay=$((delay * 2 ** (attempt - 1)))
  if ((delay > cap)); then
    delay=$cap
  fi
  printf '%s.%03d' "$delay" "$((RANDOM % 1000))"
}

# Rate limiting is retryable here but not for the issue read above: the GraphQL
# issue query answers "could not resolve" for a rate-limited request, which would
# be read as a missing issue, while the REST comments call fails with a 403/429
# that says what happened.
is_retryable_comment_failure() {
  case "$1" in
    *"rate limit"* | *"Rate limit"* | *"429"*)
      return 0
      ;;
  esac
  is_transient_gh_failure "$1"
}

# Read the issue's comments once. Exit 0 with the joined bodies on success, 1 when
# the failure is retryable, 2 when it is not; a failure prints the gh error so the
# caller can quote it.
read_comments_once() {
  local issue="$1" comments error
  local error_file
  error_file="$(mktemp)"
  if comments="$(gh api "repos/${REPO}/issues/${issue}/comments" \
    --jq '[.[].body] | join("\n")' 2>"$error_file")"; then
    rm -f "$error_file"
    printf '%s' "$comments"
    return 0
  fi
  error="$(cat "$error_file")"
  rm -f "$error_file"
  printf '%s' "$error"
  if is_retryable_comment_failure "$error"; then
    return 1
  fi
  return 2
}

# True when the issue text names the PR in any shape the tracker accepts.
text_names_pr() {
  grep -qiE "(pull/${PR_NUMBER}([^0-9]|$)|PR[[:space:]]*#${PR_NUMBER}([^0-9]|$)|#${PR_NUMBER}([^0-9]|$))" <<<"$1"
}

# Do the issue's comments name the PR? One read and one comparison per attempt.
# The body is checked by the caller, so it is not part of this loop.
# Exit 0 found, 1 absent from every answer that could be read, 2 no answer could be
# read (retryable failures exhausted, payload is the last error), 3 no answer could
# be read and the failure is not retryable (payload is that error).
reference_is_recorded() {
  local issue="$1" attempt output status
  local read_ok=0 fatal=0 last_error=""
  for ((attempt = 1; attempt <= COMMENT_ATTEMPTS; attempt++)); do
    if output="$(read_comments_once "$issue")"; then
      status=0
    else
      status=$?
    fi
    case "$status" in
      0)
        read_ok=1
        if text_names_pr "${output}"; then
          return 0
        fi
        ;;
      2)
        # A non-retryable failure will not clear with time, so the loop stops. A
        # readable answer already collected still outranks it: the reference was
        # genuinely absent from that answer.
        fatal=1
        last_error="$output"
        break
        ;;
      *)
        last_error="$output"
        ;;
    esac
    if [[ "$attempt" -lt "$COMMENT_ATTEMPTS" ]]; then
      sleep "$(comment_retry_delay "$attempt")"
    fi
  done
  if [[ "$read_ok" -eq 1 ]]; then
    return 1
  fi
  printf '%s' "$last_error"
  if [[ "$fatal" -eq 1 ]]; then
    return 3
  fi
  return 2
}

issue_body="$(gh issue view "$issue_num" --repo "$REPO" --json body -q .body | tr -d '\r')"

# The body is authoritative when it names the PR: no comment read, no retry, and no
# chance of an API outage failing an issue that is already correctly linked.
if text_names_pr "$issue_body"; then
  reference_status=0
  reference_error=""
else
  set +e
  reference_error="$(reference_is_recorded "$issue_num")"
  reference_status=$?
  set -e
fi

case "$reference_status" in
  0) ;;
  1)
    echo "Issue #$issue_num must reference PR #$PR_NUMBER (e.g. Implementation PR: #${PR_NUMBER})"
    echo "Add it to the issue body or a comment so the tracker links both ways."
    exit 1
    ;;
  3)
    echo "Could not read the comments on issue #$issue_num: $reference_error"
    echo "That is not a retryable error, so it was not retried."
    echo "This is a read failure, not a missing reference: the link may well be there."
    exit 1
    ;;
  *)
    echo "Could not read the comments on issue #$issue_num after $COMMENT_ATTEMPTS attempts."
    echo "Last GitHub API error: $reference_error"
    echo "This is a read failure, not a missing reference: the link may well be there."
    echo "Re-run this job once the API is reachable."
    exit 1
    ;;
esac

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
