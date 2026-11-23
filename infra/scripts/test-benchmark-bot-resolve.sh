#!/usr/bin/env bash
# test-benchmark-bot-resolve.sh — regression tests for the release-resolution
# policy of the setup-benchmark-bot action
# (.github/actions/setup-benchmark-bot/resolve-release.sh) and for the action step
# that consumes it.
#
# Seven decisions are guarded here, because each one is a way for CI to run a bot
# that is not the bot the pin names:
#
#   1. No release tag configured and no release published for the pin: a source
#      build is allowed. An unreleased development commit legitimately has no
#      asset.
#   2. A configured tag that names the pin, with a release whose binary and
#      published checksum both match the digest: the release binary is used, and
#      it is the one the configured tag was asked for.
#   3. A configured tag that does not name the pin: the step fails and names the
#      disagreement. It used to print "ignoring" and fall through to tags derived
#      from the SHA, so a tag left behind on one release passed setup as long as
#      a derived tag happened to verify - a claim that the SHA, tag and digest
#      agree, checked against none of them.
#   4. A configured tag that names the pin but verifies nothing (the release is
#      missing, or the asset's digest is not the pin's): the step fails. It must
#      not cargo-build, because an explicit tag is a claim that a verified release
#      exists.
#   5. No configured tag and nothing verifies - a digest mismatch or a published
#      checksum that disagrees: a source build is still allowed, and both derived
#      tag spellings (`bot-<7>` then `v<7>`) are tried first.
#   6. A candidate whose download fails does not stop the next spelling from
#      being used: the loop advances from a failed first tag to a succeeding
#      second one, and the release that is selected is the second tag's.
#   7. A release that verifies by digest but whose binary lacks the subcommand the
#      caller requires is rejected, and the loop moves on. All five benchmark
#      workflows pass require-subcommand, so this is the path production takes: a
#      stale pin whose release predates the subcommand must not be accepted. With
#      no configured tag the build fallback still applies; with one the step
#      fails, because the configured tag claims a usable release exists.
#
# No network. The action's `run:` block is executed as extracted from the YAML,
# with a stub `gh` first on PATH that answers from the environment, and with the
# real `sha256sum` against a fixture binary whose digest is written into a private
# copy of the action's pin file. Only `gh` is faked, so the verification the
# tests rely on is the verification the action performs.
#
# Run directly: bash infra/scripts/test-benchmark-bot-resolve.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTION_DIR="$ROOT/.github/actions/setup-benchmark-bot"
ACTION="$ACTION_DIR/action.yml"
RESOLVER="$ACTION_DIR/resolve-release.sh"

# A synthetic pin. The resolver reads only the first seven characters, so the test
# does not depend on the live BENCHMARK_BOT_SHA and does not break when the pin
# rotates.
PIN="0123456789abcdef0123456789abcdef01234567"
PIN_SHORT="${PIN:0:7}"
BOT_TAG="bot-${PIN_SHORT}"
V_TAG="v${PIN_SHORT}"

