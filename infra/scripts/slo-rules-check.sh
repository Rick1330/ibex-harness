#!/usr/bin/env bash
# Gate the IBEX SLO rule tier (W6.3).
#
#   bash infra/scripts/slo-rules-check.sh     # or: make slo-rules-check
#
# Five checks, in order, and every one of them can fail:
#
#   1. Parse. `promtool check rules` over every rule file under
#      infra/monitoring/prometheus/rules (including rules/test/, excluding the
#      *.test.yml unit-test files, which are not rule files). A rule file that
#      Prometheus cannot load is not a detector.
#   2. Route annotations. Every alert in every SLO rule file must carry a
#      routing `severity` label (page|ticket) under `labels:` plus `summary` and
#      `runbook` annotations under `annotations:`. check-alert-routing.py proves
#      the severity reaches a receiver; this proves the operator has something
#      to act on when it does.
#   3. Rendered bucket labels. The bad-share expressions read the 20 ms bucket of
#      ibex_proxy_overhead_seconds. The number in buckets.go is a Go literal
#      (0.020) and the label Prometheus stores is that float rendered by
#      client_golang (0.02) — quoting the literal matches no series at all, so
#      the ratio rules return an empty vector, both burn alerts go quiet, and the
#      absence alert stays quiet too because _count still exists. The p99 rules
#      keep working, so dashboards look healthy while alerting is dead. This
#      check therefore renders the family's bounds the way the client does and
#      asserts every le= selector in the SLO rule file exists in that set. It
#      does not grep for a number: a grep for 0.020 passes on the broken rule.
#      A self-mutation re-runs the check on a copy of the rule file with the
#      selectors reverted to the Go literal and requires it to be rejected, so
#      the check itself cannot rot into a no-op.
#   4. Expectation shape. The unit-test files must keep both a firing and a
#      silent assertion. `both` means both: the silent half used to be dead code
#      (the caller passed "both", the parser compared against "silent"), so
#      deleting every negative expectation still exited 0. A self-mutation deletes
#      every silent expectation from a copy and requires the check to reject it.
#   5. Synthetic burn. `promtool test rules` evaluates the shipped rule file
#      against a synthetic histogram carrying the *rendered* labels: a 50% share
#      over 20 ms must produce a 50x burn rate and fire both burn alerts, a 1%
#      share must fire neither, a recovering burn must not page, an SLI that is
#      missing while the proxy serves traffic must raise the absence alert, and
#      an idle stack must not. A constant probe in rules/test/ is asserted to
#      fire on its first evaluation with no traffic at all.
#
# Runner selection. The rule files are evaluated by promtool, which must be new
# enough to have `check rules` and `test rules`. In order:
#   * $IBEX_PROMTOOL if it is >= 2.x (an explicit choice that cannot be ignored);
#   * /snap/bin/promtool or `promtool` on PATH, when its major version is >= 2;
#   * the digest-pinned Prometheus image from
#     infra/compose/observability/docker-compose.yml, run through docker or
#     podman. The image is not re-pinned here: the compose file stays the single
#     source of the digest, so an upgrade moves both together.
# A promtool older than 2.x is rejected by the version probe, not by path: the
# snap on this workstation is 1.8.2 (2017), has neither subcommand, and cannot
# read files under $HOME at all (snap confinement reports permission denied), so
# the container path is the one that actually runs here.
#
# Check 3 needs a Go toolchain, because the label a client emits is a property of
# the client library and not of a float formatter we can retype in awk. The tiny
# program it runs renders the bounds twice — once through client_golang's own
# text encoder and once with strconv.FormatFloat(bound, 'g', -1, 64) — and
# refuses to answer if the two disagree, so a client upgrade that changes the
# rendering is a gate failure rather than a silently inert alert.
#
# Exit codes: 0 every check ran and passed; 1 a check failed; 2 no verdict was
# possible (no capable promtool and no container runtime, a missing rule file, no
# Go toolchain for check 3, or an unreadable pin). 2 is never a pass: an
# unrunnable gate proves nothing.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROM_DIR="$ROOT_DIR/infra/monitoring/prometheus"
RULES_DIR="$PROM_DIR/rules"
TEST_DIR="$RULES_DIR/test"
UNIT_TEST_DIR="$TEST_DIR/unit"
COMPOSE_FILE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
METRICS_DIR="$ROOT_DIR/packages/metrics"
SLO_HEADER_RULES="$RULES_DIR/ibex-slo.yml"
PROBE_TEST="$UNIT_TEST_DIR/ibex-slo-burn-probe.test.yml"
BURN_TEST="$UNIT_TEST_DIR/ibex-slo-burn.test.yml"
PROM_MOUNT=/prometheus
PROBE_ALERT=IbexSloBurnProbe
FAST_BURN_ALERT=IbexProxyOverheadFastBurn
SLOW_BURN_ALERT=IbexProxyOverheadSlowBurn
FAST_BURN_SPEC="$FAST_BURN_ALERT:both"
SLOW_BURN_SPEC="$SLOW_BURN_ALERT:both"
PROBE_SPEC="$PROBE_ALERT:firing"

