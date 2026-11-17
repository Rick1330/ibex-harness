#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_MIGRATE="$ROOT_DIR/infra/scripts/db-migrate.sh"
CH_MIGRATE="$ROOT_DIR/infra/scripts/clickhouse-migrate.sh"
PROTO_DIR="$ROOT_DIR/packages/proto"
DEV_COMPOSE="$ROOT_DIR/infra/compose/dev/docker-compose.yml"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"
TEST_COMPOSE="$ROOT_DIR/infra/compose/test/docker-compose.yml"
TEST_ENV="$ROOT_DIR/infra/compose/test/.env.example"
OBS_COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
OBS_ENV="$ROOT_DIR/infra/compose/observability/.env.example"
V1_COMPOSE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"
# The supported profile uses its own operator-owned .env (0600) under
# infra/compose/v1-single-node so development credentials cannot leak in.
V1_ENV="$ROOT_DIR/infra/compose/v1-single-node/.env"
MANIFEST="$ROOT_DIR/infra/tool-versions.conf"
# benchmarks/scripts/check_reproducibility.py fails closed when jsonschema is
# absent, so the gate must not inherit whatever the system interpreter happens to
# have. This venv is provisioned once from the hash-locked requirement file CI
# installs, and every wheel hash is verified on the way in.
REPRO_VENV="$ROOT_DIR/.cache/reproducibility-venv"
REPRO_REQUIREMENTS="$ROOT_DIR/.github/requirements/jsonschema.txt"
PROTO_BREAKING_AGAINST="${PROTO_BREAKING_AGAINST:-https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto}"

source "$MANIFEST"

if command -v cygpath >/dev/null 2>&1 && [[ -n "${LOCALAPPDATA:-}" ]]; then
  export PATH="$(cygpath -u "$LOCALAPPDATA")/Microsoft/WinGet/Links:$PATH"
fi

require_tool() {
  local tool="$1" message="$2"
  command -v "$tool" >/dev/null 2>&1 || { echo "$message" >&2; exit 1; }
}

runtime() {
  local requested="${IBEX_RUNTIME:-auto}"
  case "$requested" in
    docker)
      require_tool docker 'Docker CLI is missing. Install Docker Desktop/Engine and Compose v2.'
      docker compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 is unavailable.' >&2; exit 1; }
      echo docker ;;
    podman)
      require_tool podman 'Podman is missing. Install Podman and podman-compose.'
      if podman compose version >/dev/null 2>&1; then echo podman
      elif command -v podman-compose >/dev/null 2>&1; then echo podman-compose
      else echo 'Podman Compose is missing. Install podman-compose.' >&2; exit 1; fi ;;
    auto)
      if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then echo docker
      elif command -v podman >/dev/null 2>&1 && (podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1); then
        if podman compose version >/dev/null 2>&1; then echo podman; else echo podman-compose; fi
      else echo 'No supported container runtime found. Install Docker Compose v2 or Podman + podman-compose.' >&2; exit 1; fi ;;
    *) echo "IBEX_RUNTIME must be docker, podman, or auto (got $requested)" >&2; exit 2 ;;
  esac
}

# podman_engine prints the podman invocation that owns the containers: plain
# podman for a rootless install, `sudo -n podman` when the rootful store is in
# use. Every engine call (compose, inspect, run) must use the same choice, or it
# looks in the wrong store.
podman_engine() {
  if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]] || {
    [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)" == true ]] &&
    sudo -n podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -qx false
  }; then
    echo 'sudo -n podman'
  else
    echo podman
  fi
}

compose() {
  case "$(runtime)" in
    docker) docker compose "$@" ;;
    podman)
      local -a podman_bin
      read -r -a podman_bin <<<"$(podman_engine)"
      "${podman_bin[@]}" compose "$@" ;;
    podman-compose)
      # podman-compose selects its engine with --podman-path, a single
      # executable; it has no lever for `sudo -n podman`. Refuse the rootful
      # combination instead of running Compose in the rootless store while the
      # health check inspects the rootful one.
      local -a podman_bin
      read -r -a podman_bin <<<"$(podman_engine)"
      if (( ${#podman_bin[@]} > 1 )); then
        echo 'podman-compose cannot target the rootful podman store; install the podman compose provider or run as the store owner' >&2
        return 2
      fi
      podman-compose "$@" ;;
    *) echo "unsupported container runtime: $(runtime)" >&2; return 2 ;;
  esac
}

compose_files() {
  local kind="$1"
  case "$kind" in
    dev) printf '%s\n' -f "$DEV_COMPOSE" --env-file "$DEV_ENV" ;;
    test) printf '%s\n' -f "$TEST_COMPOSE" --env-file "$TEST_ENV" ;;
    observability) printf '%s\n' -f "$OBS_COMPOSE" --env-file "$OBS_ENV" ;;
    v1) printf '%s\n' -f "$V1_COMPOSE" --env-file "$V1_ENV" ;;
    *) echo "unknown compose stack: $kind" >&2; return 2 ;;
  esac
}

compose_with_mode() {
  local kind="$1"; shift
  local args=()
  if [[ "$kind" == v1 && "${IBEX_NETWORK:-bridge}" == host ]]; then
    echo 'IBEX_NETWORK=host is not supported for v1-single-node: the profile publishes only the edge HTTPS port' >&2
    exit 2
  fi
  if [[ "$kind" == v1 && ! -f "$V1_ENV" ]]; then
    echo "missing $V1_ENV; run: make v1-secrets" >&2
    exit 1
  fi
  if [[ "$kind" == v1 ]]; then
    # The bootstrap PAT bind mount must exist and be operator-owned before the
    # runtime creates it; otherwise a root-owned directory blocks the one-shot.
    local bootstrap_dir="$ROOT_DIR/infra/compose/v1-single-node/bootstrap"
    if [[ ! -d "$bootstrap_dir" ]]; then
      mkdir -p "$bootstrap_dir" && chmod 0700 "$bootstrap_dir"
    fi
  fi
  if [[ "${IBEX_NETWORK:-bridge}" == host ]]; then
    local overlay="$ROOT_DIR/infra/compose/overlays/host/${kind}.yml"
    [[ -f "$overlay" ]] || { echo "missing host-network overlay: $overlay" >&2; exit 1; }
    args+=( -p "ibex-${kind}" -f "$overlay" --env-file "$ROOT_DIR/infra/compose/${kind}/.env.example" )
  elif [[ "${IBEX_NETWORK:-bridge}" != bridge ]]; then
    echo 'IBEX_NETWORK must be bridge or host' >&2; exit 2
  else
    while IFS= read -r arg; do args+=("$arg"); done < <(compose_files "$kind")
  fi
  compose "${args[@]}" "$@"
}

# container_runtime_bin maps the compose front-end to the engine binary.
# `runtime()` may return `podman-compose`, which is a front-end and has no
# `inspect`/`run` of its own; the engine is always `podman`.
container_runtime_bin() {
  case "$(runtime)" in
    docker) echo docker ;;
    *) podman_engine ;;
  esac
}

v1_wait_healthy() {
  # The default budget covers TEI's two-hour first-start window (compose sets
  # start_period: 7200s); a warm start returns on the first pass.
  local attempts="${IBEX_V1_HEALTH_ATTEMPTS:-3600}" i ids statuses
  local required="postgres redis auth proxy api memory embedder worker context console edge tei"
  local -a engine
  read -r -a engine <<<"$(container_runtime_bin)"
  for ((i = 1; i <= attempts; i++)); do
    if (( i % 60 == 0 )); then
      echo "v1-single-node still starting (${i} of ${attempts} checks); set IBEX_V1_HEALTH_ATTEMPTS to shorten the wait" >&2
    fi
    ids="$(compose_with_mode v1 ps -q 2>/dev/null || true)"
    if [[ -n "$ids" ]]; then
      # `ps --format json` differs between Docker Compose and podman-compose,
      # and podman-compose omits health from it entirely. Asking the runtime
      # keeps one code path for both providers.
      # shellcheck disable=SC2086
      statuses="$("${engine[@]}" inspect --format '{{.Name}}|{{index .Config.Labels "com.docker.compose.service"}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $ids 2>/dev/null || true)"
      if V1_STATUSES="$statuses" V1_REQUIRED="$required" python3 - <<'PY'
import os
import sys

required = os.environ.get("V1_REQUIRED", "").split()
lines = [line for line in os.environ.get("V1_STATUSES", "").splitlines() if line.strip()]
if not lines:
    sys.exit(1)


def service_name(container: str) -> str:
    parts = container.lstrip("/").split("-")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return parts[-1] if parts else container


seen = {}
for line in lines:
    name, _, rest = line.partition("|")
    label, _, health = rest.partition("|")
    seen[label.strip() or service_name(name)] = health.strip().lower()
if any(seen.get(service) != "healthy" for service in required):
    sys.exit(1)
PY
      then
        echo 'v1-single-node services are healthy'
        return 0
      fi
    fi
    sleep 2
  done
  echo 'v1-single-node services did not all become healthy' >&2
  compose_with_mode v1 ps >&2 || true
  return 1
}

