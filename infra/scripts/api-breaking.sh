#!/usr/bin/env bash
# OpenAPI breaking-change gate (release plan W5.2 / audit P0-13).
#
# Diffs the committed OpenAPI snapshot against a baseline spec read from git with
# oasdiff, so regenerating the snapshot in a PR can no longer legalise a /v1
# break (`.github/scripts/check-openapi-snapshot.sh` only proves freshness).
#
# oasdiff is module-pinned in .github/tools/go.mod (`tool` directive + go.sum)
# and run through `go run`; it is never installed globally. The invocation names
# no version, so the pin comes from go.mod and go.sum is verified: the first run
# downloads the module graph, and every later run works with GOPROXY=off.
#
# usage: api-breaking.sh [<base>]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.github/tools"
OASDIFF_MODULE="github.com/oasdiff/oasdiff"
SPEC_PATH="services/api/openapi.snapshot.json"
DEFAULT_BASE="origin/main"

usage() {
  cat <<'EOF'
usage: api-breaking.sh [<base>]

  <base>  Git ref the committed OpenAPI snapshot is diffed against.
          Default: origin/main (PR mode, --fail-on WARN, diffed against the
          merge-base of <base> and HEAD).
          A tag selects release mode (--fail-on ERR, diffed against the tag
          itself so the comparison is the released contract). Tag spellings are
          normalized: v0.1.9, tags/v0.1.9 and refs/tags/v0.1.9 are the same
          baseline.

environment:
  IBEX_API_SPEC  Revision spec to check instead of
                 services/api/openapi.snapshot.json (used by the gate's own
                 negative proof; the committed snapshot stays untouched).

oasdiff runs with an explicit empty --config file inside this script's temporary
directory, so neither .oasdiff.* in the working directory nor OASDIFF_CONFIG can
change the verdict.

The first run downloads the pinned oasdiff module; later runs work offline (GOPROXY=off).

exit status:
  0  no breaking change at or above the fail-on level for this mode
  1  a breaking change was reported; this is the contract result
  2  the gate could not run: the baseline ref or its history is not in this
     clone (fetch it), oasdiff produced no contract verdict (missing pin, tool
     build, or network), the baseline spec is absent at that ref, or the
     arguments were invalid
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "api-breaking: unknown option '$1'" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done
if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi
base="${1:-$DEFAULT_BASE}"

# Tag detection is spelling-insensitive. `v0.1.9`, `tags/v0.1.9` and
# `refs/tags/v0.1.9` name the same released baseline, so all three must resolve
# to the same tag ref and select the same mode, --fail-on, and released
# snapshot. Git's own DWIM does not cover this: `tags/v0.1.9` resolves as a
# commit through refs/<ref>, but not as refs/tags/tags/v0.1.9, so a literal
# refs/tags/<base> test dropped two of the three spellings into PR mode with a
# merge-base baseline instead of the released contract.
tag_name=""
case "$base" in
  refs/tags/?*) tag_name="${base#refs/tags/}" ;;
  tags/?*) tag_name="${base#tags/}" ;;
  *) tag_name="$base" ;;
esac
tag_ref="refs/tags/${tag_name}"

# A tag spelling is validated as the tag it names, not through DWIM, so a typo in
# refs/tags/... cannot quietly resolve to a branch of that name.
case "$base" in
  refs/tags/?*|tags/?*) base_ref="$tag_ref" ;;
  *) base_ref="$base" ;;
esac

if [[ -n "${IBEX_API_SPEC:-}" ]]; then
  [[ -f "$IBEX_API_SPEC" ]] || {
    echo "api-breaking: IBEX_API_SPEC is not a file: $IBEX_API_SPEC" >&2
    exit 2
  }
  revision="$(cd "$(dirname "$IBEX_API_SPEC")" && pwd)/$(basename "$IBEX_API_SPEC")"
  revision_label="${revision#"$ROOT_DIR"/}"
else
  revision="$ROOT_DIR/$SPEC_PATH"
  revision_label="$SPEC_PATH"
fi

