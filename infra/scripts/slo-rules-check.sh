#!/usr/bin/env bash
# Gate the IBEX SLO rule tier (W6.3).
#
#   bash infra/scripts/slo-rules-check.sh     # or: make slo-rules-check
#
# Six checks, in order, and every one of them can fail:
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
#   4. Population. The ratified objective measures the proxy with context
#      assembly disabled, so every selector on ibex_proxy_overhead_seconds and on
#      the eligible-traffic counter ibex_proxy_nonstreaming_requests_total, in an
#      SLO rule file, must pin assembly="disabled". A selector that omits the pin
#      grades the assembly-enabled workload against a number that never described
#      it (that request legitimately pays for the Context Assemble RPC), and a
#      ratio that pins only one side divides one population by the other. The
#      check reads expression bodies only, because the header, the summaries and
#      the descriptions name these metrics in prose. A self-mutation strips the
#      pin from a copy and requires the check to reject it.
#   5. Expectation shape. The unit-test files must keep both a firing and a
#      silent assertion. `both` means both: the silent half used to be dead code
#      (the caller passed "both", the parser compared against "silent"), so
#      deleting every negative expectation still exited 0. A bare `exp_alerts:`
#      key is not an assertion either: it counts only when an expected-alert
#      entry follows, so `Alert:` with nothing under it is an empty list spelled
#      the other way round. Two self-mutations prove it — one deletes every
#      silent expectation, the other deletes every positive entry from a copy —
#      and both must be rejected.
#   6. Synthetic burn. `promtool test rules` evaluates the shipped rule file
#      against a synthetic histogram carrying the *rendered* labels: a 50% share
#      over 20 ms must produce a 50x burn rate and fire both burn alerts, a 1%
#      share must fire neither, a recovering burn must not page, a 6-minute
#      burst inside an otherwise clean hour must breach the 5m window without
#      breaching the 1h window and must stay silent, an SLI that is missing or
#      frozen while the proxy serves eligible traffic must raise the absence
#      alert, and an idle stack must not. A constant probe in rules/test/ is
#      asserted to fire on its first evaluation with no traffic at all. Every
#      synthetic series carries assembly="disabled", and the on-budget case also
#      carries an assembly="enabled" series with a 100% over-budget share, so a
#      rule that lost the population pin would burn there and fail the test.
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
# Re-indents captured checker output under the check that produced it. One
# definition, because the same sed expression spelled out at every call site is
# what SonarQube shell:S1192 flags (and what one future edit gets wrong).
INDENT_FILTER='s/^/  /'
# The SLO histogram and the eligible-traffic counter share one population, so
# the population check scans both by name (see check_population).
POPULATION_METRIC_RE='ibex_proxy_(overhead_seconds(_bucket|_count|_sum)?|nonstreaming_requests_total)'
POPULATION_PIN='assembly="disabled"'