FAILURES=0
fail() { printf 'slo-rules-check: FAIL %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }
pass() { printf 'slo-rules-check: ok %s\n' "$*"; }
note() { printf 'slo-rules-check: %s\n' "$*"; }
no_verdict() { printf 'slo-rules-check: cannot verify %s\n' "$*" >&2; exit 2; }

# TMP_DIR holds the label-rendering program and the mutated copies the two
# self-tests feed to their checkers. Nothing is written inside the repository.
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ibex-slo-check.XXXXXX")"
cleanup_tmp() { rm -rf "$TMP_DIR"; }
trap cleanup_tmp EXIT

# prometheus_image reads the pinned digest from the compose file that actually
# runs the stack, so the check and the deployment cannot drift apart.
prometheus_image() {
  sed -n 's/^[[:space:]]*image:[[:space:]]*\(docker\.io\/prom\/prometheus@sha256:[0-9a-f]\{64\}\)[[:space:]]*$/\1/p' \
    "$COMPOSE_FILE" | head -n 1
}

# promtool_major prints the major version of a promtool binary, or nothing when
# the binary does not answer `version` at all (an old build prints usage).
promtool_major() {
  "$1" version 2>/dev/null |
    sed -n 's/^promtool, version \([0-9][0-9]*\)\..*/\1/p' | head -n 1
}

RUNNER_KIND=""
PROMTOOL_CMD=()

select_runner() {
  local candidate major image runtime
  if [[ -n "${IBEX_PROMTOOL:-}" ]]; then
    [[ -x "$IBEX_PROMTOOL" ]] || no_verdict "IBEX_PROMTOOL=$IBEX_PROMTOOL is not executable"
    major="$(promtool_major "$IBEX_PROMTOOL")"
    if [[ -z "$major" || "$major" -lt 2 ]]; then
      no_verdict "IBEX_PROMTOOL=$IBEX_PROMTOOL is promtool ${major:-unknown}.x; need >= 2.x for 'check rules' and 'test rules'"
    fi
    PROMTOOL_CMD=("$IBEX_PROMTOOL")
    RUNNER_KIND="local promtool"
    return 0
  fi
  for candidate in /snap/bin/promtool "$(command -v promtool 2>/dev/null || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    major="$(promtool_major "$candidate")"
    [[ -n "$major" && "$major" -ge 2 ]] || continue
    PROMTOOL_CMD=("$candidate")
    RUNNER_KIND="local promtool"
    return 0
  done
  image="$(prometheus_image)"
  [[ -n "$image" ]] || no_verdict "no promtool >= 2 and no pinned Prometheus image readable from $COMPOSE_FILE"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    runtime=docker
  elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    runtime=podman
  else
    no_verdict "no promtool >= 2 on PATH and no running docker/podman to run $image (set IBEX_PROMTOOL to a promtool 2.x binary)"
  fi
  PROMTOOL_CMD=("$runtime" run --rm --entrypoint /bin/promtool
    -v "$PROM_DIR:$PROM_MOUNT:ro" "$image")
  RUNNER_KIND="$runtime container"
  return 0
}

# to_runner_path maps a host path into the container mount, and is the identity
# for a local promtool. Rule unit tests reference their rule file relatively
# (../ibex-slo.yml), so the directory layout has to survive the mapping.
to_runner_path() {
  if [[ "$RUNNER_KIND" == "local promtool" ]]; then
    printf '%s' "$1"
  else
    printf '%s' "${1/#$PROM_DIR/$PROM_MOUNT}"
  fi
}

# rule_files lists every rule file Prometheus would load, including the test
# probes, and excluding the promtool unit-test files (which live in
# rules/test/unit/ precisely so they are never mistaken for loaded rules).
rule_files() {
  find "$RULES_DIR" -type f -name '*.yml' ! -name '*.test.yml' -print | sort
}

# alert_coverage reports alerts that carry no severity label, no summary, or no
# runbook. It reads only the `labels:` and `annotations:` sections of each alert
# block, so a `summary:` that drifted into labels still counts as a summary, but
# a `severity:` under annotations does not count as a routing label.
alert_coverage() {
  awk '
    function report(what) {
      printf "FAIL %s:%d: alert %s has no %s\n", file, line, name, what > "/dev/stderr"
      bad = 1
    }
    function flush() {
      if (!open) return
      if (!sev) report("routing severity label under labels:")
      if (!summary) report("summary annotation")
      if (!runbook) report("runbook annotation")
    }
    /^[[:space:]]*-[[:space:]]+alert:/ {
      flush()
      file = FILENAME
      line = FNR
      name = $3
      sev = summary = runbook = 0
      section = ""
      open = 1
      next
    }
    open && /^[[:space:]]+(labels|annotations):/ {
      section = $1
      sub(":", "", section)
      next
    }
    open && /^[[:space:]]+severity:[[:space:]]*(page|ticket)[[:space:]]*$/ && section == "labels" { sev = 1 }
    open && /^[[:space:]]+summary:/ && section == "annotations" { summary = 1 }
    open && /^[[:space:]]+runbook:/ && section == "annotations" { runbook = 1 }
    END {
      flush()
      exit bad
    }
  ' "$@"
}

# expectation_shape proves a promtool unit-test file still contains the kind of
# assertion it is named for. Each spec is `ALERT:kind` where kind is
#
#   firing  the file must assert at least one firing evaluation of ALERT;
#   silent  the file must assert at least one empty (exp_alerts: []) evaluation;
#   both    the file must assert at least one of each.
#
# "both" is what the burn alerts use, and it is the reason this function exists
# in this shape. It previously read `need_silent = (kind == "silent")` while the
# caller passed "both", so the silent half was unreachable and every negative
# expectation could be deleted without the gate noticing. Emptying an
# `exp_alerts:` list (or dropping it) is the cheapest way to make a rule gate
# vacuous, and this is the check that refuses it. An unknown kind is a failure,
# not a silent downgrade: a typo in the caller must not weaken the gate.
expectation_shape() {
  local file="$1"
  shift
  awk -v file="$file" -v wanted="$*" '
    BEGIN {
      count = split(wanted, specs, " ")
      for (i = 1; i <= count; i++) {
        split(specs[i], parts, ":")
        name = parts[1]
        want = parts[2]
        if (want == "firing" || want == "both") need_fire[name] = 1
        if (want == "silent" || want == "both") need_silent[name] = 1
        if (want != "firing" && want != "silent" && want != "both") {
          printf "FAIL %s: unknown expectation kind \"%s\" for %s (use firing, silent or both)\n", file, want, name > "/dev/stderr"
          specbad = 1
        }
      }
    }
    /^[[:space:]]+-[[:space:]]+eval_time:/ {
      if (alert != "") record()
      alert = ""
      kind = ""
      next
    }
    /alertname:/ { alert = $2; sub(/^"/, "", alert); sub(/"$/, "", alert) }
    /exp_alerts:[[:space:]]*\[\][[:space:]]*$/ { kind = "silent" }
    /exp_alerts:[[:space:]]*$/ { kind = "firing" }
    function record() {
      if (kind == "firing") fired[alert] = 1
      if (kind == "silent") silent[alert] = 1
    }
    END {
      record()
      bad = specbad
      for (name in need_fire) {
        if (need_fire[name] && !fired[name]) {
          printf "FAIL %s: no firing assertion for %s\n", file, name > "/dev/stderr"
          bad = 1
        }
        if (need_silent[name] && !silent[name]) {
          printf "FAIL %s: no silent assertion for %s (a gate that cannot fail is not a gate)\n", file, name > "/dev/stderr"
          bad = 1
        }
      }
      exit bad
    }
  ' "$file"
}

# bucket_family prints the `Buckets:` registration line of the overhead metric,
# resolved from the metric definition rather than assumed. The family name is
# what the check then resolves to a literal.
bucket_family() {
  local metric_file fetch
  metric_file="$(grep -rl 'Name: *"ibex_proxy_overhead_seconds"' "$METRICS_DIR" --include='*.go' |
    grep -v '_test\.go$' | head -n 1)"
  [[ -n "$metric_file" ]] || return 1
  fetch="$(awk '
    /Name:[[:space:]]*"ibex_proxy_overhead_seconds"/ { seen = 1 }
    seen && /Buckets:/ { print; exit }
  ' "$metric_file")"
  [[ -n "$fetch" ]] || return 1
  printf '%s\n' "$fetch"
}