cd "$ROOT_DIR"
git rev-parse -q --verify "${base_ref}^{commit}" >/dev/null 2>&1 || {
  echo "api-breaking: unknown git ref '$base_ref' (from '$base'). Fetch it first: git fetch origin --tags" >&2
  exit 2
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
baseline_spec="$tmp_dir/baseline.json"

# oasdiff loads configuration from --config, then OASDIFF_CONFIG, then
# .oasdiff.{json,yaml,yml,toml,hcl} in the process working directory (here
# .github/tools, because `go run` runs from there). Any of those can change the
# verdict: a config carrying `match-path` narrows the comparison until a removed
# path is not compared at all and the gate passes. The gate owns its
# configuration, so it passes an explicit empty file, which outranks
# OASDIFF_CONFIG. --config is a root persistent flag in the pinned oasdiff
# v1.37.0, and an explicit path that does not exist is an error, so the file is
# created here rather than left to the environment.
oasdiff_config="$tmp_dir/oasdiff.config.yaml"
: >"$oasdiff_config"

# --fail-on is chosen per mode and never relaxed by an ignore file, so the next
# change on a path cannot be masked:
#   PR mode     WARN  a WARN-level finding blocks the PR; the merge-base diff is
#                     clean today, so the gate starts green.
#   release mode ERR  a tag diff is the release gate. oasdiff v1.37.0 reports no
#                     breaking change for v0.1.9 -> HEAD today, so ERR and WARN
#                     are both green; ERR is kept until this gate has run through
#                     one release cycle, so its first red build is a real ERR
#                     regression. Known blind spot: the `cursor` query parameter
#                     of GET /v1/agents gained maxLength=2048 (a genuine
#                     narrowing) and `breaking` does not report it, because the
#                     constraint sits inside a nullable anyOf branch and no
#                     request-parameter-max-length-* check fires there; it shows
#                     only in `oasdiff diff`. Flip this to WARN once WARN-level
#                     findings are being triaged rather than masked, or when that
#                     parameter stops being an anyOf union (the narrowing then
#                     becomes an ERR and fails either way).
if git rev-parse -q --verify "${tag_ref}^{commit}" >/dev/null 2>&1; then
  mode='release mode'
  baseline_rev="$tag_ref"
  baseline_label="tag $tag_name"
  fail_on='ERR'
else
  mode='PR mode'
  # A failing merge-base is not a contract result. A shallow clone or an
  # unrelated history has no merge-base, and under `set -e` the bare assignment
  # aborted with git's own status - the same status a confirmed break returns -
  # and no diagnostic. Report what is missing and exit 2 (could not run).
  if ! baseline_rev="$(git merge-base "$base" HEAD 2>"$tmp_dir/merge-base.err")"; then
    fetch_hint="$base"
    if [[ "$base" == origin/?* ]]; then
      fetch_hint="${base#origin/}"
    fi
    echo "api-breaking: cannot find a merge-base between '$base' and HEAD; the baseline history is not in this clone." >&2
    echo "api-breaking: fetch '$base' first, then re-run:" >&2
    echo "api-breaking:   git fetch origin '$fetch_hint'   # ref never fetched here" >&2
    echo "api-breaking:   git fetch --unshallow            # --depth 1 / shallow clone" >&2
    echo "api-breaking: an unrelated history has no merge-base to fetch; merge or rebase it instead." >&2
    sed 's/^/  /' "$tmp_dir/merge-base.err" >&2
    exit 2
  fi
  baseline_label="$base at merge-base ${baseline_rev:0:12}"
  fail_on='WARN'
fi

if ! git show "${baseline_rev}:${SPEC_PATH}" >"$baseline_spec" 2>"$tmp_dir/git-show.err"; then
  echo "api-breaking: no ${SPEC_PATH} at ${baseline_label}; the baseline predates the snapshot." >&2
  echo "api-breaking: pass a newer ref (or a tag that contains the snapshot)." >&2
  sed 's/^/  /' "$tmp_dir/git-show.err" >&2
  exit 2
fi
if [[ ! -s "$baseline_spec" ]]; then
  echo "api-breaking: ${SPEC_PATH} is empty at ${baseline_label}" >&2
  exit 2
fi

pin_err="$tmp_dir/go-list.err"
version="$(cd "$TOOLS_DIR" && go list -m -f '{{.Version}}' "$OASDIFF_MODULE" 2>"$pin_err" || true)"
if [[ -z "$version" ]]; then
  # A missing pin and an unresolvable pin are different operator problems: the
  # first needs a go.mod edit, the second needs a network (or a warm module cache).
  if grep -q "tool ${OASDIFF_MODULE}" "$TOOLS_DIR/go.mod" 2>/dev/null; then
    echo "api-breaking: cannot resolve ${OASDIFF_MODULE} from .github/tools/go.mod." >&2
    echo "api-breaking: it is pinned there; the failure is resolution, not the pin (offline cache?)." >&2
    echo "api-breaking: run once with the network available, or point GOMODCACHE at a warm cache." >&2
    sed 's/^/  /' "$pin_err" >&2
  else
    echo "api-breaking: ${OASDIFF_MODULE} is not pinned in .github/tools/go.mod." >&2
    echo "api-breaking: add 'tool ${OASDIFF_MODULE}' there and run 'cd .github/tools && go mod tidy'." >&2
    echo "api-breaking: this gate never installs a tool globally." >&2
  fi
  exit 2
fi

echo "api-breaking: ${OASDIFF_MODULE} ${version} via go run, pinned in .github/tools/go.mod (no global install)"
echo "api-breaking: baseline ${baseline_label} -> ${revision_label} (${mode}, --fail-on ${fail_on})"

out="$tmp_dir/oasdiff.out"
err="$tmp_dir/oasdiff.err"
set +e
(cd "$TOOLS_DIR" && go run "$OASDIFF_MODULE" breaking "$baseline_spec" "$revision" \
  --config "$oasdiff_config" --fail-on "$fail_on" --format text --color never) >"$out" 2>"$err"
status=$?
set -e

# Telling "the tool never ran" apart from "the tool found a break" cannot use the
# exit status: on a cold module cache `go run` writes module-graph progress to
# stderr ("go: downloading ..."), and it flattens oasdiff's own non-zero result
# to 1, the same status a failed build or a blocked download returns. So the
# classification is output-based:
#   1. `go` progress lines are stripped; they are not failures.
#   2. oasdiff's contract report is what it writes to stdout. A report means the
#      comparison happened, so a non-zero status is a contract verdict (exit 1).
#   3. no report and a non-zero status means oasdiff produced no verdict, so the
#      failure is the tool or the network (exit 2).
# `go run` also echoes the child's status ("exit status 1"); that is not a
# diagnostic either, because the status is handled below.
nonfatal_re='^(go: (downloading|finding|extracting|verifying|copying) |exit status [0-9]+$)'
diagnostics="$tmp_dir/oasdiff.diagnostics"
if [[ -s "$err" ]]; then
  grep -vE "$nonfatal_re" "$err" >"$diagnostics" || true
else
  : >"$diagnostics"
fi

if [[ -s "$out" ]]; then
  if [[ -s "$diagnostics" ]]; then
    cat "$diagnostics" >&2
  fi
  cat "$out"
  if (( status == 0 )); then
    echo "api-breaking: PASS - oasdiff reported no breaking change at or above ${fail_on} from ${baseline_label}"
    exit 0
  fi
  echo "api-breaking: FAIL - oasdiff reported a breaking change at or above ${fail_on} from ${baseline_label}." >&2
  echo "api-breaking: make the change additive (new field, new optional parameter, new path), keep the old" >&2
  echo "api-breaking: shape until its deprecation window closes, or justify the break in review." >&2
  exit 1
fi

if (( status == 0 )); then
  echo "api-breaking: PASS - oasdiff reported no breaking change at or above ${fail_on} from ${baseline_label}"
  exit 0
fi

echo "api-breaking: FAILED to run oasdiff (exit ${status}); it wrote no contract verdict, so this is a tool or network error, not a contract change." >&2
echo "api-breaking: only the first run needs the network (it downloads the pinned module)." >&2
cat "$err" >&2
exit 2