PASSED=0
fail=0
pass() {
  PASSED=$((PASSED + 1))
  printf 'PASS: %s\n' "$*"
}
bad() {
  printf 'FAIL: %s\n' "$*" >&2
  fail=1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ibex-benchmark-bot-resolve.XXXXXX")"
cleanup() {
  chmod -R u+rwX "$WORK" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# --- assertion helpers -----------------------------------------------------

expect_status() { # <label> <dir> <expected>
  local actual
  actual="$(cat "$2/status")"
  if [[ "$actual" == "$3" ]]; then
    pass "$1 (exit $3)"
  else
    bad "$1: expected exit $3, got $actual (output in ${2#"$WORK"/}/out.log)"
  fi
}

expect_field() { # <label> <dir> <field> <expected>
  local actual
  actual="$(sed -n "s/^$3=//p" "$2/github-output" 2>/dev/null | tail -n1)"
  if [[ "$actual" == "$4" ]]; then
    pass "$1 ($3=$4)"
  else
    bad "$1: expected $3='$4', got '${actual}'"
  fi
}

expect_log() { # <label> <dir> <text>
  if grep -Fq -- "$3" "$2/out.log"; then
    pass "$1"
  else
    bad "$1: '${3}' is missing from the step output"
  fi
}

expect_no_log() { # <label> <dir> <text>
  if grep -Fq -- "$3" "$2/out.log"; then
    bad "$1: '${3}' appeared in the step output"
  else
    pass "$1"
  fi
}

# --- the action's download step, executed as extracted ----------------------

# extract_step prints the `run:` body of the download step. Reading the shell out
# of the YAML keeps one copy of the loop: the tests exercise the code the action
# runs, not a transcription of it. The extraction fails loudly rather than
# silently producing an empty script, so a re-indented step cannot turn every
# case into a no-op that passes.
extract_step() {
  awk '
    index($0, "name: Download pinned benchmark bot binary") { found = 1; next }
    found && /^      run: \|$/ { body = 1; next }
    body {
      if ($0 ~ /^[[:space:]]*$/) { print ""; next }
      if ($0 !~ /^        /) { exit }
      sub(/^        /, "", $0); print
    }
  ' "$ACTION"
}

STEP="$WORK/action-step.sh"
extract_step >"$STEP"
if [[ ! -s "$STEP" ]] || ! grep -Fq 'gh release download' "$STEP"; then
  echo "FAIL: could not extract the download step from ${ACTION#"$ROOT"/}" >&2
  exit 1
fi

# The step must take its candidate tags from the resolver; if it stopped calling
# it, every case below would still pass against the extracted block while the
# action used its own copy of the policy.
# shellcheck disable=SC2016 # single quotes are deliberate: the patterns are the literal text of the step.
if grep -Fq '"$resolver" tags --sha' "$ACTION" && grep -Fq '"$resolver" fallback --sha' "$ACTION"; then
  pass "the download step asks resolve-release.sh which tags to try and whether a build is allowed"
else
  bad "the download step no longer calls resolve-release.sh; the tested policy is not the policy the action runs"
fi

# --- fixtures --------------------------------------------------------------

# Two binaries with different digests: one is the release the pin names, the
# other is what a mismatched pin or a tampered asset looks like.
BODY="$WORK/release-asset"
OTHER_BODY="$WORK/other-asset"
printf '#!/bin/sh\necho pinned bot\n' >"$BODY"
printf '#!/bin/sh\necho another bot\n' >"$OTHER_BODY"
BODY_DIGEST="$(sha256sum "$BODY" | awk '{ print $1 }')"
OTHER_DIGEST="$(sha256sum "$OTHER_BODY" | awk '{ print $1 }')"

# The subcommand the benchmark workflows require, and a binary that carries it:
# `--help` names it, which is the only thing the step greps for. A release that
# verifies by digest but was built before the subcommand existed answers --help
# without it, and that stale release is what the check exists to catch.
SUBCMD="post-hnsw-pr-comment"
SUB_BODY="$WORK/subcommand-asset"
printf '#!/bin/sh\necho "usage: ibex-benchmark-bot <command>"\necho "  %s  post the PR comment"\n' \
  "$SUBCMD" >"$SUB_BODY"
SUB_DIGEST="$(sha256sum "$SUB_BODY" | awk '{ print $1 }')"

# gh_stub answers `gh release download` from the environment and records every
# call. FAKE_GH_MODE=absent models a tag with no release; FAKE_GH_MODE=serve
# models one, and FAKE_GH_PUBLISHED_DIGEST is the digest its `.sha256` asset
# carries, so a binary that matches the pin can still be paired with a published
# checksum that does not. FAKE_GH_ABSENT_TAGS lists tags whose download fails
# even though the mode serves, which is how a case tells the first candidate from
# the second.
gh_stub() {
  cat >"$1" <<'STUB'
#!/usr/bin/env bash
set -u
printf '%s\n' "$*" >>"$FAKE_GH_LOG"
tag=""
asset=""
dir=""
consume=""
for arg in "$@"; do
  if [[ -n "$consume" ]]; then
    case "$consume" in
      pattern) asset="$arg" ;;
      dir) dir="$arg" ;;
    esac
    consume=""
    continue
  fi
  case "$arg" in
    --pattern) consume=pattern ;;
    --dir) consume=dir ;;
    --repo) consume=repo ;;
    -*|release|download) ;;
    *) [[ -n "$tag" ]] || tag="$arg" ;;
  esac