# v1_bootstrap_pat_read prints the one-time PAT on stdout. It returns 3 when the
# file is absent (a re-run after the operator consumed it), and 1 when the file
# exists but is not operator-only: a world-readable credential is a refusal, not
# a warning. The banner belongs to v1_bootstrap_pat, so the smoke path can read
# the value without printing it.
v1_bootstrap_pat_read() {
  # The PAT is written by the one-shot into a host bind mount, so it outlives
  # the container. Reading the host file avoids `cp` (which streams a tar
  # archive) and any rootful/rootless container-store mismatch.
  local dir="$ROOT_DIR/infra/compose/v1-single-node/bootstrap"
  local path="$dir/bootstrap.pat" mode
  local -a engine
  if [[ ! -f "$path" ]]; then
    echo "no bootstrap PAT at $path; a first install writes it once during make v1-up" >&2
    return 3
  fi
  mode="$(stat -c %a "$path")"
  if [[ "$mode" != "600" ]]; then
    echo "refusing to read $path: mode $mode, expected 600" >&2
    return 1
  fi
  if [[ -r "$path" ]]; then
    cat "$path"
    return 0
  fi
  # A rootful runtime writes the file as root, so the operator cannot read it
  # directly. Read it through the image that created it: the image runs as uid
  # 10001 by default, so the read needs an explicit root user, and the mount is
  # read-only.
  local -a run_args
  read -r -a engine <<<"$(container_runtime_bin)"
  run_args=("${engine[@]}" run --rm --user 0:0 --entrypoint cat)
  run_args+=(--security-opt label=disable)
  run_args+=(-v "$dir:/run/ibex:ro" ibex-v1-auth:local /run/ibex/bootstrap.pat)
  "${run_args[@]}"
}

v1_bootstrap_pat() {
  local pat rc
  # `! cmd` reports the inverted status, so capture the function's real exit
  # code before testing it. A missing file is exit 3, not a success with no
  # output.
  pat="$(v1_bootstrap_pat_read)" && rc=0 || rc=$?
  if (( rc != 0 )); then
    return "$rc"
  fi
  echo "bootstrap PAT (store it in your secret manager, then delete infra/compose/v1-single-node/bootstrap/bootstrap.pat):" >&2
  printf '%s\n' "$pat"
}

# v1_pg_exec runs one SQL statement against the profile's Postgres through
# Compose, using the profile's own POSTGRES_USER/POSTGRES_DB. It is the only
# way the smoke can resolve the bootstrap org and agent ids without guessing:
# the bootstrap command generates them with uuid.New().
v1_pg_exec() {
  local sql="$1" user db
  user="$(v1_env_value POSTGRES_USER)"; user="${user:-ibex}"
  db="$(v1_env_value POSTGRES_DB)"; db="${db:-ibex}"
  compose_with_mode v1 exec -T postgres psql -U "$user" -d "$db" -Atc "$sql"
}

v1_is_uuid() {
  local value="$1"
  python3 -c 'import sys, uuid
try:
    uuid.UUID(sys.argv[1])
except (ValueError, AttributeError):
    sys.exit(1)
' "$value" 2>/dev/null
}

# v1_smoke_org_id resolves the bootstrap organization id. IBEX_V1_ORG_ID wins so
# an operator can run the smoke against a profile whose slug they changed.
v1_smoke_org_id() {
  local org="${IBEX_V1_ORG_ID:-}" slug
  if [[ -n "$org" ]]; then
    printf '%s\n' "$org"
    return 0
  fi
  slug="$(v1_env_value IBEX_BOOTSTRAP_ORG_SLUG)"; slug="${slug:-ibex}"
  if [[ ! "$slug" =~ ^[a-z0-9-]+$ ]]; then
    echo "refusing to query an invalid organization slug: $slug" >&2
    return 1
  fi
  v1_pg_exec "SELECT id FROM ibex_core.organizations WHERE slug = '$slug' AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
}

v1_smoke_agent_id() {
  local org="$1" slug
  if [[ -n "${IBEX_V1_AGENT_ID:-}" ]]; then
    printf '%s\n' "$IBEX_V1_AGENT_ID"
    return 0
  fi
  slug="$(v1_env_value IBEX_BOOTSTRAP_AGENT_SLUG)"; slug="${slug:-default}"
  if [[ ! "$slug" =~ ^[a-z0-9-]+$ ]]; then
    echo "refusing to query an invalid agent slug: $slug" >&2
    return 1
  fi
  v1_pg_exec "SELECT id FROM ibex_core.agents WHERE org_id = '$org'::uuid AND slug = '$slug' AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
}

v1_edge_port() {
  local port="${IBEX_EDGE_PORT:-}"
  [[ -n "$port" ]] || port="$(v1_env_value IBEX_EDGE_PORT)"
  printf '%s\n' "${port:-443}"
}

v1_edge_ca() {
  printf '%s\n' "$ROOT_DIR/infra/compose/v1-single-node/secrets/ca.crt"
}

# v1_smoke_http is the one curl call the assertion uses. Keeping it separate
# lets the self-test replace `curl` with a stub and exercise the parsing and
# status assertions without a running profile.
#
# A fifth argument makes the call a POST whose request body is that file: it is
# how the chat check sends its JSON payload without putting it in argv. The
# payload is static and non-sensitive, but it travels the same path as the
# token-bearing call, so there is one code path to review.
#
# A sixth argument is a file to dump the response headers into (`curl -D`). The
# chat arm reads the proxy's X-IBEX-Context-* outcome headers from it, because a
# status alone cannot say whether context assembly ran: the proxy is fail-open
# and serves the completion anyway when assembly degrades.
#
# The bootstrap PAT is an admin credential, so it must not appear in curl's
# argv: OpenCode (and any process monitor) logs argv. The bearer header is
# written to a 0600 curl config file and passed with --config; only the file
# path is visible.
#
# The call is bounded. Without --connect-timeout/--max-time a socket that
# accepts the TCP connection and never answers keeps curl waiting forever, and
# the smoke hangs instead of reporting a status. The `|| true` at the call site
# is what preserves the retry behaviour: a timeout leaves the status empty, the
# assertion below reports it as a failed probe, and v1_smoke's own loop decides
# whether to try again — the smoke never dies inside curl.
v1_smoke_http() {
  local url="$1" token="$2" agent="$3" body="$4" payload="${5:-}" headers="${6:-}"
  local -a args=(
    --cacert "$(v1_edge_ca)" -sS
    --connect-timeout 5 --max-time 20
    -o "$body" -w '%{http_code}'
  )
  local cfg="" status
  [[ -n "$headers" ]] && args+=(-D "$headers")
  if [[ -n "$token" ]]; then
    cfg="$(mktemp "${TMPDIR:-/tmp}/ibex-v1-smoke-curl.XXXXXX")"
    chmod 0600 "$cfg"
    printf 'header = "Authorization: Bearer %s"\n' "$token" >"$cfg"
    args+=(--config "$cfg")
  fi
  [[ -n "$agent" ]] && args+=(-H "X-IBEX-Agent-ID: $agent")
  if [[ -n "$payload" ]]; then
    args+=(-X POST -H "Content-Type: application/json" --data-binary "@$payload")
  fi
  status="$(curl "${args[@]}" "$url" || true)"
  [[ -n "$cfg" ]] && rm -f "$cfg"
  printf '%s' "$status"
}