# bucket_literal prints the source block that declares the bucket family.
bucket_literal() {
  local buckets_line="$1" family literal="" file
  family="$(sed -n 's/.*Buckets:[[:space:]]*\([A-Za-z_][A-Za-z0-9_]*\).*/\1/p' <<<"$buckets_line")"
  if [[ -n "$family" ]]; then
    for file in "$METRICS_DIR"/*.go; do
      literal="$(awk -v name="$family" '
        $0 ~ ("^[[:space:]]*(var[[:space:]]+)?" name "[[:space:]]*=[[:space:]]*\\[\\]float64\\{") { grab = 1 }
        grab { print }
        grab && /\}/ { exit }
      ' "$file")"
      [[ -n "$literal" ]] && break
    done
    [[ -n "$literal" ]] || return 1
    printf '%s\n' "$literal"
    return 0
  fi
  # Inline literal: read from the Buckets: line to the closing brace.
  awk '
    /Buckets:[[:space:]]*\[\]float64\{/ { grab = 1 }
    grab { print }
    grab && /\}/ { exit }
  ' <<<"$buckets_line"
}

# bucket_bounds reduces a bucket-family source block to one float per line: the
# bounds are what is between the first `{` and the first `}` outside a comment.
bucket_bounds() {
  awk '
    {
      line = $0
      sub(/\/\/.*/, "", line)
      if (!inside) {
        at = index(line, "{")
        if (at == 0) next
        line = substr(line, at + 1)
        inside = 1
      }
      if ((at = index(line, "}")) > 0) {
        print substr(line, 1, at - 1)
        exit
      }
      print line
    }
  ' <<<"$1" | grep -oE '[-+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]+)?' || true
}