done
case "${FAKE_GH_MODE:-absent}" in
  absent) exit 1 ;;
  serve) ;;
  *)
    printf 'gh stub: unknown FAKE_GH_MODE=%s\n' "$FAKE_GH_MODE" >&2
    exit 2
    ;;
esac
# A tag named here has no release even though the mode serves one. The loop must
# move to the next candidate rather than treat the failure as final.
for skipped in ${FAKE_GH_ABSENT_TAGS:-}; do
  if [[ "$tag" == "$skipped" ]]; then
    exit 1
  fi
done
mkdir -p "$dir"
if [[ "$asset" == *.sha256 ]]; then
  printf '%s  %s\n' "${FAKE_GH_PUBLISHED_DIGEST:-}" "${asset%.sha256}" >"$dir/$asset"
else
  cp "$FAKE_GH_BODY" "$dir/$asset"
fi
STUB
  chmod 0755 "$1"
}
mkdir -p "$WORK/bin"
gh_stub "$WORK/bin/gh"

# stage_case builds one case directory: a private copy of the action whose pin
# file carries <digest>, the extracted step, and empty output and call logs. The
# private pin file is what lets the real `sha256sum` check a real fixture binary
# instead of a digest that had to be faked.
#
# It also resets the knobs run_step reads, so a case cannot inherit a configured
# tag, a required subcommand, a fixture binary or an absent tag from the case
# above it. A case that needs a non-default sets it after staging.
stage_case() {
  local dir="$1" digest="$2"
  mkdir -p "$dir/action" "$dir/bin"
  cp "$ACTION" "$RESOLVER" "$dir/action/"
  printf '%s  ibex-benchmark-bot-linux-amd64\n' "$digest" \
    >"$dir/action/ibex-benchmark-bot-linux-amd64.sha256"
  cp "$STEP" "$dir/action-step.sh"
  cp "$WORK/bin/gh" "$dir/bin/gh"
  : >"$dir/github-output"
  : >"$dir/gh.log"
  configured=""
  required_subcommand=""
  asset_body="$BODY"
  absent_tags=""
}

# run_step <dir> <gh-mode> <published-digest> runs the step as GitHub would, with:
#   configured           the BENCHMARK_BOT_RELEASE_TAG the caller sets
#   required_subcommand  REQUIRE_SUBCOMMAND, the action's require-subcommand input
#   asset_body           the fixture binary the stub `gh` serves
#   absent_tags          tags whose download fails while the rest succeed
# The exit status is recorded, never raised, so a failing case is an assertion
# rather than an aborted suite.
configured=""
required_subcommand=""
asset_body="$BODY"
absent_tags=""
run_step() {
  local dir="$1" mode="$2" published="$3" status=0
  (
    cd "$dir"
    GITHUB_ACTION_PATH="$dir/action"
    GITHUB_WORKSPACE="$dir"
    GITHUB_OUTPUT="$dir/github-output"
    GH_TOKEN="test-token"
    BENCHMARK_BOT_SHA="$PIN"
    BENCHMARK_BOT_RELEASE_TAG="$configured"
    REQUIRE_SUBCOMMAND="$required_subcommand"
    FAKE_GH_LOG="$dir/gh.log"
    FAKE_GH_MODE="$mode"
    FAKE_GH_BODY="$asset_body"
    FAKE_GH_PUBLISHED_DIGEST="$published"
    FAKE_GH_ABSENT_TAGS="$absent_tags"
    PATH="$dir/bin:$PATH"
    export GITHUB_ACTION_PATH GITHUB_WORKSPACE GITHUB_OUTPUT GH_TOKEN
    export BENCHMARK_BOT_SHA BENCHMARK_BOT_RELEASE_TAG REQUIRE_SUBCOMMAND
    export FAKE_GH_LOG FAKE_GH_MODE FAKE_GH_BODY FAKE_GH_PUBLISHED_DIGEST
    export FAKE_GH_ABSENT_TAGS PATH
    bash "$dir/action-step.sh"
  ) >"$dir/out.log" 2>&1 || status=$?
  printf '%s\n' "$status" >"$dir/status"
}