# v1_smoke_body_org asserts the JSON body's org_id equals the requested org.
v1_smoke_body_org() {
  local body="$1" expected="$2"
  python3 - "$body" "$expected" <<'PY'
import json
import sys

path, expected = sys.argv[1], sys.argv[2].strip().lower()
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)
actual = str(payload.get("org_id", "")).strip().lower()
sys.exit(0 if actual == expected else 1)
PY
}

# v1_smoke_body_chat asserts the one thing the exit gate's chat check means: the
# edge answered a completion with a single assistant message. It is deliberately
# narrower than "any 2xx" and narrower than a schema check: an error envelope
# carrying 200, an SSE frame, an empty choices list and an unparseable body all
# fail. The mock provider's non-stream body is that shape
# (packages/provider/mockllm/provider.go: mockJSONBody), and the proxy re-encodes
# the response through packages/responsepipeline without dropping the message.
v1_smoke_body_chat() {
  local body="$1"
  python3 - "$body" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)
if not isinstance(payload, dict):
    sys.exit(1)
choices = payload.get("choices")
if not isinstance(choices, list) or not choices:
    sys.exit(1)
first = choices[0]
message = first.get("message") if isinstance(first, dict) else None
role = message.get("role") if isinstance(message, dict) else None
sys.exit(0 if role == "assistant" else 1)
PY
}

# v1_smoke_context_fallback classifies the chat response's
# X-IBEX-Context-Fallback header. The header is the outcome signal a status
# cannot carry: context assembly is fail-open by design and the proxy answers
# the completion directive-only when the Assemble RPC degrades or comes back
# empty (services/proxy/internal/http/chat_context_assemble.go:149-157), so a
# 200 proves the chat completes and nothing about assembly.
#
# Exit 0: present and "false" — the RPC ran and did not degrade.
# Exit 1: present and "true" — the RPC fail-opened; the completion was served
#         without assembled context.
# Exit 2: absent — Assemble was never attempted, so nothing is proven. The
#         writer returns early while Attempted is false (:359-363), which covers
#         assembly disabled, a Skip-Memory request, a request with no verified
#         principal, and one too incomplete to assemble. The profile takes none
#         of those paths, so absent fails the caller instead of passing blindly.
# Exit 3: present with a value other than true/false — the header contract
#         changed, and this check must not read a drifting value as a pass.
v1_smoke_context_fallback() {
  local headers="$1"
  python3 - "$headers" <<'PY'
import sys
from pathlib import Path

try:
    raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
except OSError:
    sys.exit(2)
values = []
for line in raw.splitlines():
    name, sep, value = line.partition(":")
    if sep and name.strip().lower() == "x-ibex-context-fallback":
        values.append(value.strip().lower())
if not values:
    sys.exit(2)
if "true" in values:
    sys.exit(1)
sys.exit(0 if all(value == "false" for value in values) else 3)
PY
}

# v1_smoke_assert proves the profile serves an authenticated request on the chat
# path — not only the auth-probe — and that the two negative paths stay closed.
# The chat arm accepts a 200 only when the response reports a non-degraded
# context assembly, because the proxy is fail-open and a 200 alone would pass
# while assembly was skipped or degraded.
# It returns 1 instead of exiting so the self-test can assert a failure.
v1_smoke_assert() {
  local base="$1" org="$2" agent="$3" pat="$4" body="$5" status wrong_org
  status="$(v1_smoke_http "$base/v1/orgs/$org/auth-probe" "$pat" "$agent" "$body" || true)"
  [[ "$status" == "200" ]] || { echo "auth-probe with the bootstrap PAT returned $status, want 200" >&2; return 1; }
  v1_smoke_body_org "$body" "$org" || { echo "auth-probe body org_id does not match $org" >&2; return 1; }

  status="$(v1_smoke_http "$base/v1/orgs/$org/auth-probe" "" "$agent" "$body" || true)"
  [[ "$status" == "401" ]] || { echo "auth-probe without a token returned $status, want 401" >&2; return 1; }

  wrong_org="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  status="$(v1_smoke_http "$base/v1/orgs/$wrong_org/auth-probe" "$pat" "$agent" "$body" || true)"
  [[ "$status" == "403" ]] || { echo "auth-probe for a different org returned $status, want 403" >&2; return 1; }

  # The chat path itself. The org is implicit in the token, so there is no org
  # path segment; the agent header selects the agent the request is attributed
  # to, and the request stays non-streaming so the body is JSON.
  #
  # A 200 does not prove context assembly ran. The proxy is fail-open on that
  # path, so a degraded or timed-out assembly still answers the completion
  # (services/proxy/internal/http/chat_context_assemble.go:149-157), which is
  # why the three X-IBEX-Context-* headers exist. They are written only when the
  # Assemble RPC was actually attempted (:359-371), so their absence means the
  # assembly path was skipped rather than that it succeeded quietly.
  #
  # The profile enables assembly (IBEX_CONTEXT_ENABLED: "true",
  # infra/compose/v1-single-node/compose.yml:359), routes chat through the agent
  # verifier that binds the verified principal
  # (services/proxy/internal/http/router_protected.go:168), and wraps every
  # request in a real OTel span
  # (services/proxy/internal/http/router.go:242), so the attempted path is the
  # only one a well-formed chat request can take here. A missing header is
  # therefore a failure: an unproven assembly is not a passing one. `true` is
  # also a failure — the chat path completed by degrading, and the gate says
  # the profile serves the request without that.
  local payload="$body.chat-request.json" headers="$body.chat-headers.txt" hrc=0
  printf '%s' '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}' >"$payload"
  status="$(v1_smoke_http "$base/v1/chat/completions" "$pat" "$agent" "$body" "$payload" "$headers" || true)"
  [[ "$status" == "200" ]] || { echo "chat completion with the bootstrap PAT returned $status, want 200" >&2; return 1; }
  v1_smoke_body_chat "$body" || { echo "chat completion body is not one assistant message (choices[0].message.role)" >&2; return 1; }
  v1_smoke_context_fallback "$headers" || hrc=$?
  case "$hrc" in
    0) ;;
    1) echo "chat completion degraded context assembly (X-IBEX-Context-Fallback: true); the proxy fail-opened to directive-only messages" >&2; return 1 ;;
    2) echo "chat response carried no X-IBEX-Context-Fallback header: context assembly was not attempted, so a 200 does not prove the assembly path ran" >&2; return 1 ;;
    *) echo "chat response carries an unexpected X-IBEX-Context-Fallback value; want true or false" >&2; return 1 ;;
  esac
  return 0
}

