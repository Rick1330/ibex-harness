#!/usr/bin/env bash
# Regression tests for check-pr-tracking.sh.
#
# The gate used to report a GitHub API outage as "the issue does not exist" (PR #1104 and
# PR #1108 were both failed that way). These tests pin the retry classification, the
# messages, and the exit codes with a stubbed `gh` — no network, no live outage required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$ROOT/check-pr-tracking.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"

cat > "$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
set -uo pipefail
dir="${GH_STUB_DIR:?}"
printf '%s\n' "$*" >> "$dir/calls"
cmd="${1:-}"
sub="${2:-}"

if [[ "$cmd" == "pr" && "$sub" == "view" ]]; then
  printf '%s' '{"author":{"login":"Rick1330"},"headRefName":"feat/x","title":"t","body":"Closes #42\n\n## What and Why\n\n## How\n\n## Testing\n\n## Performance\n\n## Security\n\n## Migrations / Ops\n\n## Docs\n"}'
  exit 0
fi

if [[ "$cmd" == "issue" && "$sub" == "view" ]]; then
  calls=$(cat "$dir/issue_calls" 2>/dev/null || echo 0)
  calls=$((calls + 1))
  printf '%s' "$calls" > "$dir/issue_calls"
  mode=$(cat "$dir/mode")
  if [[ "$mode" == "transient" ]]; then
    limit=$(cat "$dir/transient_attempts")
    if ((calls <= limit)); then
      printf 'Post "https://api.github.com/graphql": dial tcp 140.82.121.6:443: i/o timeout\n' >&2
      exit 1
    fi
  fi
  if [[ "$mode" == "fatal" ]]; then
    printf 'GraphQL: Could not resolve to an Issue with the number of 42.\n' >&2
    exit 1
  fi
  if [[ "$*" == *"--json body"* ]]; then
    cat "$dir/issue_body"
  else
    cat "$dir/state"
  fi
  exit 0
fi

if [[ "$cmd" == "api" ]]; then
  calls=$(cat "$dir/api_calls" 2>/dev/null || echo 0)
  calls=$((calls + 1))
  printf '%s' "$calls" > "$dir/api_calls"
  api_mode=$(cat "$dir/api_mode" 2>/dev/null || echo ok)
  if [[ "$api_mode" == "fatal" ]]; then
    printf 'gh: Resource not accessible by integration (HTTP 403)\n' >&2
    exit 1
  fi
  if [[ "$api_mode" == "down" ]]; then
    printf 'gh: Service Unavailable (HTTP 503)\n' >&2
    exit 1
  fi
  if [[ "$api_mode" == "transient" ]]; then
    limit=$(cat "$dir/api_transient_attempts")
    if ((calls <= limit)); then
      printf 'gh: Server Error (HTTP 502)\n' >&2
      exit 1
    fi
  fi
  if [[ "$api_mode" == "stale_then_fail" ]] && ((calls > 1)); then
    # A 200 that predates the comment, then the endpoint stops answering. The one
    # successful read is stale, so it must not be reported as a missing reference.
    printf 'gh: Service Unavailable (HTTP 503)\n' >&2
    exit 1
  fi
  if [[ "$api_mode" == "stale" ]] && ((calls == 1)); then
    # A 200 that predates the comment: GitHub has not propagated it yet, so the
    # first successful read returns nothing and the second one carries it.
    exit 0
  fi
  # The real call projects the comments through --jq and prints the joined
  # bodies, so the fixture holds the text gh would print, not the raw array.
  cat "$dir/comments" 2>/dev/null || true
  exit 0
fi

printf 'stub gh: unhandled invocation: %s\n' "$*" >&2
exit 99
STUB
chmod +x "$WORK/bin/gh"

# The script sleeps between retries; the stub records the delay it was asked for and
# returns immediately, so the suite stays fast while the backoff numbers stay
# observable.
cat > "$WORK/bin/sleep" <<'STUB'
#!/usr/bin/env bash
set -uo pipefail
if [[ -n "${GH_STUB_DIR:-}" ]]; then
  printf '%s\n' "${1:-}" >> "$GH_STUB_DIR/sleeps"
fi
exit 0
STUB
chmod +x "$WORK/bin/sleep"

failures=0

# The summary line a passing run prints, and the prefix every captured-output
# dump is indented with. Both are asserted on many times, so each is named once.
PASS_SUMMARY='tracks issue #42'
INDENT_OUTPUT='s/^/  | /'

reset_case() {
  rm -rf "$WORK/case"
  mkdir -p "$WORK/case"
  printf 'ok' > "$WORK/case/mode"
  printf 'ok' > "$WORK/case/api_mode"
  printf '0' > "$WORK/case/transient_attempts"
  printf '0' > "$WORK/case/api_transient_attempts"
  printf 'OPEN' > "$WORK/case/state"
  : > "$WORK/case/sleeps"
  printf '## Problem\n\nTracked.\n\n## Proposed solution\n\nDo the thing.\n\n## Acceptance criteria\n\n- Done.\n\nImplementation PR: #7\n' > "$WORK/case/issue_body"
  : > "$WORK/case/comments"
}