# attempted_tags prints the distinct tags the step asked `gh` for, in order.
attempted_tags() {
  sed -n 's/^release download \([^ ]*\).*/\1/p' "$1/gh.log" | awk '!seen[$0]++'
}

# --- resolver interface ----------------------------------------------------

dir="$WORK/interface"
mkdir -p "$dir"
if [[ "$(bash "$RESOLVER" tags --sha "$PIN")" == "$(printf 'tag=%s\ntag=%s' "$BOT_TAG" "$V_TAG")" ]]; then
  pass "with no configured tag the resolver offers $BOT_TAG then $V_TAG"
else
  bad "the resolver does not offer the two derived tags for a pin with no configured tag"
fi
if [[ "$(bash "$RESOLVER" tags --sha "$PIN" --tag "$V_TAG")" == "$(printf 'tag=%s\ntag=%s' "$V_TAG" "$BOT_TAG")" ]]; then
  pass "a configured tag that names the pin is offered first and is not repeated"
else
  bad "the resolver does not put a matching configured tag first, or repeats a derived tag"
fi
if ! out="$(bash "$RESOLVER" tags --sha "$PIN" --tag "$BOT_TAG" 2>"$dir/err.log")"; then
  bad "the resolver rejected $BOT_TAG, which names the pin"
elif [[ "$out" != "$(printf 'tag=%s\ntag=%s' "$BOT_TAG" "$V_TAG")" ]]; then
  bad "a matching configured tag produced '${out}'"
else
  pass "a configured tag that names the pin is accepted and deduplicated against the derived one"
fi
if out="$(bash "$RESOLVER" tags --sha "$PIN" --tag bot-9999999 2>"$dir/err.log")" && [[ -n "$out" ]]; then
  bad "the resolver accepted a configured tag for another commit and still printed candidates"
else
  if grep -Fq 'does not match pin' "$dir/err.log"; then
    pass "the resolver refuses a configured tag for another commit and prints no candidate"
  else
    bad "the resolver refused a mismatched tag without naming the disagreement"
  fi
fi
if [[ "$(bash "$RESOLVER" fallback --sha "$PIN" 2>"$dir/err.log")" == "source=build" ]]; then
  pass "the resolver allows a source build when no tag was configured"
else
  bad "the resolver did not allow a source build with no configured tag"
fi
if bash "$RESOLVER" fallback --sha "$PIN" --tag "$BOT_TAG" >/dev/null 2>"$dir/err.log"; then
  bad "the resolver allowed a source build although a release tag was configured"
elif grep -Fq 'Refusing to fall back to a source build' "$dir/err.log"; then
  pass "the resolver refuses a source build when a configured tag verified nothing"
else
  bad "the resolver refused the source fallback without saying so"
fi
# The usage text is how a caller learns --sha is required, so `--help` must be
# answered before that requirement is enforced; it used to exit 2 with
# "--sha is required" and never print the usage it was asked for.
if bash "$RESOLVER" --help >"$dir/help.log" 2>&1 &&
  grep -Fq 'Usage: resolve-release.sh' "$dir/help.log"; then
  pass "the resolver answers --help before it demands --sha"
else
  bad "the resolver does not answer --help: it exits non-zero or prints no usage"
fi

# --- case 1: no configured tag, no release exists --------------------------

dir="$WORK/case1-no-release"
stage_case "$dir" "$BODY_DIGEST"
configured=""
run_step "$dir" absent ""
expect_status "case 1 (no tag, no release)" "$dir" 0
expect_field "case 1 (no tag, no release)" "$dir" source build
expect_field "case 1 (no tag, no release)" "$dir" path ""
expect_log "case 1 (no tag, no release) says the build will happen" "$dir" "will cargo build"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 1 (no tag, no release) tries $BOT_TAG then $V_TAG"
else
  bad "case 1 (no tag, no release) tried '$(attempted_tags "$dir" | tr '\n' ' ')': expected both derived tags in order"