# v1_smoke is the O06 proof: an authenticated edge request through Caddy, not a
# static /_edge/health string. It reads the one-time bootstrap PAT (mode 600),
# resolves the org and agent ids from the profile database, then asserts the
# authenticated auth-probe, the 401/403 negatives, and one authenticated chat
# completion that did not degrade context assembly.
#
# A skip is exit 4, never 0: no readable bootstrap PAT means the authenticated
# half of the gate was not exercised, and a caller must not be able to read that
# as a pass. The code is distinct from 1 (a probe ran and failed) and from 2
# (usage). `make v1-smoke` fails on 4; `make v1-up` maps that one code to a
# printed warning so a re-run whose one-time PAT was already consumed still
# starts the profile, and propagates every other failure unchanged.
v1_smoke() {
  local from_up=0
  if [[ "${1:-}" == "--from-up" ]]; then
    from_up=1
    shift
  fi
  local attempts="${IBEX_V1_SMOKE_ATTEMPTS:-15}" i rc=3 pat="" org="" agent="" port base
  for ((i = 1; i <= attempts; i++)); do
    # The assignment inherits the function's status; `|| rc=$?` keeps `set -e`
    # from exiting on the expected "file absent" (3) result.
    pat="$(v1_bootstrap_pat_read 2>/dev/null)" && rc=0 || rc=$?
    if (( rc == 0 )); then
      break
    fi
    if (( rc != 3 )); then
      echo "bootstrap PAT is present but unreadable (mode check failed); fix its mode instead of retrying" >&2
      return 1
    fi
    sleep 2
  done
  if (( rc != 0 )); then
    if (( from_up )); then
      echo "SKIP: bootstrap PAT absent (the one-time credential was already consumed); authenticated v1 liveness is unproven on this run. Run 'make v1-smoke' with the PAT restored to prove it." >&2
    else
      echo "SKIP: cannot prove v1 liveness: no readable bootstrap PAT. Restore the one-time PAT under infra/compose/v1-single-node/bootstrap/ (or re-provision it with 'make v1-provision') and re-run 'make v1-smoke'." >&2
    fi
    return 4
  fi
  # The org/agent lookup and the edge port default to the profile .env. An
  # explicit triple lets the smoke run without it, but a missing .env with any
  # default still needed is a setup error, not a probe failure.
  if [[ ! -f "$V1_ENV" && ( -z "${IBEX_V1_ORG_ID:-}" || -z "${IBEX_V1_AGENT_ID:-}" || -z "${IBEX_EDGE_PORT:-}" ) ]]; then
    echo "missing $V1_ENV; run: make v1-secrets (or set IBEX_V1_ORG_ID, IBEX_V1_AGENT_ID and IBEX_EDGE_PORT)" >&2
    return 1
  fi
  for ((i = 1; i <= attempts; i++)); do
    org="$(v1_smoke_org_id 2>/dev/null || true)"
    if [[ -n "$org" ]] && v1_is_uuid "$org"; then
      agent="$(v1_smoke_agent_id "$org" 2>/dev/null || true)"
      if [[ -n "$agent" ]] && v1_is_uuid "$agent"; then
        break
      fi
    fi
    org="" agent=""
    sleep 2
  done
  if [[ -z "$org" || -z "$agent" ]]; then
    echo "cannot resolve the bootstrap org/agent ids from the profile database; run 'make v1-ps' and 'make v1-logs'" >&2
    return 1
  fi
  port="$(v1_edge_port)"
  base="https://localhost:${port}"
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/ibex-v1-smoke.XXXXXX")"
  if ! v1_smoke_assert "$base" "$org" "$agent" "$pat" "$tmp/body.json"; then
    rm -rf "$tmp"
    return 1
  fi
  rm -rf "$tmp"
  echo "PASS: v1 auth-probe 200 through the edge with the bootstrap PAT (org_id matches $org)"
  echo "PASS: v1 auth-probe 401 without a token"
  echo "PASS: v1 auth-probe 403 for a different org path"
  echo "PASS: v1 chat completion 200 through the edge (choices[0].message.role is assistant, X-IBEX-Context-Fallback is false)"
  return 0
}

# v1_smoke_selftest exercises v1_smoke_assert against a stub curl, so the
# parsing and status assertions are tested even when no profile is running. It
# is the only test of that parser, so every way the chat check can pass
# something the gate must reject has an arm here: a non-200, a 200 whose
# choices[0].message.role is not assistant, a 200 with an empty choices list, a
# 200 whose body is a JSON array rather than an object, a 200 whose body is not
# JSON, and the three assembly outcomes a 200 can carry. The last group is the
# point of the header assertion: a completion is not a pass when the proxy says
# assembly did not run (`true`) or says nothing at all (no header). The accepted
# completion body is the one the mock provider returns
# (packages/provider/mockllm/provider.go: mockJSONBody), so the parser is tested
# against what the profile serves in its current posture.
v1_smoke_selftest() {
  local org="11111111-1111-4111-8111-111111111111"
  local agent="22222222-2222-4222-8222-222222222222"
  local pat="ibex_pat_selftest"
  local stub_chat="ok"
  local stub_chat_body='{"id":"mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}'
  V1_SMOKE_SELFTEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/ibex-v1-smoke-selftest.XXXXXX")"
  # The trap runs at script exit, after this function's locals are gone, so the
  # directory is held in a global and the expansion is guarded.
  trap 'rm -rf "${V1_SMOKE_SELFTEST_TMP:-}"' EXIT
  local tmp="$V1_SMOKE_SELFTEST_TMP"

  # One stub answers both probes. `stub_chat` selects the arm, so each negative
  # case differs from the accepted one by a single value rather than by a copied
  # curl replacement. The token is read from the 0600 config file, which is the
  # path v1_smoke_http actually uses.
  #
  # The chat headers mirror what the proxy writes (chat_context_assemble.go:364-370):
  # the accepted arm carries all three X-IBEX-Context-* headers with fallback
  # `false`, which is what a healthy assembly on the profile produces.
  stub_chat_headers() {
    local status="$1"
    printf 'HTTP/1.1 %s X\r\n' "$status"
    case "$stub_chat" in
      fallback-absent) printf 'X-IBEX-Memories-Injected: 0\r\nX-IBEX-Context-Tokens: 12\r\n' ;;
      fallback-true) printf 'X-IBEX-Memories-Injected: 0\r\nX-IBEX-Context-Tokens: 0\r\nX-IBEX-Context-Fallback: true\r\n' ;;
      fallback-unexpected) printf 'X-IBEX-Context-Fallback: degraded\r\n' ;;
      *) printf 'X-IBEX-Memories-Injected: 0\r\nX-IBEX-Context-Tokens: 12\r\nX-IBEX-Context-Fallback: false\r\n' ;;
    esac
    printf '\r\n'
  }

  stub_curl() {
    local out="" url="" token="" cfg="" hdr="" status=200 body=""
    while (( $# )); do
      case "$1" in
        -o) out="$2"; shift 2 ;;
        -D) hdr="$2"; shift 2 ;;
        --cacert|-w|--connect-timeout|--max-time) shift 2 ;;
        --config) cfg="$2"; shift 2 ;;
        -X|--data-binary|-H) shift 2 ;;
        -sS) shift ;;
        *) url="$1"; shift ;;
      esac
    done
    if [[ -n "$cfg" ]]; then
      token="$(sed -n 's/^header = "Authorization: Bearer \(.*\)"$/\1/p' "$cfg")"
    fi
    if [[ "$url" == *"/v1/chat/completions" ]]; then
      if [[ -z "$token" ]]; then
        status=401; body='{"error":{"code":"MISSING_TOKEN"}}'
      else
        case "$stub_chat" in
          non-200) status=500; body='{"error":{"code":"INTERNAL_ERROR"}}' ;;
          wrong-role) body='{"id":"mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"user","content":"ok"}}]}' ;;
          no-choices) body='{"id":"mock","object":"chat.completion","choices":[]}' ;;
          not-an-object) body='[]' ;;
          malformed) body='{"id":"mock","object":"chat.completion","choices":[' ;;
          *) body="$stub_chat_body" ;;
        esac
      fi
      [[ -n "$hdr" ]] && stub_chat_headers "$status" >"$hdr"
    else
      case "$stub_chat" in
        wrong-org) body='{"org_id":"33333333-3333-4333-8333-333333333333"}' ;;
        *) body="{\"org_id\":\"$org\"}" ;;
      esac
      if [[ "$url" != *"/orgs/$org/auth-probe" ]]; then
        status=403; body='{"error":"forbidden"}'
      elif [[ -z "$token" ]]; then
        status=401; body='{"error":"missing token"}'
      fi
    fi
    [[ -n "$out" ]] && printf '%s' "$body" >"$out"
    printf '%s' "$status"
  }

  if (
    curl() { stub_curl "$@"; }
    v1_smoke_assert "https://stub" "$org" "$agent" "$pat" "$tmp/body.json"
  ); then
    echo "PASS: v1-smoke self-test accepts a 200+matching-org auth-probe, its 401 and 403, and one assistant completion with X-IBEX-Context-Fallback: false"
  else
    echo "FAIL: v1-smoke self-test rejected a well-formed stub" >&2
    return 1
  fi

  # A negative arm passes only when the assertion fails. An accepted stub here
  # is the defect: the parser would let the gate pass on something it must
  # reject.
  assert_rejected() {
    local label="$1"
    if (
      curl() { stub_curl "$@"; }
      v1_smoke_assert "https://stub" "$org" "$agent" "$pat" "$tmp/body.json"
    ) 2>/dev/null; then
      echo "FAIL: v1-smoke self-test accepted $label" >&2
      return 1
    fi
    echo "PASS: v1-smoke self-test rejects $label"
  }

  stub_chat="wrong-org"
  assert_rejected "a mismatched org_id body" || return 1
  stub_chat="non-200"
  assert_rejected "a chat completion whose status is not 200" || return 1
  stub_chat="wrong-role"
  assert_rejected "a 200 chat body whose choices[0].message.role is not assistant" || return 1
  stub_chat="no-choices"
  assert_rejected "a 200 chat body with an empty choices list" || return 1
  stub_chat="not-an-object"
  assert_rejected "a 200 chat body that is a JSON array, not an object" || return 1
  stub_chat="malformed"
  assert_rejected "a 200 chat body that is not valid JSON" || return 1
  stub_chat="fallback-true"
  assert_rejected "a 200 chat completion that reports X-IBEX-Context-Fallback: true (assembly degraded)" || return 1
  stub_chat="fallback-absent"
  assert_rejected "a 200 chat completion that carries no X-IBEX-Context-Fallback header (assembly unproven)" || return 1
  stub_chat="fallback-unexpected"
  assert_rejected "a 200 chat completion whose X-IBEX-Context-Fallback is neither true nor false" || return 1
  return 0
}

