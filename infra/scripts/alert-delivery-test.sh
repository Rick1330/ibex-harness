#!/usr/bin/env bash
# Prove that IBEX alerts reach a real webhook receiver (P0-19 / W6.2).
#
# What this verifies, end to end:
#   1. Prometheus evaluates the shipped rule tree and fires two constant probes
#      (severity=page and severity=ticket).
#   2. The shipped routing tree in infra/monitoring/alertmanager/alertmanager.yml
#      sends each one to its own webhook path.
#   3. A sink records the delivery as JSONL, and the record carries this run's
#      nonce label.
#
# The Alertmanager config under test is the committed file, rendered with the
# documented receiver-base substitution (see
# infra/monitoring/alertmanager/README.md). Rendering is required because
# the pinned Alertmanager 0.27.0 has no --config.expand-env flag.
#
# Anti-forgery: the probe rules are rendered into $TMP_DIR with a random
# `run_nonce` label, and every assertion requires that nonce inside the sink
# record. The committed rules file stays static; a peer that can reach the sink
# but does not know the nonce cannot make the test pass.
#
# Exposure: the sink runs as a compose service on the test network and publishes
# no host port. The absent port is not the control, and the bind address is not
# either (`IBEX_ALERT_SINK_BIND=0.0.0.0` listens on every address in the
# container's netns):
#   * rootless podman: verified unreachable from the host (connection
#     refused/timeout; the rootless bridge gateway cannot be bound from the host
#     at all, EADDRNOTAVAIL, and a host loopback bind is refused from the
#     container).
#   * rootful Docker: not equivalent — the container IP can be reachable from the
#     host or a routed peer.
#   * the per-run nonce is the control, and it is partial: it defeats a peer that
#     can reach only the sink, not one that can also read Prometheus
#     /api/v1/rules, which serves the nonce label.
# Stated in full in infra/monitoring/alertmanager/README.md §"Local test".
#
# Everything it starts is removed on exit, including on failure.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_DIR="$ROOT_DIR/infra/compose/observability"
BASE_COMPOSE="$COMPOSE_DIR/docker-compose.yml"
TEST_COMPOSE="$COMPOSE_DIR/docker-compose.alerting-test.yml"
AM_CONFIG="$ROOT_DIR/infra/monitoring/alertmanager/alertmanager.yml"
PROBE_RULES_SRC="$ROOT_DIR/infra/monitoring/prometheus/rules/test"
PROJECT=ibex-alerting-test
AM_IMAGE=docker.io/prom/alertmanager@sha256:e13b6ed5cb929eeaee733479dce55e10eb3bc2e9c4586c705a4e8da41e5eacf5
PAGE_ALERT=IbexAlertDeliveryProbePage
TICKET_ALERT=IbexAlertDeliveryProbeTicket

PROM_PORT="${IBEX_ALERT_TEST_PROM_PORT:-19190}"
AM_PORT="${IBEX_ALERT_TEST_ALERTMANAGER_PORT:-19193}"
# In-network port of the sink. No host port is published for it (see above).
SINK_PORT="${IBEX_ALERT_SINK_PORT:-18099}"
TIMEOUT="${IBEX_ALERT_TEST_TIMEOUT:-180}"
# Optional: copy the sink JSONL somewhere durable before the temp dir is removed
# (CI artifacts, a PR comment). Unset by default: nothing is left behind.
EVIDENCE_DIR="${IBEX_ALERT_TEST_EVIDENCE_DIR:-}"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ibex-alert-delivery.XXXXXX")"
SINK_DIR="$TMP_DIR/sink"
SINK_OUT="$SINK_DIR/alerts.jsonl"
SINK_READY="$SINK_DIR/sink.ready"
RENDERED_RULES="$TMP_DIR/rules"
RENDERED_AM="$TMP_DIR/alertmanager.yml"
# 128-bit nonce, rendered into the probe rules for this run only.
RUN_NONCE="$(od -An -v -N16 -tx1 /dev/urandom | tr -d ' \n')"
COMPOSE_UP=0
COMPOSE_CMD=()
RUNTIME=()
# Set by podman_engine(): plain `podman`, or `sudo -n podman` for the rootful
# store. Declared here so every reader sees the same name as COMPOSE_CMD.
PODMAN_BIN=()


