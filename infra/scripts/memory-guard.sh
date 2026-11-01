#!/usr/bin/env bash
# Memory guard: when RAM usage crosses the threshold, stop the heavy, non-essential
# things this workspace owns — the SonarQube MCP container, Docker Desktop if it was
# only running for that, and a small allowlist of media apps.
#
# It never touches the terminal, the OpenCode service, the desktop, or system services.
#
# Environment:
#   MEMORY_GUARD_THRESHOLD  percent of RAM that triggers the cooldown (default 90)
#   MEMORY_GUARD_DRY_RUN    set to 1 to report actions without taking them
#
# Exit codes: 0 = below threshold or action taken, 2 = acted (useful for timers/logs).
set -euo pipefail

THRESHOLD="${MEMORY_GUARD_THRESHOLD:-90}"
DRY_RUN="${MEMORY_GUARD_DRY_RUN:-0}"
LOG_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/opencode"
LOG="$LOG_DIR/memory-guard.log"

mkdir -p "$LOG_DIR"
if [[ -f "$LOG" ]] && [[ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 500000 ]]; then
  mv "$LOG" "$LOG.1"
fi

read -r total_kb avail_kb < <(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{print t, a}' /proc/meminfo)
used_pct=$(( (total_kb - avail_kb) * 100 / total_kb ))
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log() { printf '%s %s\n' "$ts" "$*" >>"$LOG"; }

if [[ "$used_pct" -lt "$THRESHOLD" ]]; then
  exit 0
fi

log "RAM ${used_pct}% >= ${THRESHOLD}% — starting cooldown"
acted=0

run() {
  if [[ "$DRY_RUN" = "1" ]]; then
    log "dry-run: $*"
  else
    log "exec: $*"
    "$@" >/dev/null 2>&1 || true
  fi
}

# 1. SonarQube MCP container (the largest workspace-owned consumer).
#    Podman is the default runtime; Docker is handled only as a fallback.
for runtime in podman docker; do
  if command -v "$runtime" >/dev/null 2>&1 && "$runtime" info >/dev/null 2>&1; then
    mapfile -t containers < <("$runtime" ps -q --filter "ancestor=sonarsource/sonarqube-mcp" 2>/dev/null || true)
    if [[ "${#containers[@]}" -gt 0 ]]; then
      run "$runtime" stop "${containers[@]}"
      acted=1
    fi
  fi
done

# 2. Docker Desktop itself, if it is running (legacy path; Podman needs no VM).
if systemctl --user is-active --quiet docker-desktop 2>/dev/null; then
  run systemctl --user stop docker-desktop
  acted=1
fi

# 3. Media apps on a small, explicit allowlist. Never a terminal, editor, or the agent.
# shellcheck disable=SC2043  # the allowlist is intentionally single-entry and may grow
for app in vlc; do
  if pgrep -x "$app" >/dev/null 2>&1; then
    run pkill -x "$app"
    acted=1
  fi
done

if [[ "$acted" = "1" ]]; then
  log "cooldown complete (RAM was ${used_pct}%)"
  exit 2
fi

log "RAM ${used_pct}% but nothing on the allowlist was running"
exit 0