FAILURES=0
fail() { printf 'slo-rules-check: FAIL %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }
pass() { printf 'slo-rules-check: ok %s\n' "$*"; }
note() { printf 'slo-rules-check: %s\n' "$*"; }
no_verdict() { printf 'slo-rules-check: cannot verify %s\n' "$*" >&2; exit 2; }
# file_count renders "1 file" or "2 files" for a message, so no call site has to
# hand-roll the plural.
file_count() {
  if [[ "$#" -eq 1 ]]; then
    printf '1 file'
  else
    printf '%d files' "$#"
  fi
}

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
  local tool="$1"
  "$tool" version 2>/dev/null |
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
# A firing assertion is an `exp_alerts:` key followed by at least one
# `- exp_annotations:`/`- exp_labels:` entry. The key on its own is not one:
# `IbexProxyOverheadFastBurn:` with nothing under it means "no alerts", is valid
# YAML (null), and used to satisfy the firing half of `both` — a test that
# asserted nothing passed the gate. Only a following entry promotes the key from
# pending to firing, and an explicit `exp_alerts: []` stays a silent assertion.
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
      pending = 0
      next
    }
    /alertname:/ { alert = $2; sub(/^"/, "", alert); sub(/"$/, "", alert); pending = 0 }
    /exp_alerts:[[:space:]]*\[\][[:space:]]*$/ { kind = "silent"; pending = 0 }
    # A bare key is pending, not firing: it becomes an assertion only when an
    # expected-alert entry actually follows it. An empty list spelled `[]` is
    # the genuine silent assertion and is handled above.
    /exp_alerts:[[:space:]]*$/ { kind = ""; pending = 1 }
    pending && /^[[:space:]]+-[[:space:]]+(exp_annotations|exp_labels):/ { kind = "firing"; pending = 0 }
    function record() {
      if (kind == "firing") fired[alert] = 1
      if (kind == "silent") silent[alert] = 1
      kind = ""
      pending = 0
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
  local block="$1"
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
  ' <<<"$block" | grep -oE '[-+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]+)?' || true
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
  local file="$1"
  grep -oE 'le="[^"]*"' "$file" 2>/dev/null | sed -e 's/^le="//' -e 's/"$//' | sort -u || true
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

# check_population reports (on stderr) every selector in a production SLO rule
# file that reads the SLI histogram or the eligible-traffic counter without
# pinning assembly="disabled", and exits non-zero when there is one. Like
# check_le_labels it is pure: it does not touch FAILURES, so the self-test can
# run it on a mutant.
#
# Only `expr: |` bodies are scanned. The header comment, the alert summaries and
# the descriptions name these metrics in prose, and a prose mention is not a
# selector; scanning the whole file would demand a label set inside a sentence.
#
# The pin is compared as a whole label, not as a substring: the selector's label
# set is split on commas and one element must equal assembly="disabled". That
# accepts `{assembly="disabled"}` and `{assembly="disabled",le="0.02"}` and
# rejects `{le="0.02"}`, `{}`, and any future `assembly="enabled"` by
# construction. Across all files it must find at least one pinned selector: a
# scan that matches nothing proves nothing.
check_population() {
  awk -v metric_re="$POPULATION_METRIC_RE" -v pin="$POPULATION_PIN" \
    -v context_group="ibex.slo.context_memory" -v context_pin='assembly="enabled"' '
    function indent(line) { match(line, /^[[:space:]]*/); return RLENGTH }
    function pinned_in(tail, want,   labels, parts, count, i) {
      if (substr(tail, 1, 1) != "{") return 0
      if (index(tail, "}") == 0) return 0
      labels = substr(tail, 2, index(tail, "}") - 2)
      count = split(labels, parts, ",")
      for (i = 1; i <= count; i++) {
        if (parts[i] == want) return 1
      }
      return 0
    }
    # The ratified overhead population is assembly="disabled" everywhere. The
    # one exception is the context/memory group-owned eligible-traffic guard, which
    # is deliberately assembly="enabled": it is the population whose SLI can go
    # missing. Every other group still has to pin the ratified population, so a
    # new group cannot read the overhead histogram or the counter unpinned.
    function required_pin(metric) {
      if (metric == "ibex_proxy_nonstreaming_requests_total" && group == context_group) return context_pin
      return pin
    }
    function analyse(body, nr,   rest, at, metric, tail, want) {
      rest = body
      while ((at = match(rest, metric_re)) > 0) {
        metric = substr(rest, RSTART, RLENGTH)
        tail = substr(rest, RSTART + RLENGTH)
        want = required_pin(metric)
        if (pinned_in(tail, want)) {
          pinned++
          if (want == pin) pinned_disabled++
        } else {
          printf "FAIL %s:%d: selector %s does not pin the required population (expected %s in its label set)\n", FILENAME, nr, metric, want > "/dev/stderr"
          bad = 1
        }
        rest = tail
      }
    }
    /^[[:space:]]*-[[:space:]]+name:[[:space:]]*/ { group = $3; next }
    {
      if (in_body && $0 !~ /^[[:space:]]*$/ && indent($0) <= body_indent) in_body = 0
      if ($0 ~ /^[[:space:]]*expr:[[:space:]]*\|[[:space:]]*$/) {
        in_body = 1
        body_indent = indent($0)
        next
      }
      if (in_body && $0 !~ /^[[:space:]]*$/) analyse($0, FNR)
    }
    END {
      if (pinned_disabled == 0) {
        printf "FAIL %s: selects none of the SLI metrics with %s, so the population check would be vacuous\n", FILENAME, pin > "/dev/stderr"
        bad = 1
      }
      exit bad
    }
  ' "$@"
}