# rendered_le_labels prints the le= values Prometheus stores for a set of bucket
# bounds, in sorted order, including +Inf.
#
# The rendering is not reimplemented here. The program below renders the bounds
# through client_golang's own text encoder — the code path Prometheus scrapes —
# and independently through strconv.FormatFloat(bound, 'g', -1, 64). It prints
# the client result only when both agree, so the gate is anchored to the library
# instead of to a remembered formatting rule. That matters because the Go literal
# 0.020 and the stored label 0.02 are different strings, and a rule that quotes
# the literal matches nothing.
rendered_le_labels() {
  local bounds="$1" program="$TMP_DIR/render_bucket_labels.go" output err
  command -v go >/dev/null 2>&1 ||
    no_verdict "no Go toolchain on PATH: check 3 renders bucket labels through client_golang, and an unrendered label set cannot be verified"
  cat >"$program" <<'GO'
// render_bucket_labels prints the le= label client_golang emits for each bucket
// bound read from stdin, one float per line. It cross-checks the client encoder
// against strconv.FormatFloat(bound, 'g', -1, 64) and refuses to answer when the
// two disagree, so a client upgrade that changes the rendering shows up as a gate
// failure instead of an inert alert.
package main

import (
	"bufio"
	"fmt"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/common/expfmt"
)

func readBounds() ([]float64, error) {
	var bounds []float64
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		bound, err := strconv.ParseFloat(line, 64)
		if err != nil {
			return nil, fmt.Errorf("not a bucket bound: %q", line)
		}
		bounds = append(bounds, bound)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if len(bounds) == 0 {
		return nil, fmt.Errorf("no bucket bounds on stdin")
	}
	return bounds, nil
}

// clientLabels is the label set Prometheus actually stores: the histogram is
// gathered and encoded with the text exposition format, then le= is lifted out.
func clientLabels(bounds []float64) ([]string, error) {
	histogram := prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_label_render_probe_seconds",
		Help:    "Renders bucket labels for the SLO rule gate.",
		Buckets: bounds,
	})
	registry := prometheus.NewRegistry()
	if err := registry.Register(histogram); err != nil {
		return nil, err
	}
	histogram.Observe(0)
	families, err := registry.Gather()
	if err != nil {
		return nil, err
	}
	var buf strings.Builder
	encoder := expfmt.NewEncoder(&buf, expfmt.NewFormat(expfmt.TypeTextPlain))
	for _, family := range families {
		if err := encoder.Encode(family); err != nil {
			return nil, err
		}
	}
	seen := make(map[string]bool)
	var labels []string
	for _, line := range strings.Split(buf.String(), "\n") {
		at := strings.Index(line, `le="`)
		if at < 0 {
			continue
		}
		rest := line[at+len(`le="`):]
		end := strings.Index(rest, `"`)
		if end < 0 {
			continue
		}
		label := rest[:end]
		if !seen[label] {
			seen[label] = true
			labels = append(labels, label)
		}
	}
	sort.Strings(labels)
	return labels, nil
}