compose_down() {
  "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
    down -v --remove-orphans
}

leftover_containers() {
  local filter="label=com.docker.compose.project=$PROJECT"
  "${RUNTIME[@]}" ps -a --filter "$filter" --format '{{.Names}}' 2>/dev/null || true
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "$COMPOSE_UP" == 1 ]]; then
    if [[ "$status" -ne 0 ]]; then
      echo "alert-delivery-test: collecting container log tails" >&2
      "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
        logs --no-color --tail 40 alertmanager 2>&1 | sed 's/^/  am| /' >&2 || true
      "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
        logs --no-color --tail 20 alert-receiver 2>&1 | sed 's/^/  sink| /' >&2 || true
    fi
    # Rootless podman intermittently fails the first stop of a rootless netns
    # ("kill network process: permission denied"). Retry once before reporting.
    local down_out
    if ! down_out="$(compose_down 2>&1)" && ! down_out="$(compose_down 2>&1)"; then
      echo "alert-delivery-test: compose down failed twice:" >&2
      printf '%s\n' "$down_out" | sed 's/^/  down| /' >&2
    fi
    if [[ -n "$(leftover_containers)" ]]; then
      echo "alert-delivery-test: containers from this test are still present: $(leftover_containers | tr '\n' ' ')" >&2
      [[ "$status" -eq 0 ]] && status=1
    fi
  fi
  if [[ -n "$EVIDENCE_DIR" && -s "$SINK_OUT" ]]; then
    mkdir -p "$EVIDENCE_DIR" && cp "$SINK_OUT" "$EVIDENCE_DIR/alert-delivery-sink.jsonl" || true
  fi
  rm -rf "$TMP_DIR"
  exit "$status"
}
# Teardown is bound to EXIT only, so it runs for every path: success, failure,
# and the signal handlers below. The handlers must not let the script fall
# through to the assertions (which could still pass and exit 0): each exits with
# the conventional status, and that exit runs the EXIT trap, so cleanup still
# happens exactly once.
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${#RUN_NONCE}" -ne 32 ]]; then
  echo "alert-delivery-test: could not generate a run nonce (got '${RUN_NONCE}')" >&2
  exit 2
fi

# podman_engine sets PODMAN_BIN to the invocation that owns the containers:
# plain podman for a rootless install, `sudo -n podman` when the rootful store
# is requested with IBEX_PODMAN_SUDO=1. Every engine call in this script
# (compose, run, ps) must use the same choice, or it looks in the wrong store.
#
# Rootful selection is opt-in only. The scripts that share this lever
# (dev-tool.sh, observability-up.sh, observability-down.sh) also guess the store
# from a rootless/rootful probe; this test does not, because it starts the
# containers it inspects, so there is no pre-existing store to match and
# IBEX_PODMAN_SUDO=1 is the single, explicit lever.
podman_engine() {
  if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]]; then
    PODMAN_BIN=(sudo -n podman)
  else
    PODMAN_BIN=(podman)
  fi
}

# no_runtime is the single message for "nothing here can run compose": one exit
# path, one status, and the caller never has to guess which probe failed.
no_runtime() {
  echo "alert-delivery-test: no usable Docker or Podman compose runtime" >&2
  exit 2
}