# v1_canonical_path prints an absolute, directory-resolved spelling of a path
# without requiring the file itself to exist. readlink -f is not portable (macOS
# has no -f), so the directory is resolved with cd -P and the last component is
# kept as given.
v1_canonical_path() {
  local path="$1" dir
  if ! dir="$(cd "$(dirname "$path")" 2>/dev/null && pwd -P)"; then
    printf '%s\n' "$path"
    return 0
  fi
  printf '%s\n' "$dir/$(basename "$path")"
}

# v1_pgbackrest_conf resolves the repository config the platform scripts use and
# refuses the shipped .example. It is the same path resolution as
# pgbackrest-backup.sh, so the wrapper fails before a destructive restore can
# start.
#
# The .example rejection is by identity, not by file name: the path is resolved
# through its directory, so an absolute path, a relative path, and a symlinked
# parent all compare equal to the template. The template exists on disk, so the
# missing-file check alone would pass it through to pgBackRest with placeholder
# credentials.
v1_pgbackrest_conf() {
  local conf="${PGBACKREST_CONF:-$ROOT_DIR/infra/backup/pgbackrest/pgbackrest.conf}"
  local real="$ROOT_DIR/infra/backup/pgbackrest/pgbackrest.conf"
  local example="$real.example"
  if [[ "$(v1_canonical_path "$conf")" == "$(v1_canonical_path "$example")" ]]; then
    cat >&2 <<EOF
refusing the shipped pgBackRest template as the config: $conf
$example carries placeholder repository settings and no credentials, so a backup
or restore that started here would fail halfway through. Copy it to
$real, fill the credentials, and point PGBACKREST_CONF at that file (or leave
PGBACKREST_CONF unset to use that path by default).
EOF
    return 1
  fi
  if [[ ! -f "$conf" ]]; then
    cat >&2 <<EOF
missing pgBackRest config: $conf
The repository ships only infra/backup/pgbackrest/pgbackrest.conf.example.
Copy it to $real and fill the repository credentials; do not point
PGBACKREST_CONF at the example.
EOF
    return 1
  fi
  printf '%s\n' "$conf"
}

# v1_container_cli prints the engine invocation the platform scripts can exec.
# IBEX_CONTAINER_CLI wins when set; otherwise the selected engine is returned as
# given, including the multi-word `sudo -n podman` a rootful store needs. The
# platform scripts split the value into an argv array, so a multi-word engine is
# passed through consistently instead of being rejected here (that rejection made
# a rootful profile unable to arm archiving at all).
v1_container_cli() {
  if [[ -n "${IBEX_CONTAINER_CLI:-}" ]]; then
    printf '%s\n' "$IBEX_CONTAINER_CLI"
    return 0
  fi
  case "$(runtime)" in
    docker)
      printf 'docker\n'
      return 0 ;;
    *)
      # podman / podman-compose: the podman engine resolution below owns both.
      ;;
  esac
  podman_engine
}

# v1_backup_env exports the repository credentials the restore container needs.
# They live in .env (0600) and are never placed on a command line; the backup
# path does not need them because it execs into the postgres container, which
# already carries them in its environment.
v1_backup_env() {
  PGBACKREST_REPO1_CIPHER_PASS="$(v1_env_value PGBACKREST_REPO1_CIPHER_PASS)"
  PGBACKREST_REPO1_S3_KEY="$(v1_env_value IBEX_OBJECTSTORE_ACCESS_KEY)"
  PGBACKREST_REPO1_S3_KEY_SECRET="$(v1_env_value IBEX_OBJECTSTORE_SECRET_KEY)"
  export PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET
}

# v1_backup_init arms WAL archiving. It runs inside the postgres container
# (the image carries pgBackRest and the stanza config), and stanza-create is
# idempotent, so this is safe on every start.
#
# --soft turns a failure into a warning: a repository outage must not stop the
# profile from serving, and the archive command will retry the WAL it could not
# push. The warning is loud because archiving is not armed until this succeeds.
v1_backup_init() {
  local soft=0 cid cli
  if [[ "${1:-}" == "--soft" ]]; then
    soft=1
    shift
  fi
  # Both hard guards sit inside the soft contract, not before it. `make v1-up`
  # has already built and started every service by the time this arm runs, and
  # its documented behaviour is that a failed arm is printed as a warning; a
  # `return 1` here would make a healthy profile exit non-zero at the last step.
  # The config guard can legitimately fail here (a missing repository config).
  # The engine guard accepts the multi-word `sudo -n podman` a rootful store
  # needs, so a healthy rootful profile is no longer turned into a warning.
  # Strict `make v1-backup-init` still fails loudly through the same guards.
  if ! v1_pgbackrest_conf >/dev/null; then
    if (( soft )); then
      echo "WARNING: pgBackRest config missing or refused; PITR is NOT armed." >&2
      echo "WARNING: fix the config, then run make v1-backup-init." >&2
      return 0
    fi
    return 1
  fi
  if ! cli="$(v1_container_cli)"; then
    if (( soft )); then
      echo "WARNING: pgBackRest container CLI could not be resolved; PITR is NOT armed." >&2
      return 0
    fi
    return 1
  fi
  cid="$(compose_with_mode v1 ps -q postgres 2>/dev/null | head -n1 || true)"
  if [[ -z "$cid" ]]; then
    if (( soft )); then
      echo "WARNING: postgres container not found; pgBackRest stanza not initialised" >&2
      return 0
    fi
    echo "postgres container not found; run make v1-up first" >&2
    return 1
  fi
  if IBEX_CONTAINER_CLI="$cli" PGBACKREST_EXEC_CONTAINER="$cid" \
    bash "$ROOT_DIR/infra/scripts/platform/pgbackrest-backup.sh" stanza-create; then
    return 0
  fi
  if (( soft )); then
    echo "WARNING: pgBackRest stanza-create failed; PITR is NOT armed." >&2
    echo "WARNING: WAL is retained in pg_wal until archiving succeeds. Fix the repository and run make v1-backup-init." >&2
    return 0
  fi
  return 1
}

v1_backup() {
  local type="${1:-full}" cid cli
  case "$type" in
    full|diff|incr|check|stanza-create) : ;;
    *) echo "usage: make v1-backup TYPE=full|diff|incr|check|stanza-create" >&2; return 2 ;;
  esac
  v1_pgbackrest_conf >/dev/null || return 1
  if ! cli="$(v1_container_cli)"; then
    return 1
  fi
  # The backup must run where the cluster is. The v1 postgres image carries
  # pgBackRest and the repository credentials, so the script execs into it
  # instead of talking to the cluster over the network.
  cid="$(compose_with_mode v1 ps -q postgres 2>/dev/null | head -n1 || true)"
  if [[ -z "$cid" ]]; then
    echo "postgres container not found; run make v1-up first" >&2
    return 1
  fi
  IBEX_CONTAINER_CLI="$cli" PGBACKREST_EXEC_CONTAINER="$cid" \
    bash "$ROOT_DIR/infra/scripts/platform/pgbackrest-backup.sh" "$type"
}

# Both restore paths pin the profile's own Compose file. pgbackrest-restore.sh
# defaults COMPOSE_FILE to infra/compose/dev/docker-compose.yml, so without this
# a v1 restore would stop the dev stack's Postgres and resolve the dev volume.
# The v1 file carries `name: ibex-v1-single-node`, and Compose loads .env from
# the Compose file's directory, which is exactly infra/compose/v1-single-node.
#
# The restore runs the profile's own postgres image as uid 999: a root-owned
# restore would leave a data directory the server cannot read, and the image
# already carries the matching pgBackRest version.
v1_restore_env() {
  v1_backup_env
  PGBACKREST_IMAGE="ibex-v1-postgres:local"
  PGBACKREST_RESTORE_USER="postgres"
  IBEX_CONTAINER_CLI="$(v1_container_cli)" || return 1
  COMPOSE_FILE="$V1_COMPOSE"
  export PGBACKREST_IMAGE PGBACKREST_RESTORE_USER IBEX_CONTAINER_CLI COMPOSE_FILE
}