// strconvLabels is the same rendering spelled out, used to prove the client has
// not changed the rule under us. The client always emits a +Inf bucket and it is
// not a bound, so it is added here to keep the two sets comparable.
func strconvLabels(bounds []float64) []string {
	labels := make([]string, 0, len(bounds)+1)
	for _, bound := range bounds {
		switch {
		case math.IsInf(bound, 1):
			continue
		case math.IsNaN(bound):
			labels = append(labels, "NaN")
		default:
			labels = append(labels, strconv.FormatFloat(bound, 'g', -1, 64))
		}
	}
	if len(bounds) > 0 {
		labels = append(labels, "+Inf")
	}
	sort.Strings(labels)
	return labels
}

func main() {
	bounds, err := readBounds()
	if err != nil {
		fmt.Fprintf(os.Stderr, "render_bucket_labels: %v\n", err)
		os.Exit(2)
	}
	client, err := clientLabels(bounds)
	if err != nil {
		fmt.Fprintf(os.Stderr, "render_bucket_labels: client encoder: %v\n", err)
		os.Exit(2)
	}
	strconvRendered := strconvLabels(bounds)
	if strings.Join(client, ",") != strings.Join(strconvRendered, ",") {
		fmt.Fprintf(os.Stderr,
			"render_bucket_labels: client_golang renders [%s] but strconv.FormatFloat('g', -1) renders [%s]; the label the SLO rules must select has changed\n",
			strings.Join(client, " "), strings.Join(strconvRendered, " "))
		os.Exit(3)
	}
	for _, label := range client {
		fmt.Println(label)
	}
}
GO
  output="$(printf '%s\n' "$bounds" | (cd "$ROOT_DIR" && go run "$program") 2>"$TMP_DIR/render.err")" || {
    err="$(cat "$TMP_DIR/render.err")"
    printf '%s\n' "$err" >&2
    return 1
  }
  [[ -n "$output" ]] || return 1
  printf '%s\n' "$output"
}