detect_compose() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    RUNTIME=(docker)
    return
  fi
  command -v podman >/dev/null 2>&1 || no_runtime
  podman_engine
  # Probe the engine that was selected, not whichever store the current user
  # happens to reach.
  if ! "${PODMAN_BIN[@]}" info >/dev/null 2>&1; then
    if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]]; then
      echo "alert-delivery-test: IBEX_PODMAN_SUDO=1 selects the rootful podman store, but 'sudo -n podman info' failed; passwordless sudo is required for that store" >&2
      exit 2
    fi
    no_runtime
  fi
  RUNTIME=("${PODMAN_BIN[@]}")
  if "${PODMAN_BIN[@]}" compose version >/dev/null 2>&1; then
    COMPOSE_CMD=("${PODMAN_BIN[@]}" compose)
    return
  fi
  command -v podman-compose >/dev/null 2>&1 || no_runtime
  # podman-compose has no lever for `sudo -n podman`: it would run Compose in
  # the rootless store while this script inspects and tears down the rootful
  # one. Refuse the combination instead of splitting the run across two stores.
  if ((${#PODMAN_BIN[@]} > 1)); then
    echo "alert-delivery-test: refusing podman-compose with the rootful podman store (IBEX_PODMAN_SUDO=1): podman-compose cannot target that store. Install the podman compose provider or unset IBEX_PODMAN_SUDO" >&2
    exit 2
  fi
  COMPOSE_CMD=(podman-compose)
}

render_config() {
  # Documented render step: replace the in-network placeholder host:port with
  # the receiver host:port for this environment. Scheme and paths are kept as
  # written in the committed file. The host is the sink service on the test
  # network, and SINK_PORT keeps the substitution non-trivial so the mechanism
  # itself is exercised.
  sed "s|alert-receiver:8080|alert-receiver:${SINK_PORT}|g" \
    "$AM_CONFIG" >"$RENDERED_AM"
  if [[ "$SINK_PORT" != "8080" ]] && grep -q "alert-receiver:8080" "$RENDERED_AM"; then
    echo "alert-delivery-test: render step left the placeholder base in place" >&2
    exit 1
  fi
  if ! grep -q "alert-receiver:${SINK_PORT}/alerts/page" "$RENDERED_AM"; then
    echo "alert-delivery-test: render step did not produce the sink base" >&2
    exit 1
  fi
}

render_rules() {
  # Copy the committed probe rules into the temp dir and tag every page/ticket
  # probe with this run's nonce. The committed file is never modified.
  local files=() src expected injected
  shopt -s nullglob
  files=("$PROBE_RULES_SRC"/*.yml)
  shopt -u nullglob
  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "alert-delivery-test: no probe rules under $PROBE_RULES_SRC" >&2
    exit 1
  fi
  mkdir -p "$RENDERED_RULES"
  expected="$(grep -hcE '^[[:space:]]+severity:[[:space:]]*(page|ticket)[[:space:]]*$' "${files[@]}" |
    awk '{total += $1} END {print total + 0}' || true)"
  if [[ "$expected" -lt 1 ]]; then
    echo "alert-delivery-test: no severity:page|ticket label in $PROBE_RULES_SRC to tag" >&2
    exit 1
  fi
  for src in "${files[@]}"; do
    awk -v nonce="$RUN_NONCE" '
      /^[[:space:]]+severity:[[:space:]]*(page|ticket)[[:space:]]*$/ {
        match($0, /^[[:space:]]+/)
        print
        printf "%*srun_nonce: %s\n", RLENGTH, "", nonce
        next
      }
      { print }
    ' "$src" >"$RENDERED_RULES/$(basename "$src")"
  done
  injected="$(grep -hc "run_nonce: $RUN_NONCE" "$RENDERED_RULES"/*.yml |
    awk '{total += $1} END {print total + 0}' || true)"
  if [[ "$injected" -ne "$expected" ]]; then
    echo "alert-delivery-test: nonce injection tagged $injected of $expected probes" >&2
    exit 1
  fi
  echo "ok: rendered $injected probe rules with this run's nonce"
}

check_config() {
  "${RUNTIME[@]}" run --rm -v "$RENDERED_AM:/etc/alertmanager/alertmanager.yml:ro" \
    --entrypoint /bin/amtool "$AM_IMAGE" \
    check-config /etc/alertmanager/alertmanager.yml >/dev/null
  echo "ok: amtool check-config ($AM_IMAGE)"
}

start_sink() {
  # The sink is a compose service with no published port: only this network can
  # reach it, and readiness is a file written after the socket is bound.
  echo "alert-delivery-test: starting the sink (compose service alert-receiver, no host port)"
  COMPOSE_UP=1
  if ! "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
    up -d alert-receiver >"$TMP_DIR/sink-up.log" 2>&1; then
    cat "$TMP_DIR/sink-up.log" >&2
    exit 1
  fi
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if [[ -s "$SINK_READY" ]]; then
      echo "ok: sink listening on alert-receiver:${SINK_PORT} (compose network only)"
      return
    fi
    sleep 0.5
  done
  echo "alert-delivery-test: sink did not become ready" >&2
  "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
    logs --no-color --tail 20 alert-receiver 2>&1 | sed 's/^/  sink| /' >&2 || true
  exit 1
}

wait_http() {
  local url="$1" name="$2" deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "ok: $name ready"
      return
    fi
    sleep 1
  done
  echo "alert-delivery-test: $name not ready at $url" >&2
  exit 1
}

# Prints "<alertname>=<state>" for the two probes, or nothing when absent.
probe_states() {
  python3 - "$PROM_PORT" <<'PY' 2>/dev/null || true
import json, sys, urllib.request
port = sys.argv[1]
wanted = {"IbexAlertDeliveryProbePage", "IbexAlertDeliveryProbeTicket"}
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/rules?type=alert", timeout=3) as r:
        data = json.load(r)
except Exception:
    sys.exit(0)
out = {}
for group in data.get("data", {}).get("groups", []):
    for rule in group.get("rules", []):
        if rule.get("name") in wanted:
            out[rule["name"]] = rule.get("state", "unknown")
for name in sorted(wanted):
    print(f"{name}={out.get(name, 'absent')}")
PY
}

fail_with_state() {
  local message="$1"
  echo "alert-delivery-test: FAIL $message" >&2
  echo "last observed rule state:" >&2
  probe_states | sed 's/^/  rules| /' >&2 || true
  echo "last observed sink contents:" >&2
  if [[ -s "$SINK_OUT" ]]; then
    sed 's/^/  sink| /' "$SINK_OUT" >&2
  else
    echo "  sink| (empty)" >&2
  fi
  exit 1
}

# assert_delivery [--quiet] <alertname> <expected path>
# Passes only when a sink record for <alertname> arrived on <expected path>,
# carries this run's nonce, and no other path carries the same nonce. A record
# without the nonce is not evidence: a peer that can reach the sink cannot guess
# it. Repeated deliveries on the expected path are allowed.
assert_delivery() {
  local quiet=0 alertname="" expected_path=""
  while (($#)); do
    case "$1" in
    --quiet) quiet=1 ;;
    *)
      if [[ -z "$alertname" ]]; then
        alertname="$1"
      else
        expected_path="$1"
      fi
      ;;
    esac
    shift
  done
  if [[ -z "$alertname" || -z "$expected_path" ]]; then
    echo "alert-delivery-test: assert_delivery needs <alertname> <path>" >&2
    return 2
  fi
  python3 - "$SINK_OUT" "$alertname" "$expected_path" "$RUN_NONCE" "$quiet" <<'PY'
import json, os, sys

sink, alertname, expected, nonce, quiet = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == "1"
if not os.path.exists(sink):
    print(f"  {alertname}: NOT DELIVERED (no sink file yet)", file=sys.stderr)
    sys.exit(1)
seen_paths, nonce_paths = [], []
with open(sink, encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        for alert in record.get("alerts", []):
            if alert.get("alertname") != alertname:
                continue
            seen_paths.append(record.get("path"))
            if alert.get("run_nonce") == nonce:
                nonce_paths.append(record.get("path"))
if not seen_paths:
    print(f"  {alertname}: NOT DELIVERED", file=sys.stderr)
    sys.exit(1)
if not nonce_paths:
    print(
        f"  {alertname}: seen at {seen_paths} but no record carries this run's nonce "
        f"(prefix {nonce[:8]}...); forged or stale record refused",
        file=sys.stderr,
    )
    sys.exit(1)
if expected not in nonce_paths:
    print(f"  {alertname}: delivered to {nonce_paths} not {expected}", file=sys.stderr)
    sys.exit(1)
# The set of paths carrying this run's nonce must be exactly {expected}:
# repeated deliveries on the expected path are fine, a second nonce-bearing
# path is not. A record on the expected path does not license a copy elsewhere.
extra_paths = sorted(set(nonce_paths) - {expected})
if extra_paths:
    print(
        f"  {alertname}: delivered to {expected} and also {extra_paths} with this run's nonce "
        f"(prefix {nonce[:8]}...); only {expected} may carry it",
        file=sys.stderr,
    )
    sys.exit(1)
if not quiet:
    print(f"ok: {alertname} -> {expected} (run nonce {nonce[:8]}... present)")
PY
}

detect_compose
render_config
render_rules
check_config

export IBEX_ALERT_TEST_CONFIG_FILE="$RENDERED_AM"
export IBEX_ALERT_TEST_RULES_DIR="$RENDERED_RULES"
export IBEX_ALERT_TEST_SINK_DIR="$SINK_DIR"
export IBEX_ALERT_SINK_PORT="$SINK_PORT"
export IBEX_OBS_PROMETHEUS_PORT="$PROM_PORT"
export IBEX_OBS_ALERTMANAGER_PORT="$AM_PORT"

mkdir -p "$SINK_DIR"
start_sink

echo "alert-delivery-test: starting prometheus + alertmanager (project $PROJECT)"
if ! "${COMPOSE_CMD[@]}" -p "$PROJECT" -f "$BASE_COMPOSE" -f "$TEST_COMPOSE" \
  up -d prometheus alertmanager >"$TMP_DIR/up.log" 2>&1; then
  cat "$TMP_DIR/up.log" >&2
  exit 1
fi

wait_http "http://127.0.0.1:${PROM_PORT}/-/ready" "prometheus"
wait_http "http://127.0.0.1:${AM_PORT}/-/ready" "alertmanager"

echo "alert-delivery-test: waiting for both probes to fire (timeout ${TIMEOUT}s)"
deadline=$((SECONDS + TIMEOUT))
while ((SECONDS < deadline)); do
  states="$(probe_states)"
  if grep -q '^IbexAlertDeliveryProbePage=firing$' <<<"$states" &&
    grep -q '^IbexAlertDeliveryProbeTicket=firing$' <<<"$states"; then
    echo "ok: both probes firing"
    break
  fi
  sleep 2
done
if ! grep -q '^IbexAlertDeliveryProbePage=firing$' <<<"$(probe_states)" ||
  ! grep -q '^IbexAlertDeliveryProbeTicket=firing$' <<<"$(probe_states)"; then
  fail_with_state "probes did not reach firing within ${TIMEOUT}s"
fi

echo "alert-delivery-test: waiting for both webhook deliveries"
# Fresh budget: group_wait is 30s, so delivery follows firing by design.
deadline=$((SECONDS + TIMEOUT))
while ((SECONDS < deadline)); do
  if assert_delivery --quiet "$PAGE_ALERT" /alerts/page 2>/dev/null &&
    assert_delivery --quiet "$TICKET_ALERT" /alerts/digest 2>/dev/null; then
    break
  fi
  sleep 2
done

assert_delivery "$PAGE_ALERT" /alerts/page ||
  fail_with_state "page probe not routed to /alerts/page with this run's nonce"
assert_delivery "$TICKET_ALERT" /alerts/digest ||
  fail_with_state "ticket probe not routed to /alerts/digest with this run's nonce"

echo "alert-delivery-test passed (both deliveries carry run nonce ${RUN_NONCE:0:8}...)"