v1_restore() {
  v1_pgbackrest_conf >/dev/null || return 1
  v1_restore_env || return 1
  bash "$ROOT_DIR/infra/scripts/platform/pgbackrest-restore.sh"
}

# v1_pitr_report_path resolves the report a PITR run must leave behind. It sits
# next to the drill's report directory but defaults to the per-user state dir,
# because a non-root operator cannot write /var/lib/ibex. IBEX_PITR_REPORT (or
# `make v1-pitr PITR_REPORT=...`) points it at an evidence directory instead.
v1_pitr_report_path() {
  if [[ -n "${IBEX_PITR_REPORT:-}" ]]; then
    printf '%s\n' "$IBEX_PITR_REPORT"
    return 0
  fi
  printf '%s/ibex/restore-drill/pitr-report.json\n' "${RESTORE_DRILL_REPORT_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}}"
}

# v1_pitr_blocked writes the honest artefact for a run that never reached the
# restore. A missing report is not a pass; a report that says "unavailable,
# blocked by X" is, and the writer refuses one without that reason.
v1_pitr_blocked() {
  local reason="$1" target="$2"
  echo "PITR unavailable: $reason" >&2
  PITR_REPORT="$(v1_pitr_report_path)" \
    PITR_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    PITR_ENVIRONMENT_CLASS="${IBEX_DRILL_ENVIRONMENT_CLASS:-local-${IBEX_RUNTIME:-auto}-pitr}" \
    PITR_MECHANISM=unavailable \
    PITR_TARGET_TIMESTAMP="$target" \
    PITR_BLOCKED_BY="$reason" \
    bash "$ROOT_DIR/infra/scripts/platform/pitr_report.sh"
}

# v1_pitr_clear_previous_report moves a report left by an earlier run out of the
# way, so the only file at $report afterwards is the one this invocation wrote.
#
# The check it replaces compared the report's mtime against the run's start at
# whole-second precision. A retry that started in the same second as the previous
# run satisfied that check with the previous run's file and printed its path as
# though this run had written it. A timestamp cannot identify an invocation; the
# file's presence after this move can.
v1_pitr_clear_previous_report() {
  local report="$1" aside
  [[ -f "$report" ]] || return 0
  aside="$report.previous"
  if ! mv -f -- "$report" "$aside"; then
    echo "cannot move the previous report at $report aside, so this run's report could not be identified" >&2
    return 1
  fi
  echo "pitr report: moved the previous report to $aside" >&2
  return 0
}

# v1_pitr restores to a timestamp. The target is mandatory: without it the
# restore would recover to the end of WAL and could not be called PITR.
# IBEX_PITR_SCRATCH_VOLUME restores beside the live cluster instead of over it.
# Every outcome writes a report through the same writer the drill uses, so
# `make v1-pitr` cannot finish without an artefact that says what happened.
v1_pitr() {
  local target="${1:-}" scratch="${IBEX_PITR_SCRATCH_VOLUME:-}" report
  local status=0
  if [[ -z "$target" ]]; then
    echo "usage: make v1-pitr TARGET=2026-11-14T03:00:00Z" >&2
    echo "       make v1-pitr TARGET=... SCRATCH_VOLUME=<name> (restores beside the live cluster)" >&2
    return 2
  fi
  report="$(v1_pitr_report_path)"
  export IBEX_PITR_REPORT="$report"
  if ! v1_pitr_clear_previous_report "$report"; then
    echo "pitr report=NOT WRITTEN ($report)" >&2
    return 1
  fi
  if ! v1_pgbackrest_conf >/dev/null; then
    v1_pitr_blocked "the pgBackRest repository config is missing or refused (run make v1-secrets, or point PGBACKREST_CONF at a real file)" "$target"
    return 1
  fi
  if ! v1_restore_env; then
    v1_pitr_blocked "the container runtime or profile environment for the v1 profile could not be resolved" "$target"
    return 1
  fi
  PGBACKREST_RESTORE_TARGET="$target"
  PGBACKREST_RESTORE_SCRATCH_VOLUME="$scratch"
  PGBACKREST_RESTORE_REPORT="$report"
  export PGBACKREST_RESTORE_TARGET PGBACKREST_RESTORE_SCRATCH_VOLUME PGBACKREST_RESTORE_REPORT
  bash "$ROOT_DIR/infra/scripts/platform/pgbackrest-restore.sh" || status=$?
  # The path is printed only when this run actually wrote it. The previous
  # report was moved aside above, so a file at $report now belongs to this
  # invocation. A restore whose evidence could not be written has not produced a
  # report, and naming a file left by an earlier run would be worse than saying
  # it is missing.
  if [[ -f "$report" ]]; then
    echo "pitr report=$report"
  else
    echo "pitr report=NOT WRITTEN ($report)" >&2
    if (( status == 0 )); then
      status=1
    fi
  fi
  return "$status"
}

v1_up() {
  local do_build=1
  if [[ "${IBEX_V1_SKIP_BUILD:-0}" == 1 ]]; then
    do_build=0
  fi
  if [[ "${1:-}" == "--no-build" ]]; then
    do_build=0
    shift
  fi
  if (( do_build )); then
    compose_with_mode v1 build
  fi
  if (( do_build )); then
    compose_with_mode v1 up -d "$@"
    return
  fi
  compose_with_mode v1 up -d --no-build "$@"
}

v1_migrate() {
  local do_build=1
  if [[ "${IBEX_V1_SKIP_BUILD:-0}" == 1 ]]; then
    do_build=0
  fi
  if [[ "${1:-}" == "--no-build" ]]; then
    do_build=0
    shift
  fi
  if (( do_build )); then
    compose_with_mode v1 build migrate
  fi
  compose_with_mode v1 run --rm migrate "$@"
}

v1_provision() {
  local do_build=1
  if [[ "${IBEX_V1_SKIP_BUILD:-0}" == 1 ]]; then
    do_build=0
  fi
  if [[ "${1:-}" == "--no-build" ]]; then
    do_build=0
    shift
  fi
  if (( do_build )); then
    # Same Dockerfile as migrate: build both so `run` never hits a missing image.
    compose_with_mode v1 build migrate provision
  fi
  # `run` honours depends_on, so a cold profile runs migrate first and the repair
  # path works without a prior `up`.
  compose_with_mode v1 run --rm provision "$@"
}

v1_down() {
  compose_with_mode v1 down "$@" || {
    echo 'v1 down reported a runtime cleanup error; retrying' >&2
    compose_with_mode v1 down "$@"
  }
}

v1_env_value() {
  local key="$1"
  python3 "$ROOT_DIR/infra/scripts/lib/dotenv.py" "$key" <"$V1_ENV"
}

v1_url() {
  local port="${IBEX_EDGE_PORT:-}" ca
  if [[ -z "$port" ]]; then
    port="$(v1_env_value IBEX_EDGE_PORT)"
  fi
  port="${port:-443}"
  ca="$ROOT_DIR/infra/compose/v1-single-node/secrets/ca.crt"
  for _ in $(seq 1 30); do
    if curl -fsS --cacert "$ca" "https://localhost:${port}/_edge/health" >/dev/null 2>&1; then
      printf 'v1-single-node is up: https://localhost:%s\n' "$port"
      printf '%s\n' 'bootstrap PAT (first install only): make v1-bootstrap-pat'
      return 0
    fi
    sleep 2
  done
  echo 'v1-single-node edge did not answer over the profile CA; run: make v1-logs' >&2
  return 1
}

version_ok() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" || "$actual" == "$expected".* || "$actual" == "$expected"-* ]]; then
    printf 'PASS  %-20s %s\n' "$label" "$actual"; return 0
  fi
  printf 'FAIL  %-20s found=%s expected=%s\n' "$label" "$actual" "$expected"
  return 1
}