# check_context_memory reports (on stderr) every selector in the
# ibex.slo.context_memory group that does not pin the population it belongs to,
# and exits non-zero when there is one. The group records two SLIs whose targets
# are unratified (05-request-lifecycle-and-slos.md §Timing policy), so this check
# is about *which* series each rule reads, not about a threshold:
#   * the context-assembly SLI reads ibex_proxy_context_assemble_seconds, which
#     carries no assembly label;
#   * its traffic guard reads ibex_proxy_nonstreaming_requests_total pinned to
#     assembly="enabled" — the population whose SLI can go missing;
#   * the memory SLI and its guard both pin route="/v1/memories/search", so a
#     different route cannot satisfy the retrieval assertion.
# It also requires the absence alert to subtract the advancing targets with
# `unless on(job, instance)`. The alert is the only place where the guard and the
# SLI meet, and the pairing has to be per scrape target: `and on()` with no
# shared labels collapses the guard into one global match, so a single proxy
# whose histogram advances keeps the alert silent for a proxy whose histogram is
# missing. A body that reads both the histogram and the enabled guard without
# that exclusion is rejected.
# Like check_population it is pure: it does not touch FAILURES, so the
# self-tests can run it on a mutant.
check_context_memory() {
  awk '
    function indent(line) { match(line, /^[[:space:]]*/); return RLENGTH }
    # close_body ends the expression body being scanned and, when it is the
    # context-assembly absence alert, requires the per-target exclusion. The
    # histogram alone is the recording rule (no guard), so the requirement is
    # keyed on both selectors appearing in the same body.
    function close_body() {
      if (!in_body) return
      if (body_context && body_guard && !body_unless) {
        printf "FAIL %s:%d: context-assembly absence rule selects ibex_proxy_context_assemble_seconds and the assembly=\"enabled\" guard without \"unless on(job, instance)\"; an and-on() guard matches every target at once, so one advancing proxy silences the alert for a proxy whose histogram is missing\n", FILENAME, body_line > "/dev/stderr"
        bad = 1
      }
      in_body = 0
      body_context = body_guard = body_unless = 0
    }
    function label_set(tail,   end) {
      if (substr(tail, 1, 1) != "{") return ""
      end = index(tail, "}")
      if (end == 0) return ""
      return substr(tail, 2, end - 2)
    }
    function has_label(labels, want,   parts, count, i) {
      count = split(labels, parts, ",")
      for (i = 1; i <= count; i++) if (parts[i] == want) return 1
      return 0
    }
    function analyse(body, nr,   rest, at, metric, labels) {
      rest = body
      while ((at = match(rest, /ibex_(proxy_(context_assemble_seconds|nonstreaming_requests_total)|memory_http_(request_duration_seconds|requests_total))/)) > 0) {
        metric = substr(rest, RSTART, RLENGTH)
        rest = substr(rest, RSTART + RLENGTH)
        if (match(rest, /^(_bucket|_count|_sum)/)) rest = substr(rest, RLENGTH + 1)
        labels = label_set(rest)
        if (metric == "ibex_proxy_context_assemble_seconds") {
          context++
          body_context = 1
        } else if (metric == "ibex_proxy_nonstreaming_requests_total") {
          if (has_label(labels, "assembly=\"enabled\"")) { guard++; body_guard = 1 }
          else {
            printf "FAIL %s:%d: context-assembly traffic guard %s must pin assembly=\"enabled\"\n", FILENAME, nr, metric > "/dev/stderr"
            bad = 1
          }
        } else if (metric == "ibex_memory_http_request_duration_seconds") {
          if (has_label(labels, "route=\"/v1/memories/search\"")) { memory++ }
          else {
            printf "FAIL %s:%d: memory-retrieval selector %s must pin route=\"/v1/memories/search\"\n", FILENAME, nr, metric > "/dev/stderr"
            bad = 1
          }
        } else if (metric == "ibex_memory_http_requests_total") {
          if (has_label(labels, "route=\"/v1/memories/search\"")) { memory_guard++ }
          else {
            printf "FAIL %s:%d: memory-retrieval traffic guard %s must pin route=\"/v1/memories/search\"\n", FILENAME, nr, metric > "/dev/stderr"
            bad = 1
          }
        }
      }
    }
    /^[[:space:]]*-[[:space:]]+name:[[:space:]]*/ { close_body(); group = $3; next }
    {
      if (in_body && $0 !~ /^[[:space:]]*$/ && indent($0) <= body_indent) close_body()
      if ($0 ~ /^[[:space:]]*expr:[[:space:]]*\|[[:space:]]*$/) {
        close_body()
        in_body = 1
        body_indent = indent($0)
        body_line = FNR
        body_context = body_guard = body_unless = 0
        next
      }
      if (in_body && $0 !~ /^[[:space:]]*$/) {
        if ($0 ~ /^[[:space:]]*unless[[:space:]]+on[[:space:]]*\(job,[[:space:]]*instance\)[[:space:]]*$/) body_unless = 1
        if (group == "ibex.slo.context_memory") analyse($0, FNR)
      }
    }
    END {
      close_body()
      if (context == 0) {
        printf "FAIL %s: no ibex_proxy_context_assemble_seconds selector in the ibex.slo.context_memory group\n", FILENAME > "/dev/stderr"
        bad = 1
      }
      if (guard == 0) {
        printf "FAIL %s: no assembly=\"enabled\" traffic guard in the ibex.slo.context_memory group\n", FILENAME > "/dev/stderr"
        bad = 1
      }
      if (memory == 0) {
        printf "FAIL %s: no ibex_memory_http_request_duration_seconds selector pinned to the search route\n", FILENAME > "/dev/stderr"
        bad = 1
      }
      if (memory_guard == 0) {
        printf "FAIL %s: no ibex_memory_http_requests_total traffic guard pinned to the search route\n", FILENAME > "/dev/stderr"
        bad = 1
      }
      exit bad
    }
  ' "$@"
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
  printf '%s\n' "$parse_output" | sed "$INDENT_FILTER"
  total_rules="$(printf '%s\n' "$parse_output" |
    sed -n 's/^[[:space:]]*SUCCESS: \([0-9][0-9]*\) rules found$/\1/p' |
    awk '{sum += $1} END {print sum + 0}')"
  [[ "$total_rules" -gt 0 ]] || fail "promtool parsed no rules"
  pass "promtool check rules: ${#files[@]} files, $total_rules rules"
