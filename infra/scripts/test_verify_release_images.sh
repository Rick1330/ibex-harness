#!/usr/bin/env bash
# test_verify_release_images.sh — regression tests for verify-release-images.sh.
#
# The verifier is the only evidence a tagged release published its images: the
# reusable docker-publish workflow reports green while every publish job is
# skipped, so the release workflow inspects the published artifact instead. A
# guard that silently passes would restore exactly the failure it exists to
# catch, so these cases pin its behaviour:
#
#   1. a tag whose every service resolves to a sha256 digest passes;
#   2. one absent service fails the run and is named;
#   3. several absent services, separated by a published one, are all reported
#      and the published one is not, so a success cannot mask a miss;
#   4. a digest that is not `sha256:<64 hex>` — truncated, the literal `null`,
#      empty — counts as absent, whatever the registry answered;
#   5. a tag that is not `vX.Y.Z`, and a host with no docker, are usage errors
#      (exit 2) rather than passes.
#
# A stub `docker` on PATH answers `buildx imagetools inspect` from a list, so no
# registry, network, or container engine is touched.
#
# Run directly: bash infra/scripts/test_verify_release_images.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERIFY="$ROOT_DIR/infra/scripts/verify-release-images.sh"
BASH_BIN="${BASH:-$(command -v bash)}"

PASSED=0
pass() {
  PASSED=$((PASSED + 1))
  echo "PASS: $*"
}
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ibex-release-images-tests.XXXXXX")"
cleanup() {
  rm -rf "$WORK"
}
trap cleanup EXIT

STUB_BIN="$WORK/bin"
EMPTY_BIN="$WORK/empty-bin"
PRESENT="$WORK/present.txt"
mkdir -p "$STUB_BIN" "$EMPTY_BIN"

GOOD_DIGEST="sha256:$(printf 'a%.0s' {1..64})"
REPOSITORY="Rick1330/ibex-harness"

cat >"$STUB_BIN/docker" <<'STUB'
#!/usr/bin/env bash
# Stands in for `docker buildx imagetools inspect <ref> --format <template>`.
# Answers from $FAKE_PRESENT, one "<service>" or "<service>=<digest>" per line,
# and exits non-zero for anything absent, which is what a real inspect does.
set -u
if [[ "${1:-}" != "buildx" || "${2:-}" != "imagetools" || "${3:-}" != "inspect" ]]; then
  printf 'stub docker: unsupported invocation: %s\n' "$*" >&2
  exit 99
fi
reference="${4:-}"
service="${reference##*/}"
service="${service%%:*}"
while IFS= read -r line; do
  case "$line" in
    "$service" | "$service="*)
      if [[ "$line" == *=* ]]; then
        printf '"%s"\n' "${line#*=}"
      else
        printf '"%s"\n' "${FAKE_DIGEST}"
      fi
      exit 0
      ;;
  esac
done <"$FAKE_PRESENT"
printf 'stub docker: not found: %s\n' "$reference" >&2
exit 1
STUB
chmod 0755 "$STUB_BIN/docker"

# verify runs the verifier against the stub. Remaining arguments describe what
# the registry holds: "<service>" for a published image, or "<service>=<digest>"
# for one that answers with exactly that digest.
verify() {
  local services="$1" tag="$2"
  shift 2
  : >"$PRESENT"
  local entry
  for entry in "$@"; do
    printf '%s\n' "$entry" >>"$PRESENT"
  done
  PATH="$STUB_BIN:$PATH" \
    GITHUB_REPOSITORY="$REPOSITORY" \
    FAKE_PRESENT="$PRESENT" \
    FAKE_DIGEST="$GOOD_DIGEST" \
    "$BASH_BIN" "$VERIFY" --tag "$tag" --services "$services"
}

# exit_code prints the status of a command whose failure is the point, with the
# output left in $WORK/last.log for the assertion that follows.
exit_code() {
  local status=0
  set +e
  "$@" >"$WORK/last.log" 2>&1
  status=$?
  set -e
  printf '%s\n' "$status"
}

# --- case 1: every service published ---------------------------------------

if ! verify "auth,proxy" v1.2.3 auth proxy >"$WORK/all.log" 2>&1; then
  cat "$WORK/all.log" >&2
  fail "all present: the verifier exited non-zero"
fi
grep -q 'verified 2 release images at v1.2.3' "$WORK/all.log" \
  || fail "all present: the success message is missing"
pass "every published service passes"

# --- case 2: one service absent --------------------------------------------

if verify "auth,proxy" v1.2.3 auth >"$WORK/one-missing.log" 2>&1; then
  fail "one missing: the verifier exited zero although proxy published nothing"
fi
grep -q 'published no image for: proxy' "$WORK/one-missing.log" \
  || fail "one missing: the absent service was not named"
pass "an absent service fails and is named"

# --- case 3: several absent, one published between them ---------------------

if verify "auth,proxy,api" v1.2.3 proxy >"$WORK/aggregate.log" 2>&1; then
  fail "aggregation: the verifier exited zero although auth and api published nothing"
fi
grep -q 'published no image for: auth api' "$WORK/aggregate.log" \
  || fail "aggregation: not every absent service was named in one line"
missing_lines="$(grep -c 'missing release image:' "$WORK/aggregate.log" || true)"
[[ "$missing_lines" == "2" ]] \
  || fail "aggregation: expected 2 per-service failures, saw $missing_lines"
if grep -q 'published no image for: proxy' "$WORK/aggregate.log"; then
  fail "aggregation: the published service was reported as missing"
fi
pass "several absent services either side of a published one are all reported"

# --- case 4: a digest that is not sha256:<64 hex> ---------------------------

for digest in "sha256:abc" "null" ""; do
  if verify "auth" v1.2.3 "auth=$digest" >"$WORK/malformed.log" 2>&1; then
    fail "malformed digest '$digest': the verifier exited zero"
  fi
  grep -q 'published no image for: auth' "$WORK/malformed.log" \
    || fail "malformed digest '$digest': the service was not named"
done
pass "a digest that is not sha256:<64 hex> counts as a missing image"

# --- case 5: usage errors are not passes ------------------------------------

for tag in "1.2.3" "v1.2" "latest"; do
  code="$(exit_code verify "auth" "$tag" auth)"
  [[ "$code" == "2" ]] || fail "invalid tag '$tag': expected exit 2, saw $code"
done
grep -q 'unsupported release tag' "$WORK/last.log" \
  || fail "invalid tag: the refusal message is missing"
pass "an invalid release tag is a usage error"

code="$(exit_code env PATH="$EMPTY_BIN" GITHUB_REPOSITORY="$REPOSITORY" \
  "$BASH_BIN" "$VERIFY" --tag v1.2.3 --services auth)"
[[ "$code" == "2" ]] || fail "no docker: expected exit 2, saw $code"
grep -q 'docker is not available' "$WORK/last.log" \
  || fail "no docker: the refusal message is missing"
pass "a host without docker is a usage error"

echo "release image verification tests: PASS ($PASSED cases)"