# An issue body that satisfies the template checks but names no PR, so the comment
# read is exercised rather than short-circuited by the body.
body_without_reference() {
  printf '## Problem\n\nTracked.\n\n## Proposed solution\n\nDo the thing.\n\n## Acceptance criteria\n\n- Done.\n' \
    > "$WORK/case/issue_body"
}

run() {
  env PATH="$WORK/bin:$PATH" \
    GH_STUB_DIR="$WORK/case" \
    GITHUB_REPOSITORY="Rick1330/ibex-harness" \
    GITHUB_EVENT_PULL_REQUEST_NUMBER="7" \
    bash "$SCRIPT" > "$WORK/out" 2>&1
}

expect() {
  local name="$1" expected_status="$2" expected_text="$3"
  local status=0
  run || status=$?
  local calls
  calls="$(cat "$WORK/case/issue_calls" 2>/dev/null || echo 0)"
  if [[ "$status" -ne "$expected_status" ]]; then
    printf 'FAIL %s: exit %s, expected %s\n' "$name" "$status" "$expected_status"
    sed "$INDENT_OUTPUT" "$WORK/out"
    failures=$((failures + 1))
    return
  fi
  if ! grep -qF "$expected_text" "$WORK/out"; then
    printf 'FAIL %s: output missing %s\n' "$name" "$expected_text"
    sed "$INDENT_OUTPUT" "$WORK/out"
    failures=$((failures + 1))
    return
  fi
  printf 'ok   %s (exit %s, %s issue read(s), %s comment read(s))\n' \
    "$name" "$status" "$calls" "$(cat "$WORK/case/api_calls" 2>/dev/null || echo 0)"
}

expect_issue_calls() {
  local name="$1" expected="$2"
  local calls
  calls="$(cat "$WORK/case/issue_calls" 2>/dev/null || echo 0)"
  if [[ "$calls" -ne "$expected" ]]; then
    printf 'FAIL %s: %s issue read(s), expected %s\n' "$name" "$calls" "$expected"
    failures=$((failures + 1))
  fi
}

expect_api_calls() {
  local name="$1" expected="$2"
  local calls
  calls="$(cat "$WORK/case/api_calls" 2>/dev/null || echo 0)"
  if [[ "$calls" -ne "$expected" ]]; then
    printf 'FAIL %s: %s comment read(s), expected %s\n' "$name" "$calls" "$expected"
    failures=$((failures + 1))
  fi
}

# Assert the comment-retry backoff recorded by the sleep stub: exactly two sleeps,
# the first in [1,2) seconds and the second in [2,3).
expect_comment_backoff() {
  local name="$1"
  local delays=()
  if [[ -f "$WORK/case/sleeps" ]]; then
    mapfile -t delays < "$WORK/case/sleeps"
  fi
  if [[ "${#delays[@]}" -ne 2 ]]; then
    printf 'FAIL %s: %s sleep(s), expected 2\n' "$name" "${#delays[@]}"
    failures=$((failures + 1))
    return
  fi
  if ! awk -v v="${delays[0]}" 'BEGIN { exit !(v >= 1 && v < 2) }'; then
    printf 'FAIL %s: first delay %s not in [1,2)\n' "$name" "${delays[0]}"
    failures=$((failures + 1))
  fi
  if ! awk -v v="${delays[1]}" 'BEGIN { exit !(v >= 2 && v < 3) }'; then
    printf 'FAIL %s: second delay %s not in [2,3)\n' "$name" "${delays[1]}"
    failures=$((failures + 1))
  fi
}

# 1. Happy path: one read, no retries.
reset_case
expect "linked issue passes" 0 "$PASS_SUMMARY"
expect_issue_calls "linked issue passes" 2  # state + body
# The body names the PR, so the comments are never read.
expect_api_calls "linked issue passes" 0

# 1a. The body names the PR and the comments endpoint is unreadable: the body-only
# pass must not depend on the comment read at all.
reset_case
printf 'fatal' > "$WORK/case/api_mode"
expect "body-only link passes without reading comments" 0 "$PASS_SUMMARY"
expect_api_calls "body-only link passes without reading comments" 0

# 2. A transient failure is retried and the gate passes on recovery.
reset_case
printf 'transient' > "$WORK/case/mode"
printf '2' > "$WORK/case/transient_attempts"
expect "recovers after transient failures" 0 "$PASS_SUMMARY"
expect_issue_calls "recovers after transient failures" 4  # 3 state reads + body

# 3. Three transient failures: fail, but say what happened.
reset_case
printf 'transient' > "$WORK/case/mode"
printf '3' > "$WORK/case/transient_attempts"
expect "exhausted retries report an API failure" 1 "GitHub kept returning transient errors"
expect_issue_calls "exhausted retries report an API failure" 3

# 4. A non-transient answer is never retried and is reported verbatim.
reset_case
printf 'fatal' > "$WORK/case/mode"
expect "non-transient error is not retried" 1 "not a transient error"
expect_issue_calls "non-transient error is not retried" 1