else
  printf '%s\n' "$parse_output" | sed "$INDENT_FILTER" >&2
  fail "promtool check rules rejected the rule tree"
fi

# --- 2. Severity, summary and runbook on every SLO alert ----------------------
slo_files=()
for file in "${files[@]}"; do
  case "$(basename "$file")" in
  *slo*) slo_files+=("$file") ;;
  *) : ;; # every other rule file is covered by check 1; its alerts are not SLO alerts
  esac
done
[[ "${#slo_files[@]}" -gt 0 ]] || fail "no SLO rule file matched *slo* under $RULES_DIR"
if [[ "${#slo_files[@]}" -gt 0 ]]; then
  if coverage_output="$(alert_coverage "${slo_files[@]}" 2>&1)"; then
    pass "SLO alerts carry severity + summary + runbook (${#slo_files[@]} files)"
  else
    printf '%s\n' "$coverage_output" | sed "$INDENT_FILTER" >&2
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
    printf '%s\n' "$label_output" | sed "$INDENT_FILTER" >&2
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

# --- 4. Population: every SLO selector pins assembly="disabled" --------------
# The ratified objective is measured with context assembly disabled, and the
# histogram carries an `assembly` label, so the population is a property of the
# selector. Nothing else in the expression can tell the two workloads apart:
# an unpinned selector mixes in requests whose overhead legitimately includes
# the Context Assemble RPC, and a ratio that pins only one of its terms divides
# one population by the other. Both read as a healthy or an unhealthy SLO
# depending on which way the mix moves, which is why this is a gate and not a
# comment.
# rules/test/ holds probes and promtool unit tests; a probe is not a production
# SLO rule and does not have to read the SLI at all.
production_slo_files=()
for file in "${slo_files[@]}"; do
  case "$file" in
  "$TEST_DIR"/*) : ;; # probe rules, covered by check 1 and check 6
  *) production_slo_files+=("$file") ;;
  esac
done
if [[ "${#production_slo_files[@]}" -eq 0 ]]; then
  fail "no production SLO rule file matched *slo* outside $TEST_DIR"
elif population_output="$(check_population "${production_slo_files[@]}" 2>&1)"; then
  pass "every SLO selector pins the ratified population assembly=\"disabled\" ($(file_count "${production_slo_files[@]}"))"
else
  printf '%s\n' "$population_output" | sed "$INDENT_FILTER" >&2
  fail "an SLO expression grades a population the ratified objective does not cover, or divides one population by another"
fi

# Self-mutation: strip the population pin from a copy. The check must reject it
# and name the selector. Built by transformation, so this gate contains no copy
# of the unpinned selector it forbids.
population_mutant="$TMP_DIR/ibex-slo.unpinned-population.yml"
sed -E 's/(ibex_proxy_(overhead_seconds(_bucket|_count|_sum)?|nonstreaming_requests_total))\{assembly="disabled"/\1{/g' \
  "$SLO_HEADER_RULES" >"$population_mutant"
if cmp -s "$SLO_HEADER_RULES" "$population_mutant"; then
  fail "self-test could not build the population mutant: $(basename "$SLO_HEADER_RULES") selects no pinned SLO metric, so the mutation is vacuous"
elif mutant_output="$(check_population "$population_mutant" 2>&1)"; then
  fail "self-test: a selector without assembly=\"disabled\" was accepted; the population check cannot catch the defect it exists for"
else
  pass "self-test: a rule with the population pin removed is rejected — $(head -n 1 <<<"$mutant_output")"
fi

# --- 4b. Context/memory population (W6.3) ------------------------------------
# The unratified group reads a different population from the ratified overhead
# SLO: the context histogram has no assembly label, its absence guard must pin
# assembly="enabled", and the memory SLI/guard must both pin the search route.
# check_context_memory proves each of those, so a later edit cannot silently
# grade the wrong series while the recording rule still returns a number.
# It also proves the absence alert excludes advancing targets per scrape target
# (`unless on(job, instance)`), because that exclusion is what makes a missing
# histogram fire for one proxy while another proxy records the SLI.
if [[ "${#production_slo_files[@]}" -gt 0 ]]; then
  if context_output="$(check_context_memory "${production_slo_files[@]}" 2>&1)"; then
    pass "context/memory SLO selectors pin their populations (context_assemble, memory search route, assembly=\"enabled\" guard) and the absence alert excludes advancing targets per target (unless on(job, instance))"
  else
    printf '%s\n' "$context_output" | sed "$INDENT_FILTER" >&2
    fail "a context/memory SLO selector reads the wrong population or route"
  fi

  # Self-mutation 1: remove the assembly="enabled" pin from the context guard.
  # The check must reject it; otherwise the guard could be removed and the
  # absence alert would page on every profile with assembly disabled.
  context_guard_mutant="$TMP_DIR/ibex-slo.context-guard-unpinned.yml"
  sed -E 's/(ibex_proxy_nonstreaming_requests_total)\{assembly="enabled"\}/\1{}/g' \
    "$SLO_HEADER_RULES" >"$context_guard_mutant"
  if cmp -s "$SLO_HEADER_RULES" "$context_guard_mutant"; then
    fail "self-test could not build the context-guard mutant: the context/memory group has no assembly=\"enabled\" guard to transform"
  elif mutant_output="$(check_context_memory "$context_guard_mutant" 2>&1)"; then
    fail "self-test: a context-assembly traffic guard without assembly=\"enabled\" was accepted; the context check cannot catch the defect it exists for"
  else
    pass "self-test: a context-assembly guard with the population pin removed is rejected — $(head -n 1 <<<"$mutant_output")"
  fi

  # Self-mutation 2: point the memory SLI at another route. The check must
  # reject it, because a hot-cache route's latency is not retrieval latency.
  memory_route_mutant="$TMP_DIR/ibex-slo.memory-route-unpinned.yml"
  sed -E 's#route="/v1/memories/search"#route="/v1/memories/hot"#g' \
    "$SLO_HEADER_RULES" >"$memory_route_mutant"
  if cmp -s "$SLO_HEADER_RULES" "$memory_route_mutant"; then
    fail "self-test could not build the memory-route mutant: the context/memory group has no search-route pin to transform"
  elif mutant_output="$(check_context_memory "$memory_route_mutant" 2>&1)"; then
    fail "self-test: a memory SLI pinned to a non-search route was accepted; the context check cannot catch the defect it exists for"
  else
    pass "self-test: a memory selector pinned to a non-search route is rejected — $(head -n 1 <<<"$mutant_output")"
  fi

  # Self-mutation 3: delete the per-target exclusion from the absence alert. The
  # check must reject it. Without the exclusion the alert can only fire when no
  # target advances the histogram at all, so a single healthy proxy masks a
  # proxy whose context-assembly SLI never appeared — the defect this selector
  # exists to close. Built by transformation, so this gate holds no copy of the
  # expression it forbids.
  context_unless_mutant="$TMP_DIR/ibex-slo.context-unless-missing.yml"
  sed -E '/unless[[:space:]]+on[[:space:]]*\(job,[[:space:]]*instance\)/d' \
    "$SLO_HEADER_RULES" >"$context_unless_mutant"
  if cmp -s "$SLO_HEADER_RULES" "$context_unless_mutant"; then
    fail "self-test could not build the context-unless mutant: $(basename "$SLO_HEADER_RULES") has no 'unless on(job, instance)' clause to delete, so the mutation is vacuous"
  elif mutant_output="$(check_context_memory "$context_unless_mutant" 2>&1)"; then
    fail "self-test: a context-assembly absence rule without 'unless on(job, instance)' was accepted; one advancing proxy would silence the alert for a proxy whose histogram is missing"
  else
    pass "self-test: a context-assembly absence rule without the per-target exclusion is rejected — $(head -n 1 <<<"$mutant_output")"
  fi
fi

# --- 5. Expectation shape: firing and silent assertions both survive ---------
if expectation_output="$(expectation_shape "$BURN_TEST" "$FAST_BURN_SPEC" "$SLOW_BURN_SPEC" 2>&1)"; then
  pass "$(basename "$BURN_TEST") keeps firing and silent assertions for the burn alerts"
else
  printf '%s\n' "$expectation_output" | sed "$INDENT_FILTER" >&2
  fail "the burn unit test no longer proves a negative outcome"
fi
if expectation_output="$(expectation_shape "$PROBE_TEST" "$PROBE_SPEC" 2>&1)"; then
  pass "$(basename "$PROBE_TEST") keeps a firing assertion for $PROBE_ALERT"
else
  printf '%s\n' "$expectation_output" | sed "$INDENT_FILTER" >&2
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

# Self-mutation 2: remove the positive expectations. A bare `exp_alerts:` key
# used to satisfy the firing half of "both" on its own, so a test that asserted
# nothing but kept the key passed the gate. The mutant deletes every expected-
# alert entry and rewrites the now-empty key as `exp_alerts: []` (still valid
# YAML, and a genuine silent assertion), so only the firing half can fail.
bare_mutant="$TMP_DIR/ibex-slo-burn.no-positive.test.yml"
awk '
  function indent(line) { match(line, /^[[:space:]]*/); return RLENGTH }
  skipping {
    if ($0 ~ /^[[:space:]]*$/ || indent($0) > entry_indent) next
    skipping = 0
  }
  /^[[:space:]]+-[[:space:]]+eval_time:/ { bare = 0 }
  /^[[:space:]]+exp_alerts:[[:space:]]*$/ {
    match($0, /^[[:space:]]*/)
    print substr($0, 1, RLENGTH) "exp_alerts: []"
    bare = 1
    next
  }
  bare && /^[[:space:]]+-[[:space:]]+(exp_annotations|exp_labels):/ {
    entry_indent = indent($0)
    skipping = 1
    bare = 0
    next
  }
  { print }