# slo_le_selectors prints every le= value the rule file selects. Comments count:
# quoting the wrong label in the header would teach the next editor the wrong
# string, which is how the original defect survived review.
slo_le_selectors() {
  grep -oE 'le="[^"]*"' "$1" 2>/dev/null | sed -e 's/^le="//' -e 's/"$//' | sort -u || true
}

# check_le_labels reports (on stderr) every le= selector in the rule file that is
# not a label the client renders, and exits non-zero when there is one. It is
# pure: it does not touch FAILURES, so the self-test can run it on a mutant.
check_le_labels() {
  local file="$1" rendered="$2" label bad=0 count=0
  while IFS= read -r label; do
    [[ -n "$label" ]] || continue
    count=$((count + 1))
    if ! grep -qxF -- "$label" <<<"$rendered"; then
      printf 'FAIL %s: selector le="%s" is not a label the Prometheus client renders for this histogram (rendered: %s)\n' \
        "$(basename "$file")" "$label" "$(tr '\n' ' ' <<<"$rendered")" >&2
      bad=1
    fi
  done < <(slo_le_selectors "$file")
  if [[ "$count" -eq 0 ]]; then
    printf 'FAIL %s: selects no le= bucket at all; the bad-share expression needs the 20 ms bucket and an unselected bucket makes every ratio empty\n' \
      "$(basename "$file")" >&2
    bad=1
  fi
  return "$bad"
}

# --- 0. Inputs ---------------------------------------------------------------
[[ -f "$SLO_HEADER_RULES" ]] || no_verdict "missing $SLO_HEADER_RULES"
[[ -f "$PROBE_TEST" && -f "$BURN_TEST" ]] || no_verdict "missing a rule unit test under $UNIT_TEST_DIR"
[[ -d "$METRICS_DIR" ]] || no_verdict "missing $METRICS_DIR"

select_runner
note "runner: $RUNNER_KIND"
if [[ "$RUNNER_KIND" == "local promtool" ]]; then
  note "promtool: $("${PROMTOOL_CMD[@]}" version 2>/dev/null | head -n 1)"
else
  note "image: $(prometheus_image)"
fi

# --- 1. Parse every rule file ------------------------------------------------
mapfile -t files < <(rule_files)
[[ "${#files[@]}" -gt 0 ]] || no_verdict "no rule files under $RULES_DIR"
rule_args=()
for file in "${files[@]}"; do rule_args+=("$(to_runner_path "$file")"); done

if parse_output="$("${PROMTOOL_CMD[@]}" check rules "${rule_args[@]}" 2>&1)"; then
  printf '%s\n' "$parse_output" | sed 's/^/  /'
  total_rules="$(printf '%s\n' "$parse_output" |
    sed -n 's/^[[:space:]]*SUCCESS: \([0-9][0-9]*\) rules found$/\1/p' |
    awk '{sum += $1} END {print sum + 0}')"
  [[ "$total_rules" -gt 0 ]] || fail "promtool parsed no rules"
  pass "promtool check rules: ${#files[@]} files, $total_rules rules"
else
  printf '%s\n' "$parse_output" | sed 's/^/  /' >&2
  fail "promtool check rules rejected the rule tree"