fi

# --- case 2: configured tag names the pin, the release verifies ------------

dir="$WORK/case2-verified"
stage_case "$dir" "$BODY_DIGEST"
configured="$BOT_TAG"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 2 (tag matches, release verifies)" "$dir" 0
expect_field "case 2 (tag matches, release verifies)" "$dir" source release
expect_field "case 2 (tag matches, release verifies)" "$dir" path \
  "$dir/benchmark-bot-bin/ibex-benchmark-bot-linux-amd64"
expect_log "case 2 (tag matches, release verifies) names the tag it used" "$dir" \
  "Downloaded verified bot binary from release tag ${BOT_TAG}"
if [[ -x "$dir/benchmark-bot-bin/ibex-benchmark-bot-linux-amd64" ]]; then
  pass "case 2 (tag matches, release verifies) left an executable binary"
else
  bad "case 2 (tag matches, release verifies) did not leave an executable binary"
fi
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} " ]]; then
  pass "case 2 (tag matches, release verifies) asked only for the configured tag"
else
  bad "case 2 (tag matches, release verifies) asked for '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

# --- case 3: configured tag does not name the pin -------------------------
#
# The finding: a mismatched tag was printed as "ignoring" and the step fell
# through to the derived tags, so setup passed whenever a derived tag verified.
# The configured tag is now the disagreement it is, and no download is attempted
# for a tag the policy has already rejected.

dir="$WORK/case3-mismatch"
stage_case "$dir" "$BODY_DIGEST"
configured="bot-9999999"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 3 (tag does not match the pin)" "$dir" 1
expect_log "case 3 (tag does not match the pin) names the configured tag and the pin" "$dir" \
  "BENCHMARK_BOT_RELEASE_TAG=bot-9999999 does not match pin ${PIN}"
expect_log "case 3 (tag does not match the pin) names the tags the pin allows" "$dir" \
  "a release tag for this pin is ${BOT_TAG} or ${V_TAG}"
expect_no_log "case 3 (tag does not match the pin) does not ignore the tag" "$dir" "Ignoring"
expect_no_log "case 3 (tag does not match the pin) does not report a source build" "$dir" "will cargo build"
if [[ ! -s "$dir/gh.log" ]]; then
  pass "case 3 (tag does not match the pin) downloaded nothing"
else
  bad "case 3 (tag does not match the pin) still asked gh for '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi
if [[ -z "$(sed -n 's/^\(source\|path\)=.*/&/p' "$dir/github-output")" ]]; then
  pass "case 3 (tag does not match the pin) published no bot-path or source output"
else
  bad "case 3 (tag does not match the pin) published outputs for a step that failed"
fi

# --- case 4: configured tag names the pin, nothing verifies ----------------

dir="$WORK/case4-missing-release"
stage_case "$dir" "$BODY_DIGEST"
configured="$BOT_TAG"
run_step "$dir" absent ""
expect_status "case 4a (tag matches, release missing)" "$dir" 1
expect_log "case 4a (tag matches, release missing) refuses the source fallback" "$dir" \
  "was configured but no release asset verified for pin ${PIN}"
expect_log "case 4a (tag matches, release missing) says the fallback is refused" "$dir" \
  "Refusing to fall back to a source build"
expect_no_log "case 4a (tag matches, release missing) does not announce a cargo build" "$dir" "will cargo build"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 4a (tag matches, release missing) tried the configured tag and then the other spelling"
else
  bad "case 4a (tag matches, release missing) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

dir="$WORK/case4-digest-mismatch"
stage_case "$dir" "$OTHER_DIGEST"
configured="$BOT_TAG"
run_step "$dir" serve "$OTHER_DIGEST"
expect_status "case 4b (tag matches, digest mismatch)" "$dir" 1
expect_log "case 4b (tag matches, digest mismatch) reports the mismatch" "$dir" "SHA-256 mismatch"
expect_log "case 4b (tag matches, digest mismatch) refuses the source fallback" "$dir" \
  "was configured but no release asset verified for pin ${PIN}"