' "$BURN_TEST" >"$bare_mutant"
if grep -qE '^[[:space:]]+exp_alerts:[[:space:]]*$' "$bare_mutant"; then
  fail "self-test could not build the positive-entry mutant: a bare exp_alerts: key survived the transformation"
elif mutant_output="$(expectation_shape "$bare_mutant" "$FAST_BURN_SPEC" "$SLOW_BURN_SPEC" 2>&1)"; then
  fail "self-test: deleting every positive exp_alerts entry still passed; a bare exp_alerts: key is being counted as a firing assertion"
else
  pass "self-test: a bare exp_alerts: key is not a firing assertion — $(head -n 1 <<<"$mutant_output")"
fi

# --- 6. Synthetic burn: the shipped rules against the rendered labels --------
mapfile -t test_files < <(find "$UNIT_TEST_DIR" -maxdepth 1 -type f -name '*.test.yml' -print | sort)
[[ "${#test_files[@]}" -gt 0 ]] || no_verdict "no promtool unit tests under $UNIT_TEST_DIR"
test_args=()
for file in "${test_files[@]}"; do test_args+=("$(to_runner_path "$file")"); done
if test_output="$("${PROMTOOL_CMD[@]}" test rules "${test_args[@]}" 2>&1)"; then
  printf '%s\n' "$test_output" | sed "$INDENT_FILTER"
  pass "promtool test rules: 30 of 60 observations over 20 ms on the le=\"0.02\" label produce a 50x burn rate and fire both burn alerts; 1% share stays silent with a 100% assembly-enabled series present; a recovering burn does not page; a 6m burst inside a clean hour breaches the 5m window and not the 1h window, so the fast burn stays silent; a missing or frozen SLI with eligible traffic raises the absence alert; an idle stack does not; the context-assembly and memory-retrieval absence alerts fire only while their guarded traffic exists"
  pass "constant probe $PROBE_ALERT evaluates to a firing alert with no traffic"
else
  printf '%s\n' "$test_output" | sed "$INDENT_FILTER" >&2
  fail "promtool test rules rejected the synthetic burn expectations"
fi

# --- Verdict -----------------------------------------------------------------
if [[ "$FAILURES" -gt 0 ]]; then
  printf 'slo-rules-check: %d check(s) failed\n' "$FAILURES" >&2
  exit 1
fi
note "passed"
