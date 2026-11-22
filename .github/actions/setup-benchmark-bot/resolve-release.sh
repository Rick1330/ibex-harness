#!/usr/bin/env bash
# resolve-release.sh — the release-resolution policy of the setup-benchmark-bot
# action.
#
# The policy used to live inline in the action's `run:` block, where `bash -n`
# could check its syntax but nothing could check its decisions. It is extracted
# here so the five outcomes below are asserted by
# infra/scripts/test-benchmark-bot-resolve.sh without a network call.
#
# This script performs no network I/O and no digest computation. The caller keeps
# the `gh release download` / `sha256sum` loop, because those are the parts a test
# has to stub.
#
# Usage:
#   resolve-release.sh tags --sha <pin> [--tag <configured>]
#       Print one `tag=<t>` line per release tag the caller may try, in order.
#       A configured tag that does not name the pin is an error (exit 1): the
#       SHA, the tag and the digest are one pin, so a tag that disagrees with
#       the SHA is drift to fix, never an override to ignore. With no configured
#       tag, `bot-<7>` and `v<7>` of the SHA are printed, in that order.
#
#   resolve-release.sh fallback --sha <pin> [--tag <configured>]
#       Called once no candidate verified. With no configured tag it prints
#       `source=build` and exits 0: an unreleased development commit legitimately
#       has no asset. With a configured tag it exits 1, because a configured tag
#       is a claim that a verified release exists for this pin and a source build
#       would hide a pin that no longer matches any release.
#
# stdout carries the decision and nothing else; diagnostics go to stderr, so a
# caller can parse one and log the other.
#
# Exit status: 0 for a decision, 1 for a refusal, 2 for a usage error.
set -euo pipefail

PROG="$(basename "${BASH_SOURCE[0]}")"
# The tag convention in the bot repository: `bot-<7-char-sha>` or `v<7-char-sha>`.
SHORT_LEN=7

usage() {
  cat <<'EOF'
Usage: resolve-release.sh tags     --sha <pin> [--tag <configured>]
       resolve-release.sh fallback --sha <pin> [--tag <configured>]

  tags       print `tag=<t>` for every release tag that may be tried, in order
  fallback   decide what to do when none of them verified: `source=build`, or a
             refusal when a release tag was configured

The SHA, the release tag and the digest are one pin. A configured tag that does
not name `bot-<7-char-sha>` or `v<7-char-sha>` of --sha is an error.
EOF
}

die() {
  printf '%s: %s\n' "$PROG" "$*" >&2
  exit 2
}

verb="${1:-}"
if [[ -z "$verb" ]]; then
  usage >&2
  exit 2
fi
shift

sha=""
configured=""
while (( $# )); do
  case "$1" in
    --sha)
      (( $# >= 2 )) || die "--sha needs a value"
      sha="$2"
      shift 2
      ;;
    --tag)
      (( $# >= 2 )) || die "--tag needs a value"
      configured="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

# Help is a request, not a decision, so it is answered before --sha is required:
# the usage text is how a caller learns that --sha is required.
case "$verb" in
  -h|--help|help)
    usage
    exit 0
    ;;
esac

[[ -n "$sha" ]] || die "--sha is required"

# The short form both tag conventions are built from.
short="${sha:0:SHORT_LEN}"

# pin_spells_tag is true when a tag names this pin. It is the only thing that
# makes a configured tag usable: anything else names a different commit.
pin_spells_tag() {
  [[ "$1" == "bot-${short}" || "$1" == "v${short}" ]]
}

tags() {
  local -a candidates=()
  if [[ -n "$configured" ]]; then
    if ! pin_spells_tag "$configured"; then
      printf '::error::BENCHMARK_BOT_RELEASE_TAG=%s does not match pin %s: a release tag for this pin is bot-%s or v%s. Refusing to continue, because the SHA, the tag and the digest are one pin; re-pin the SHA instead of overriding the tag alone.\n' \
        "$configured" "$sha" "$short" "$short" >&2
      return 1
    fi
    candidates+=("$configured")
  fi
  candidates+=("bot-${short}" "v${short}")
  # A configured tag that already is one of the derived names is emitted once:
  # a duplicate would make the caller retry a tag it has just rejected.
  printf '%s\n' "${candidates[@]}" | awk '!seen[$0]++ { print "tag=" $0 }'
}

fallback() {
  if [[ -n "$configured" ]]; then
    printf '::error::BENCHMARK_BOT_RELEASE_TAG=%s was configured but no release asset verified for pin %s. Refusing to fall back to a source build; fix the pin (SHA, tag and digest move together).\n' \
      "$configured" "$sha" >&2
    return 1
  fi
  printf 'source=build\n'
  printf 'No usable release asset for pin %s; will cargo build.\n' "$sha" >&2
}

case "$verb" in
  tags) tags ;;
  fallback) fallback ;;
  *)
    usage >&2
    die "unknown command: $verb"
    ;;
esac