check_tools() {
  local failures=0 actual
  actual="$(go version 2>/dev/null | sed -n 's/.*go\([0-9.]*\).*/\1/p')"; version_ok GO_VERSION "$actual" "$GO_VERSION" || failures=$((failures+1))
  actual="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"; version_ok NODE_MAJOR "$actual" "$NODE_MAJOR" || failures=$((failures+1))
  actual="$(pnpm --version 2>/dev/null || true)"; version_ok PNPM_VERSION "$actual" "$PNPM_VERSION" || failures=$((failures+1))
  actual="$(python3 --version 2>/dev/null | awk '{print $2}' | cut -d. -f1-2)"; version_ok PYTHON_VERSION "$actual" "$PYTHON_VERSION" || failures=$((failures+1))
  actual="$(uv --version 2>/dev/null | awk '{print $2}' || true)"; version_ok UV_VERSION "$actual" "$UV_VERSION" || failures=$((failures+1))
  actual="$(buf --version 2>/dev/null || true)"; version_ok BUF_VERSION "$actual" "$BUF_VERSION" || failures=$((failures+1))
  actual="$(gitleaks version 2>/dev/null | head -1 | tr -d '[:space:]')"; version_ok GITLEAKS_VERSION "$actual" "$GITLEAKS_VERSION" || failures=$((failures+1))
  actual="$(golangci-lint version 2>/dev/null | sed -n 's/.*version \([^ ]*\).*/\1/p' | head -1)"; version_ok GOLANGCI_LINT_VERSION "$actual" "$GOLANGCI_LINT_VERSION" || failures=$((failures+1))
  actual="$(gotestsum --version 2>/dev/null | sed -n 's/.*v\([0-9.]*\).*/\1/p')"; version_ok GOTESTSUM_VERSION "$actual" "$GOTESTSUM_VERSION" || failures=$((failures+1))
  if [[ "${IBEX_TEST_MODE:-0}" != 1 ]]; then
    if runtime >/dev/null 2>&1; then
      printf 'PASS  %-20s %s\n' CONTAINER_RUNTIME "$(runtime)"
    else
      echo 'FAIL  CONTAINER_RUNTIME no supported runtime'
      failures=$((failures+1))
    fi
  fi
  if (( failures )); then
    cat >&2 <<'EOF'
check-tools: one or more tools do not match infra/tool-versions.conf.
Remediation: follow the OS-specific installation recipes in engineering/TOOLCHAIN.md,
then rerun `make check-tools`. Do not silently upgrade lockfiles or go.mod.
EOF
    return 1
  fi
  echo 'check-tools: all required tools match the manifest'
}

unset_external_otel() {
  [[ "${IBEX_ALLOW_EXTERNAL_OTEL:-0}" == 1 ]] && return 0
  while IFS='=' read -r name _; do
    case "$name" in
      OTEL_*) unset "$name" ;;
      *) : ;;
    esac
  done < <(env)
}

# reproducibility_python prints the interpreter the reproducibility check runs on:
# the shared venv when it already imports jsonschema, otherwise a fresh one built
# from .github/requirements/jsonschema.txt with --require-hashes. Progress goes to
# stderr so the caller can use the stdout as a path.
reproducibility_python() {
  local python="$REPRO_VENV/bin/python"
  if [[ -x "$python" ]] && "$python" -c 'import jsonschema' >/dev/null 2>&1; then
    printf '%s\n' "$python"
    return 0
  fi
  require_tool python3 'python3 is required to provision the reproducibility venv'
  rm -rf "$REPRO_VENV"
  python3 -m venv "$REPRO_VENV" >&2
  "$REPRO_VENV/bin/python" -m pip install --quiet --disable-pip-version-check \
    --require-hashes --only-binary :all: -r "$REPRO_REQUIREMENTS" >&2
  printf '%s\n' "$python"
}

reproducibility_check() {
  local python
  python="$(reproducibility_python)"
  cd "$ROOT_DIR"
  "$python" benchmarks/scripts/check_reproducibility.py
}

