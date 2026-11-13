#!/usr/bin/env bash
# Validates GitHub Action pins in workflow files:
# 1) external actions must use full 40-char commit SHAs (not tags)
# 2) each pinned SHA must resolve in the action repository (when gh is available)
#
# The SHA existence check calls api.github.com once per pinned action, so it is
# wrapped in a bounded retry: at most 3 attempts, backing off 1s then 2s. A retry
# fires only on a transport failure (timeout, 5xx, connection reset, DNS). A
# definitive 404 is the API answering "that commit does not exist" and fails on
# the first attempt; it is never retried into a pass. Verdicts are cached per
# owner/repo@sha for the duration of the run, so a repeated pin is resolved once.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Retry policy for the network existence check.
PIN_MAX_ATTEMPTS=3
PIN_BACKOFF_SECONDS=(1 2)
PIN_ERROR_PREVIEW=200

fail=0

while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  if [[ ! "$ref" =~ ^[a-f0-9]{40}$ ]]; then
    echo "Unpinned or invalid action ref (expected 40-char SHA): ${ref}"
    fail=1
  fi
done < <(
  grep -rhoE '(^|[[:space:]])uses:[[:space:]]*[^#[:space:]]+' .github/workflows/ \
    | sed -E 's#(^|[[:space:]])uses:[[:space:]]*##' \
    | grep -v '^\./' \
    | grep -v '/\.github/workflows/' \
    | sed -E 's#^[^@]+@##' \
    | sed 's/[[:space:]]*$//' \
    | sort -u
)

if ! command -v gh >/dev/null 2>&1; then
  echo "validate-action-pins: gh CLI not installed; SHA existence check skipped"
  exit "$fail"
fi

# Collapse a multi-line gh error into one bounded line for a warning.
one_line() {
  local text="${1//$'\r'/ }"
  text="${text//$'\n'/ }"
  printf '%s' "${text:0:PIN_ERROR_PREVIEW}"
}

# The API answered definitively that the commit does not exist: never retry.
# An unknown repository answers 404; an unknown commit in a known repository
# answers 422 ("No commit found for SHA: ..."), so both shapes are definitive.
is_definitive_not_found() {
  local err="$1"
  [[ "$err" =~ HTTP[[:space:]]*404 ]] && return 0
  [[ "$err" =~ HTTP[[:space:]]*422 ]] && return 0
  [[ "$err" =~ gh:[[:space:]]*Not[[:space:]]Found ]] && return 0
  [[ "$err" =~ No[[:space:]]commit[[:space:]]found[[:space:]]for[[:space:]]SHA ]] && return 0
  return 1
}

# The request never got a definitive answer from the API. Only recognised
# transport and 5xx signatures are transient; every other failure (401, 403,
# 422, parse errors) is treated as definitive so the check is not weakened.
is_transient_gh_failure() {
  local err="$1"
  [[ "$err" =~ HTTP[[:space:]]*5[0-9][0-9] ]] && return 0
  [[ "$err" =~ (i/o timeout|TLS handshake timeout|context deadline exceeded) ]] && return 0
  [[ "$err" =~ (connection reset|connection refused|broken pipe|network is unreachable) ]] && return 0
  [[ "$err" =~ (no such host|could not resolve host|server misbehaving|Temporary failure in name resolution) ]] && return 0
  [[ "$err" =~ (^|[[:space:]])EOF([[:space:]]|$) ]] && return 0
  return 1
}

# resolve_pin <owner> <repo> <sha> <action>
# Returns 0 when the SHA resolves in the repository, 1 otherwise.
# Writes one warning line to stderr per retry so flakiness is visible, not silent.
resolve_pin() {
  local owner="$1" repo="$2" sha="$3" action="$4"
  local attempt=1 err="" delay=""

  while :; do
    # stderr is captured for classification; stdout is discarded as before.
    if err=$(gh api "repos/${owner}/${repo}/commits/${sha}" --jq .sha 2>&1 >/dev/null); then
      return 0
    fi

    if is_definitive_not_found "$err" || ! is_transient_gh_failure "$err"; then
      return 1
    fi

    if (( attempt >= PIN_MAX_ATTEMPTS )); then
      return 1
    fi

    delay="${PIN_BACKOFF_SECONDS[attempt-1]}"
    echo "validate-action-pins: transient failure resolving ${action}@${sha} (attempt ${attempt}/${PIN_MAX_ATTEMPTS}): $(one_line "$err"); retrying in ${delay}s" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
  done
}

declare -A seen=()
# owner/repo@sha -> ok|bad, so a duplicate pin is resolved once per run.
declare -A pin_verdict=()

while IFS= read -r pinned; do
  [[ -z "$pinned" ]] && continue
  if [[ -n "${seen[$pinned]+x}" ]]; then
    continue
  fi
  seen[$pinned]=1

  action="${pinned%@*}"
  sha="${pinned##*@}"
  owner="${action%%/*}"
  repo="${action#*/}"
  repo="${repo%%/*}"

  if [[ -z "$owner" || -z "$repo" || -z "$sha" ]]; then
    echo "Unable to parse action pin: ${pinned}"
    fail=1
    continue
  fi

  cache_key="${owner}/${repo}@${sha}"
  if [[ -n "${pin_verdict[$cache_key]+x}" ]]; then
    verdict="${pin_verdict[$cache_key]}"
  elif resolve_pin "$owner" "$repo" "$sha" "$action"; then
    verdict=ok
    pin_verdict[$cache_key]=ok
  else
    verdict=bad
    pin_verdict[$cache_key]=bad
  fi

  if [[ "$verdict" != "ok" ]]; then
    echo "Invalid action pin: ${action}@${sha}"
    fail=1
  fi
done < <(
  grep -rhoE '(^|[[:space:]])uses:[[:space:]]*[^#[:space:]]+@[a-f0-9]{40}' .github/workflows/ \
    | sed -E 's#(^|[[:space:]])uses:[[:space:]]*##' \
    | grep -v '^\./' \
    | grep -v '/\.github/workflows/' \
    | sed 's/[[:space:]]*$//' \
    | sort -u
)

exit "$fail"