expect_no_log "case 4b (tag matches, digest mismatch) does not announce a cargo build" "$dir" "will cargo build"

# --- case 5: no configured tag, nothing verifies ---------------------------

dir="$WORK/case5-digest-mismatch"
stage_case "$dir" "$OTHER_DIGEST"
configured=""
run_step "$dir" serve "$OTHER_DIGEST"
expect_status "case 5a (no tag, digest mismatch)" "$dir" 0
expect_field "case 5a (no tag, digest mismatch)" "$dir" source build
expect_field "case 5a (no tag, digest mismatch)" "$dir" path ""
expect_log "case 5a (no tag, digest mismatch) reports the mismatch" "$dir" "SHA-256 mismatch"
expect_log "case 5a (no tag, digest mismatch) says the build will happen" "$dir" "will cargo build"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 5a (no tag, digest mismatch) tried both derived tags before falling back"
else
  bad "case 5a (no tag, digest mismatch) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

# The published checksum is the second half of the verification: a binary that
# hashes to the pin, published beside a `.sha256` that disagrees, is not evidence
# that the release is the pin's.
dir="$WORK/case5-published-checksum"
stage_case "$dir" "$BODY_DIGEST"
configured=""
run_step "$dir" serve "$OTHER_DIGEST"
expect_status "case 5b (no tag, published checksum disagrees)" "$dir" 0
expect_field "case 5b (no tag, published checksum disagrees)" "$dir" source build
expect_log "case 5b (no tag, published checksum disagrees) reports the disagreement" "$dir" \
  "checksum asset does not match repo pin"
expect_log "case 5b (no tag, published checksum disagrees) says the build will happen" "$dir" "will cargo build"

# --- case 6: the loop advances from a failed candidate ----------------------
#
# Both tag spellings name the same commit, so a case that fails the first one and
# serves the second proves the loop advances rather than stopping at the first
# error. Without this, a step that only ever tried `bot-<7>` would pass every case
# above, because the stub used to answer both spellings identically.

dir="$WORK/case6-second-tag"
stage_case "$dir" "$BODY_DIGEST"
absent_tags="$BOT_TAG"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 6a (first tag absent, second serves)" "$dir" 0
expect_field "case 6a (first tag absent, second serves)" "$dir" source release
expect_field "case 6a (first tag absent, second serves)" "$dir" path \
  "$dir/benchmark-bot-bin/ibex-benchmark-bot-linux-amd64"
expect_log "case 6a (first tag absent, second serves) names the tag that was used" "$dir" \
  "Downloaded verified bot binary from release tag ${V_TAG}"
expect_no_log "case 6a (first tag absent, second serves) did not take the first tag" "$dir" \
  "Downloaded verified bot binary from release tag ${BOT_TAG}"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 6a (first tag absent, second serves) asked for $BOT_TAG, failed, then asked for $V_TAG"
else
  bad "case 6a (first tag absent, second serves) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

# The other direction: a configured tag is tried first, and its failure falls
# through to the derived spelling rather than ending the search.
dir="$WORK/case6-configured-tag-absent"
stage_case "$dir" "$BODY_DIGEST"
configured="$V_TAG"
absent_tags="$V_TAG"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 6b (configured tag absent, other spelling serves)" "$dir" 0
expect_field "case 6b (configured tag absent, other spelling serves)" "$dir" source release
expect_log "case 6b (configured tag absent, other spelling serves) names the tag that was used" "$dir" \
  "Downloaded verified bot binary from release tag ${BOT_TAG}"
expect_no_log "case 6b (configured tag absent, other spelling serves) did not take the configured tag" "$dir" \
  "Downloaded verified bot binary from release tag ${V_TAG}"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${V_TAG} ${BOT_TAG} " ]]; then
  pass "case 6b (configured tag absent, other spelling serves) tried the configured tag first"
else
  bad "case 6b (configured tag absent, other spelling serves) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