# 5. A genuinely missing issue keeps its own message.
reset_case
printf '' > "$WORK/case/state"
expect "missing issue is reported as missing" 1 "does not exist"

# 6. A closed issue keeps its own message.
reset_case
printf 'CLOSED' > "$WORK/case/state"
expect "closed issue is rejected" 1 "already closed"

# 7. The bidirectional link is still enforced when the comments read succeeds and
# neither the body nor the comments name the PR. The comparison is retried, so a
# genuinely missing reference costs three reads before it is reported.
reset_case
printf 'Issue body without a PR reference\n' > "$WORK/case/issue_body"
printf 'A comment that names no pull request either.\n' > "$WORK/case/comments"
expect "issue must reference the PR" 1 "must reference PR #7"
expect_api_calls "issue must reference the PR" 3
expect_comment_backoff "issue must reference the PR"

# 8. The reference lives only in a comment: the joined comment text is read, so the
# gate passes on the first comparison. This is the shape that was reported as
# missing on PRs #1239, #1243, and #1256.
reset_case
body_without_reference
printf 'Implementation PR: #7\n' > "$WORK/case/comments"
expect "reference in a comment passes" 0 "$PASS_SUMMARY"
expect_api_calls "reference in a comment passes" 1

# 8a. Read-after-write: the first read is a 200 that predates the comment, so the
# reference is absent from a readable answer. The second comparison finds it and
# the gate passes -- retrying the read alone would still have reported it missing.
reset_case
body_without_reference
printf 'stale' > "$WORK/case/api_mode"
printf 'Implementation PR: #7\n' > "$WORK/case/comments"
expect "reference appears on the second read" 0 "$PASS_SUMMARY"
expect_api_calls "reference appears on the second read" 2

# 9. A non-retryable comment read failure must not be reported as a missing
# reference: the link may be there and the check simply could not see it.
reset_case
body_without_reference
printf 'fatal' > "$WORK/case/api_mode"
expect "unreadable comments are reported as unreadable" 1 "Could not read the comments on issue #42"
expect_api_calls "unreadable comments are reported as unreadable" 1
if grep -qF "must reference PR #7" "$WORK/out"; then
  printf 'FAIL unreadable comments are reported as unreadable: blamed the data\n'
  sed "$INDENT_OUTPUT" "$WORK/out"
  failures=$((failures + 1))
fi

# 10. A transient comment read failure is retried and passes on recovery.
reset_case
body_without_reference
printf 'transient' > "$WORK/case/api_mode"
printf '2' > "$WORK/case/api_transient_attempts"
printf 'Implementation PR: #7\n' > "$WORK/case/comments"
expect "comment read recovers after transient failures" 0 "$PASS_SUMMARY"
expect_api_calls "comment read recovers after transient failures" 3

# 11. Three transient comment read failures exhaust the retries and name the API
# failure, still without blaming the data.
reset_case
body_without_reference
printf 'down' > "$WORK/case/api_mode"
expect "exhausted comment retries name the API failure" 1 "Could not read the comments on issue #42 after 3 attempts"
expect_api_calls "exhausted comment retries name the API failure" 3
if ! grep -qF "HTTP 503" "$WORK/out"; then
  printf 'FAIL exhausted comment retries name the API failure: output missing the API error\n'
  sed "$INDENT_OUTPUT" "$WORK/out"
  failures=$((failures + 1))
fi
if grep -qF "must reference PR #7" "$WORK/out"; then
  printf 'FAIL exhausted comment retries name the API failure: blamed the data\n'
  sed "$INDENT_OUTPUT" "$WORK/out"
  failures=$((failures + 1))
fi

# 12. A readable answer that predates the comment must not outrank the failures
# that follow it. The first read is a 200 without the reference; the rest fail.
# Reporting "must reference PR #7" here would tell the author to add a link that
# may already be there, and would discard the GitHub error that stopped the
# check. The read failure is the finding.
reset_case
body_without_reference
printf 'stale_then_fail' > "$WORK/case/api_mode"
printf 'A comment that names no pull request either.\n' > "$WORK/case/comments"
expect "a stale readable answer is outranked by later read failures" 1 \
  "Could not read the comments on issue #42 after 3 attempts"
expect_api_calls "a stale readable answer is outranked by later read failures" 3
if ! grep -qF "HTTP 503" "$WORK/out"; then
  printf 'FAIL a stale readable answer is outranked by later read failures: output missing the API error\n'
  sed "$INDENT_OUTPUT" "$WORK/out"
  failures=$((failures + 1))
fi
if grep -qF "must reference PR #7" "$WORK/out"; then
  printf 'FAIL a stale readable answer is outranked by later read failures: blamed the data\n'
  sed "$INDENT_OUTPUT" "$WORK/out"
  failures=$((failures + 1))
fi

if [[ "$failures" -ne 0 ]]; then
  printf '\n%s check-pr-tracking test(s) failed\n' "$failures"
  exit 1
fi
printf '\nAll check-pr-tracking tests passed\n'