fi

# --- 2. Severity, summary and runbook on every SLO alert ----------------------
slo_files=()
for file in "${files[@]}"; do
  case "$(basename "$file")" in
  *slo*) slo_files+=("$file") ;;
  esac
done
[[ "${#slo_files[@]}" -gt 0 ]] || fail "no SLO rule file matched *slo* under $RULES_DIR"
if [[ "${#slo_files[@]}" -gt 0 ]]; then
  if coverage_output="$(alert_coverage "${slo_files[@]}" 2>&1)"; then
    pass "SLO alerts carry severity + summary + runbook (${#slo_files[@]} files)"
  else
    printf '%s\n' "$coverage_output" | sed 's/^/  /' >&2
    fail "an SLO alert is missing a routing severity, a summary, or a runbook"
  fi
fi

# --- 3. The labels the ratio rules select ------------------------------------
# The contract is not "some file mentions 0.020": it is that every le= in the
# rule file is a label the client renders for the bucket family wired to
# ibex_proxy_overhead_seconds. A grep for the Go literal passes on the exact rule
# that cannot match production.
buckets_line="$(bucket_family)" || buckets_line=""
if [[ -z "$buckets_line" ]]; then
  fail "cannot find ibex_proxy_overhead_seconds' histogram registration under packages/metrics, so the bucket labels the ratio rules read cannot be verified (fail closed: an unverified label makes both burn alerts inert)"
  RENDERED_LE=""
else
  literal="$(bucket_literal "$buckets_line")" || literal=""
  if [[ -z "$literal" ]]; then
    fail "cannot resolve the bucket family declared by '$buckets_line' to a literal under packages/metrics"
    RENDERED_LE=""
  else
    bounds="$(bucket_bounds "$literal")"
    if [[ -z "$bounds" ]]; then
      fail "the bucket family wired to ibex_proxy_overhead_seconds resolved to no numeric bound (source: $(tr '\n' ' ' <<<"$literal"))"
      RENDERED_LE=""
    else
      if ! RENDERED_LE="$(rendered_le_labels "$bounds")"; then
        fail "cannot render the bucket labels of ibex_proxy_overhead_seconds: the label-rendering probe failed (see its message above)"
        RENDERED_LE=""
      fi
    fi
  fi
fi

if [[ -n "$RENDERED_LE" ]]; then
  family_name="$(sed -n 's/.*Buckets:[[:space:]]*\([A-Za-z_][A-Za-z0-9_]*\).*/\1/p' <<<"$buckets_line")"
  note "rendered bucket labels for ibex_proxy_overhead_seconds (${family_name}): $(tr '\n' ' ' <<<"$RENDERED_LE")"
fi

if [[ -n "$RENDERED_LE" ]]; then
  if label_output="$(check_le_labels "$SLO_HEADER_RULES" "$RENDERED_LE" 2>&1)"; then
    pass "every le= selector in $(basename "$SLO_HEADER_RULES") is a rendered bucket label: $(slo_le_selectors "$SLO_HEADER_RULES" | tr '\n' ' ')"
  else
    printf '%s\n' "$label_output" | sed 's/^/  /' >&2
    fail "an SLO rule selects a bucket label the Prometheus client never writes, so its expression matches no series"
  fi

  # Self-mutation: revert the selectors to the Go literal on a copy. The check
  # must reject it, and name the mismatch. This is the regression QA found, run
  # as a test so the check cannot degrade into a grep that always passes.
  # Build the mutant by transformation rather than by hard-coding the bad string:
  # appending a trailing zero to every bucket label turns the rendered label into
  # the Go literal (0.02 -> 0.020). That is exactly the shape of the defect, and
  # this gate then contains no copy of the string it forbids.
  label_mutant="$TMP_DIR/ibex-slo.reverted-literal.yml"
  sed -E 's/(le=")([^"]+)"/\1\20"/g' "$SLO_HEADER_RULES" >"$label_mutant"
  if cmp -s "$SLO_HEADER_RULES" "$label_mutant"; then
    fail "self-test could not build the label mutant: $(basename "$SLO_HEADER_RULES") has no le= selector to transform, so the mutation is vacuous"
  elif mutant_output="$(check_le_labels "$label_mutant" "$RENDERED_LE" 2>&1)"; then
    fail "self-test: a reverted selector (le=\"0.020\", the Go literal) was accepted; the label check cannot catch the defect it exists for"
  else
    pass "self-test: a rule reverted to the Go literal is rejected — $(head -n 1 <<<"$mutant_output")"
  fi