case "${1:-help}" in
  help)
    printf '%s\n' 'IBEX Harness commands:' \
      '  setup                  Provision dependencies, stacks, migrations, and readiness' \
      '  check-tools            Verify installed versions against infra/tool-versions.conf' \
      '  env-doctor             Diagnose runtime, network, ports, DNS, and OTEL variables' \
      '  stack-init [dev|test]  Wait for a stack and create required object-store buckets' \
      '  readiness              Run stack-init readiness probes' \
      '  lint-docs              Run markdownlint' '  security-scan          Run gitleaks locally' \
      '  repo-guards            Run repository layout and hygiene guards (incl. alert routing, schema doc, contract registry, deprecations, SLO rules, OSV waiver floors, reproducibility)' '  proto-lint              Run Buf lint' \
      '  reproducibility-check  Fail when a published benchmark artifact cannot support its claim' \
      '                         Runs on .cache/reproducibility-venv, provisioned once from' \
      '                         .github/requirements/jsonschema.txt with pip --require-hashes' \
      '  slo-rules-check        Parse the Prometheus rules, check SLO alert severity/runbook coverage, and evaluate the synthetic burn' \
      '  proto-breaking         Run Buf breaking checks' '  api-breaking [base]     Diff the OpenAPI snapshot against a git baseline (default origin/main; a tag selects release mode)' \
      '  proto-gen               Generate protobuf stubs' \
      '  proto-test              Run protobuf contract tests' '  test-integration         Run Go integration tests' \
      '  test-integration-auth   Run AuthService-backed proxy integration tests' \
      '  compose-dev-up/down/reset/logs/ps  Manage development stack' \
      '  compose-test-up/down   Manage test stack' '  observability-up/down/smoke  Manage observability' '  alert-delivery-test   Prove alerts reach a real webhook receiver' \
      '  v1-secrets             Generate the v1-single-node .env and file secrets' \
      '  v1-up/down/migrate/provision/logs/ps  Manage the v1-single-node profile (use --no-build for rollback image reuse)' \
      '  v1-smoke               Prove the profile with an authenticated edge request (O06)' \
      '  v1-backup/v1-restore/v1-pitr  pgBackRest backup/restore wrappers (W4.6; PITR needs script support)' \
      '  db-migrate/down/version/seed  Manage Postgres migrations' \
      '  clickhouse-migrate/down/version  Manage ClickHouse migrations' \
      '  test-embedder/test-memory/test-memory-integration/test-worker/test-worker-integration/test-mcp-memory' \
      '  test-clickhouse-migrate/test-clickhouse-migrate-integration' \
      '  dev-smoke/dev-smoke-live/e2e-wave2b-token-fks/verify-phase15/verify-phase25/e2e-phase25/e2e-smoke-p3-memory/mcp-conformance' ;;
  setup) bash "$ROOT_DIR/infra/scripts/setup.sh" "${2:-}" ;;
  check-tools) check_tools ;;
  env-doctor) bash "$ROOT_DIR/infra/scripts/env-doctor.sh" ;;
  stack-init|readiness) bash "$ROOT_DIR/infra/scripts/stack-init.sh" "${2:-dev}" ;;
  lint-docs)
    cd "$ROOT_DIR"
    markdownlint="$ROOT_DIR/.github/markdownlint/node_modules/.bin/markdownlint-cli2"
    if [[ ! -x "$markdownlint" ]]; then
      echo 'markdownlint-cli2 is not installed; run npm ci --prefix .github/markdownlint --ignore-scripts' >&2
      exit 1
    fi
    "$markdownlint" "**/*.md" "#node_modules"
    ;;
  security-scan) cd "$ROOT_DIR"; require_tool gitleaks 'gitleaks is required for security-scan'; gitleaks detect --source . --config .gitleaks.toml --redact --verbose ;;
  # The contract registry and deprecation record guards are the same two steps repo-guards
  # runs in CI. They are stdlib-only and path-independent, so a local edit to a record is
  # checked here instead of only in the python-gated unit suite.
  # osv-scanner's IgnoredVulns is advisory-scoped, so the Nuxt waivers would also
  # suppress the 3.x range. The floor guard and its self-test run with the other
  # static guards: the guard is only worth having if it is proven to bite.
  repo-guards) cd "$ROOT_DIR"; bash .github/scripts/check-repo-layout.sh; bash .github/scripts/check-landing-assets.sh; bash .github/scripts/validate-action-pins.sh; python3 infra/scripts/check-alert-routing.py; python3 infra/scripts/check-schema-doc.py; python3 services/api/scripts/check_contract_registry.py; python3 services/api/scripts/check_deprecations.py; bash infra/scripts/slo-rules-check.sh; bash infra/scripts/test-v1-backup-credentials.sh; python3 infra/scripts/check-tenant-pin.py; python3 infra/scripts/check-osv-waiver-floor.py; python3 infra/scripts/test_check_osv_waiver_floor.py; reproducibility_check ;;
  reproducibility-check) reproducibility_check ;;
  slo-rules-check) cd "$ROOT_DIR"; bash infra/scripts/slo-rules-check.sh ;;
  proto-lint) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf lint ;;
  proto-breaking) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf breaking --against "$PROTO_BREAKING_AGAINST" ;;
  api-breaking) bash "$ROOT_DIR/infra/scripts/api-breaking.sh" "${2:-}" ;;
  proto-gen) require_tool buf 'buf is required'; cd "$PROTO_DIR"; buf generate ;;
  proto-test) cd "$ROOT_DIR"; go test ./packages/proto/... ;;
  proto-test-integration) cd "$PROTO_DIR"; buf generate; cd "$ROOT_DIR"; go test -tags=integration ./packages/proto/... ;;
  test-integration) cd "$ROOT_DIR"; unset_external_otel; export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/14}"; export POSTGRES_TEST_DSN="${POSTGRES_TEST_DSN:-postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable}"; export CLICKHOUSE_TEST_DSN="${CLICKHOUSE_TEST_DSN:-clickhouse://default:ibextest@127.0.0.1:8124/ibex}"; export CLICKHOUSE_TEST_NATIVE_DSN="${CLICKHOUSE_TEST_NATIVE_DSN:-clickhouse://default:ibextest@127.0.0.1:9000?database=ibex}"; export CLICKHOUSE_MIGRATE_DSN="${CLICKHOUSE_MIGRATE_DSN:-${CLICKHOUSE_TEST_NATIVE_DSN}}"; export CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8124}"; export CLICKHOUSE_DB="${CLICKHOUSE_DB:-ibex}"; export CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"; export CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-ibextest}"; export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"; export IBEX_TEST_FAST_ARGON2="${IBEX_TEST_FAST_ARGON2:-1}"; bash "$CH_MIGRATE" up; go test -tags=integration -race -timeout=300s -p "${GO_TEST_P:-1}" -parallel "${GO_TEST_PARALLEL:-1}" ./... ;;
  test-integration-auth) cd "$ROOT_DIR"; unset_external_otel; export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/14}"; export POSTGRES_TEST_DSN="${POSTGRES_TEST_DSN:-postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable}"; export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"; export IBEX_TEST_FAST_ARGON2="${IBEX_TEST_FAST_ARGON2:-1}"; go test -tags=integration -race -timeout=120s -p 1 -parallel "${GO_TEST_PARALLEL:-1}" ./services/auth/... ./services/proxy/... ;;
  compose-dev-up) compose_with_mode dev up -d ;;
  compose-dev-down) compose_with_mode dev down ;;
  compose-dev-reset) compose_with_mode dev down -v; compose_with_mode dev up -d ;;
  compose-dev-logs) compose_with_mode dev logs -f ;;
  compose-dev-ps) compose_with_mode dev ps ;;
  compose-test-up) compose_with_mode test up -d; echo 'compose-test Redis: REDIS_URL=redis://127.0.0.1:6380/14' ;;
  compose-test-down) compose_with_mode test down ;;
  observability-up) compose_with_mode observability up -d ;;
  observability-down) compose_with_mode observability down ;;
  observability-smoke) bash "$ROOT_DIR/infra/scripts/observability-smoke.sh" ;;
  alert-delivery-test) bash "$ROOT_DIR/infra/scripts/alert-delivery-test.sh" ;;
  db-migrate) bash "$DB_MIGRATE" up ;;
  db-migrate-down) bash "$DB_MIGRATE" down ;;
  db-version) bash "$DB_MIGRATE" version ;;
  db-seed) bash "$ROOT_DIR/infra/scripts/db-seed.sh" ;;
  db-repair-token-fks) bash "$ROOT_DIR/infra/scripts/db-repair-token-fks.sh" ;;
  clickhouse-migrate) bash "$CH_MIGRATE" up ;;
  clickhouse-migrate-down) bash "$CH_MIGRATE" down ;;
  clickhouse-version) bash "$CH_MIGRATE" version ;;
  test-clickhouse-migrate) bash "$ROOT_DIR/infra/scripts/clickhouse-migrate-test-ci.sh" ;;
  test-clickhouse-migrate-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/clickhouse-migrate-test-integration-ci.sh" ;;
  test-embedder) unset_external_otel; bash "$ROOT_DIR/infra/scripts/embedder-test-ci.sh" ;;
  test-memory) unset_external_otel; bash "$ROOT_DIR/infra/scripts/memory-test-ci.sh" ;;
  test-memory-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/memory-integration-test-ci.sh" ;;
  test-worker) unset_external_otel; bash "$ROOT_DIR/infra/scripts/worker-test-ci.sh" ;;
  test-worker-integration) unset_external_otel; bash "$ROOT_DIR/infra/scripts/worker-integration-test-ci.sh" ;;
  dev-smoke) bash "$ROOT_DIR/infra/scripts/smoke_local.sh" ;;
  dev-smoke-live) bash "$ROOT_DIR/infra/scripts/smoke_live_openrouter.sh" ;;
  e2e-wave2b-token-fks) bash "$ROOT_DIR/infra/scripts/e2e_compose_dev_wave2b.sh" ;;
  verify-phase15) bash "$ROOT_DIR/infra/scripts/verify_phase15.sh" ;;
  verify-phase25) bash "$ROOT_DIR/infra/scripts/verify_phase25.sh" ;;
  e2e-phase25) bash "$ROOT_DIR/infra/scripts/e2e_phase25.sh" ;;
  e2e-smoke-p3-memory) bash "$ROOT_DIR/infra/scripts/verify_phase3_memory_e2e.sh" ;;
  mcp-conformance) bash "$ROOT_DIR/infra/scripts/mcp-conformance.sh" ;;
  v1-up) shift; v1_up "$@" ;;
  v1-down) shift; v1_down "$@" ;;
  v1-migrate) shift; v1_migrate "$@" ;;
  v1-provision) shift; v1_provision "$@" ;;
  v1-logs) compose_with_mode v1 logs -f ;;
  v1-ps) compose_with_mode v1 ps ;;
  v1-secrets) bash "$ROOT_DIR/infra/scripts/gen-v1-secrets.sh" ;;
  v1)
    sub="${2:-}"
    if [[ -n "$sub" ]]; then shift 2; fi
    case "$sub" in
      build) compose_with_mode v1 build "$@" ;;
      up) v1_up "$@" ;;
      down) v1_down "$@" ;;
      stop) compose_with_mode v1 stop "$@" ;;
      wait) v1_wait_healthy ;;
      url) v1_url ;;
      secrets) bash "$ROOT_DIR/infra/scripts/gen-v1-secrets.sh" ;;
      bootstrap-pat) v1_bootstrap_pat ;;
      migrate) v1_migrate "$@" ;;
      provision) v1_provision "$@" ;;
      logs) compose_with_mode v1 logs -f "$@" ;;
      ps) compose_with_mode v1 ps "$@" ;;
      smoke) v1_smoke "$@" ;;
      smoke-selftest) v1_smoke_selftest ;;
      backup) v1_backup "${1:-full}" ;;
      backup-init) v1_backup_init "$@" ;;
      restore) v1_restore ;;
      pitr) v1_pitr "${1:-}" ;;
      *) echo "unknown v1 command: ${sub:-<missing>}" >&2; echo 'use: v1-up|v1-down|v1-migrate|v1-provision|v1-logs|v1-ps|v1-bootstrap-pat|v1-smoke|v1-backup|v1-backup-init|v1-restore|v1-pitr or v1 build|up|down|stop|wait|url|secrets|bootstrap-pat|migrate|provision|logs|ps|smoke|smoke-selftest|backup|backup-init|restore|pitr' >&2; exit 2 ;;
    esac ;;
  *) echo "unknown command: $1" >&2; echo 'run: make help' >&2; exit 2 ;;
esac