# --- case 7: the required-subcommand gate ----------------------------------
#
# All five benchmark workflows pass require-subcommand, so the check is on the
# path production takes. It used to be untested: run_step cleared
# REQUIRE_SUBCOMMAND, so the branch that rejects a verified release whose binary
# is too old - the stale pin the variable exists to catch - never ran.

dir="$WORK/case7-missing-subcommand-build"
stage_case "$dir" "$BODY_DIGEST"
required_subcommand="$SUBCMD"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 7a (no tag, releases lack the subcommand)" "$dir" 0
expect_field "case 7a (no tag, releases lack the subcommand)" "$dir" source build
expect_field "case 7a (no tag, releases lack the subcommand)" "$dir" path ""
expect_log "case 7a (no tag, releases lack the subcommand) reports the rejection" "$dir" \
  "missing subcommand ${SUBCMD}"
expect_log "case 7a (no tag, releases lack the subcommand) says the build will happen" "$dir" "will cargo build"
expect_no_log "case 7a (no tag, releases lack the subcommand) accepted no release" "$dir" \
  "Downloaded verified bot binary from release tag"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 7a (no tag, releases lack the subcommand) tried the next candidate after the first was rejected"
else
  bad "case 7a (no tag, releases lack the subcommand) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

dir="$WORK/case7-missing-subcommand-fail"
stage_case "$dir" "$BODY_DIGEST"
configured="$BOT_TAG"
required_subcommand="$SUBCMD"
run_step "$dir" serve "$BODY_DIGEST"
expect_status "case 7b (tag configured, releases lack the subcommand)" "$dir" 1
expect_log "case 7b (tag configured, releases lack the subcommand) reports the rejection" "$dir" \
  "missing subcommand ${SUBCMD}"
expect_log "case 7b (tag configured, releases lack the subcommand) refuses the source fallback" "$dir" \
  "was configured but no release asset verified for pin ${PIN}"
expect_log "case 7b (tag configured, releases lack the subcommand) says the fallback is refused" "$dir" \
  "Refusing to fall back to a source build"
expect_no_log "case 7b (tag configured, releases lack the subcommand) accepted no release" "$dir" \
  "Downloaded verified bot binary from release tag"
expect_no_log "case 7b (tag configured, releases lack the subcommand) does not announce a cargo build" "$dir" \
  "will cargo build"
if [[ "$(attempted_tags "$dir" | tr '\n' ' ')" == "${BOT_TAG} ${V_TAG} " ]]; then
  pass "case 7b (tag configured, releases lack the subcommand) tried every candidate before failing"
else
  bad "case 7b (tag configured, releases lack the subcommand) tried '$(attempted_tags "$dir" | tr '\n' ' ')'"
fi

# The positive control: without it, a step that rejected every release whenever
# REQUIRE_SUBCOMMAND is set would pass both cases above. This binary's --help
# names the subcommand, so the release must be accepted.
dir="$WORK/case7-subcommand-present"
stage_case "$dir" "$SUB_DIGEST"
configured="$BOT_TAG"
required_subcommand="$SUBCMD"
asset_body="$SUB_BODY"
run_step "$dir" serve "$SUB_DIGEST"
expect_status "case 7c (tag configured, binary carries the subcommand)" "$dir" 0
expect_field "case 7c (tag configured, binary carries the subcommand)" "$dir" source release
expect_field "case 7c (tag configured, binary carries the subcommand)" "$dir" path \
  "$dir/benchmark-bot-bin/ibex-benchmark-bot-linux-amd64"
expect_log "case 7c (tag configured, binary carries the subcommand) names the tag it used" "$dir" \
  "Downloaded verified bot binary from release tag ${BOT_TAG}"
expect_no_log "case 7c (tag configured, binary carries the subcommand) did not reject the release" "$dir" \
  "missing subcommand"

# --- result ----------------------------------------------------------------

if (( fail != 0 )); then
  echo "benchmark bot release resolution tests failed" >&2
  exit 1
fi
printf 'benchmark bot release resolution tests: PASS (%d cases)\n' "$PASSED"
