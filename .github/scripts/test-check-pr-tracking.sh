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
  printf '[]'
  exit 0
fi

printf 'stub gh: unhandled invocation: %s\n' "$*" >&2
exit 99
STUB
chmod +x "$WORK/bin/gh"

# The script sleeps between retries; the stub keeps the suite fast without touching the
# script's backoff behaviour.
cat > "$WORK/bin/sleep" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$WORK/bin/sleep"

failures=0

reset_case() {
  rm -rf "$WORK/case"
  mkdir -p "$WORK/case"
  printf 'ok' > "$WORK/case/mode"
  printf '0' > "$WORK/case/transient_attempts"
  printf 'OPEN' > "$WORK/case/state"
  printf '## Problem\n\nTracked.\n\n## Proposed solution\n\nDo the thing.\n\n## Acceptance criteria\n\n- Done.\n\nImplementation PR: #7\n' > "$WORK/case/issue_body"
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
    sed 's/^/  | /' "$WORK/out"
    failures=$((failures + 1))
    return
  fi
  if ! grep -qF "$expected_text" "$WORK/out"; then
    printf 'FAIL %s: output missing %s\n' "$name" "$expected_text"
    sed 's/^/  | /' "$WORK/out"
    failures=$((failures + 1))
    return
  fi
  printf 'ok   %s (exit %s, %s issue read(s))\n' "$name" "$status" "$calls"
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

# 1. Happy path: one read, no retries.
reset_case
expect "linked issue passes" 0 "tracks issue #42"
expect_issue_calls "linked issue passes" 2  # state + body

# 2. A transient failure is retried and the gate passes on recovery.
reset_case
printf 'transient' > "$WORK/case/mode"
printf '2' > "$WORK/case/transient_attempts"
expect "recovers after transient failures" 0 "tracks issue #42"
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

# 7. The bidirectional link is still enforced.
reset_case
printf 'Issue body without a PR reference\n' > "$WORK/case/issue_body"
expect "issue must reference the PR" 1 "must reference PR #7"

if [[ "$failures" -ne 0 ]]; then
  printf '\n%s check-pr-tracking test(s) failed\n' "$failures"
  exit 1
fi
printf '\nAll check-pr-tracking tests passed\n'
