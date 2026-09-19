#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5). Destructive — stop PG first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

resolve_conf() {
  if [[ -n "${PGBACKREST_CONF:-}" ]]; then
    if [[ ! -f "$PGBACKREST_CONF" ]]; then
      echo "[restore] PGBACKREST_CONF set but file missing: $PGBACKREST_CONF" >&2
      exit 1
    fi
    printf '%s\n' "$PGBACKREST_CONF"
    return
  fi
  local conf="$ROOT/infra/backup/pgbackrest/pgbackrest.conf"
  if [[ -f "$conf" ]]; then
    printf '%s\n' "$conf"
    return
  fi
  echo "[restore] missing real pgbackrest.conf at $conf (do not use .example)" >&2
  exit 1
}

# Resolve docker-compose named volume mountpoint so restore targets the same
# data directory the postgres service uses (not a bare host /var/lib/postgresql/data).
resolve_compose_pgdata() {
  local compose_file="$1"
  local preferred="${PGBACKREST_COMPOSE_VOLUME:-ibex_postgres_data}"
  local vol=""
  local candidate
  # Prefer exact / project-prefixed volume names that exist locally.
  for candidate in \
    "$preferred" \
    "dev_${preferred}" \
    "ibex_${preferred}" \
    "$(basename "$(dirname "$compose_file")")_${preferred}"; do
    if docker volume inspect "$candidate" >/dev/null 2>&1; then
      vol="$candidate"
      break
    fi
  done
  if [[ -z "$vol" ]]; then
    # Fall back to first volume matching the preferred suffix.
    vol="$(docker volume ls -q | grep -E "(^|/)${preferred}$|_${preferred}$" | head -n1 || true)"
  fi
  if [[ -z "$vol" ]]; then
    echo "[restore] could not resolve compose volume for $preferred" >&2
    return 1
  fi
  docker volume inspect -f '{{.Mountpoint}}' "$vol"
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/dev/docker-compose.yml}"
TARGET="${PGBACKREST_PGDATA:-}"
stopped=false
stopped_via_compose=false

echo "[restore] stopping Postgres before restore"
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  if docker compose -f "$COMPOSE_FILE" stop postgres 2>/dev/null; then
    stopped=true
    stopped_via_compose=true
  fi
fi

if [[ -z "$TARGET" && "$stopped_via_compose" == "true" ]]; then
  TARGET="$(resolve_compose_pgdata "$COMPOSE_FILE")"
  echo "[restore] using compose volume mountpoint TARGET=$TARGET"
elif [[ -z "$TARGET" ]]; then
  TARGET="/var/lib/postgresql/data"
fi

if command -v pg_ctl >/dev/null 2>&1 && [[ -d "$TARGET" ]]; then
  if pg_ctl -D "$TARGET" stop -m fast 2>/dev/null; then
    stopped=true
  fi
fi
if [[ "$stopped" != "true" && "${PGBACKREST_ALLOW_UNSAFE_RESTORE:-0}" != "1" ]]; then
  echo "[restore] refused: could not stop Postgres (set PGBACKREST_ALLOW_UNSAFE_RESTORE=1 only for dry-run labs)" >&2
  exit 1
fi

echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" restore
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