fi

# --- 4. Expectation shape: firing and silent assertions both survive ---------
if expectation_output="$(expectation_shape "$BURN_TEST" "$FAST_BURN_SPEC" "$SLOW_BURN_SPEC" 2>&1)"; then
  pass "$(basename "$BURN_TEST") keeps firing and silent assertions for the burn alerts"
else
  printf '%s\n' "$expectation_output" | sed 's/^/  /' >&2
  fail "the burn unit test no longer proves a negative outcome"
fi
if expectation_output="$(expectation_shape "$PROBE_TEST" "$PROBE_SPEC" 2>&1)"; then
  pass "$(basename "$PROBE_TEST") keeps a firing assertion for $PROBE_ALERT"
else
  printf '%s\n' "$expectation_output" | sed 's/^/  /' >&2
  fail "the constant burn probe is no longer asserted to fire"
fi

# Self-mutation: strip every silent expectation from a copy. `both` requires the
# negative half, so the check must fail. Without this, "both" could silently
# collapse back into "firing only" and nobody would notice until an alert
# regression had no test that could fail.
silent_mutant="$TMP_DIR/ibex-slo-burn.no-silent.test.yml"
grep -v 'exp_alerts: \[\]' "$BURN_TEST" >"$silent_mutant" || true
if grep -q 'exp_alerts: \[\]' "$silent_mutant"; then
  fail "self-test could not build the silent mutant: $(basename "$BURN_TEST") has no silent expectation to delete"
elif mutant_output="$(expectation_shape "$silent_mutant" "$FAST_BURN_SPEC" "$SLOW_BURN_SPEC" 2>&1)"; then
  fail "self-test: deleting every silent expectation still passed; the 'both' requirement is not enforcing a negative assertion"
else
  pass "self-test: 'both' rejects a test file with every silent expectation deleted — $(head -n 1 <<<"$mutant_output")"
fi

# --- 5. Synthetic burn: the shipped rules against the rendered labels --------
mapfile -t test_files < <(find "$UNIT_TEST_DIR" -maxdepth 1 -type f -name '*.test.yml' -print | sort)
[[ "${#test_files[@]}" -gt 0 ]] || no_verdict "no promtool unit tests under $UNIT_TEST_DIR"
test_args=()
for file in "${test_files[@]}"; do test_args+=("$(to_runner_path "$file")"); done
if test_output="$("${PROMTOOL_CMD[@]}" test rules "${test_args[@]}" 2>&1)"; then
  printf '%s\n' "$test_output" | sed 's/^/  /'
  pass "promtool test rules: 30 of 60 observations over 20 ms on the le=\"0.02\" label produce a 50x burn rate and fire both burn alerts, 1% share stays silent, a recovering burn does not page, and a missing SLI with traffic raises the absence alert"
  pass "constant probe $PROBE_ALERT evaluates to a firing alert with no traffic"
else
  printf '%s\n' "$test_output" | sed 's/^/  /' >&2
  fail "promtool test rules rejected the synthetic burn expectations"
fi

# --- Verdict -----------------------------------------------------------------
if [[ "$FAILURES" -gt 0 ]]; then
  printf 'slo-rules-check: %d check(s) failed\n' "$FAILURES" >&2
  exit 1
fi
note "passed"
