#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5). Destructive — stop PG first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

resolve_conf() {
  if [[ -n "${PGBACKREST_CONF:-}" && ! -f "${PGBACKREST_CONF}" ]]; then
    echo "[restore] PGBACKREST_CONF set but file missing: $PGBACKREST_CONF" >&2
    exit 1
  fi
  if [[ -n "${PGBACKREST_CONF:-}" ]]; then
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

# Resolve docker-compose named volume so restore can mount the same data dir
# the postgres service uses (not a bare host /var/lib/postgresql/data).
resolve_compose_volume() {
  local compose_file="$1"
  local preferred="${PGBACKREST_COMPOSE_VOLUME:-ibex_postgres_data}"
  local vol=""
  local candidate
  for candidate in \
    "$preferred" \
    "dev_${preferred}" \
    "ibex_${preferred}" \
    "$(basename "$(dirname "$compose_file")")_${preferred}"; do
    if docker volume inspect "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  vol="$(docker volume ls -q | grep -E "(^|/)${preferred}$|_${preferred}$" | head -n1 || true)"
  if [[ -z "$vol" ]]; then
    echo "[restore] could not resolve compose volume for $preferred" >&2
    return 1
  fi
  printf '%s\n' "$vol"
}

# Compose project network so repo1-s3-endpoint=minio:9000 resolves.
resolve_compose_network() {
  local compose_file="$1"
  local cid
  cid="$(docker compose -f "$compose_file" ps -q minio 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    cid="$(docker compose -f "$compose_file" ps -aq 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "$cid" ]]; then
    echo "[restore] could not resolve compose network (no containers)" >&2
    return 1
  fi
  docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{$k}}{{end}}' "$cid" | awk '{print $1}'
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/dev/docker-compose.yml}"
TARGET="${PGBACKREST_PGDATA:-}"
PGBACKREST_IMAGE="${PGBACKREST_IMAGE:-pgbackrest/pgbackrest:2.53}"
stopped=false
stopped_via_compose=false
COMPOSE_VOLUME=""

echo "[restore] stopping Postgres before restore"
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]] \
  && docker compose -f "$COMPOSE_FILE" stop postgres 2>/dev/null; then
  stopped=true
  stopped_via_compose=true
fi

if [[ -z "$TARGET" && "$stopped_via_compose" == "true" ]]; then
  COMPOSE_VOLUME="$(resolve_compose_volume "$COMPOSE_FILE")"
  TARGET="/var/lib/postgresql/data"
  echo "[restore] using compose volume=$COMPOSE_VOLUME container path TARGET=$TARGET"
elif [[ -z "$TARGET" ]]; then
  TARGET="/var/lib/postgresql/data"
fi

if command -v pg_ctl >/dev/null 2>&1 && [[ -d "$TARGET" ]] \
  && pg_ctl -D "$TARGET" stop -m fast 2>/dev/null; then
  stopped=true
fi
if [[ "$stopped" != "true" && "${PGBACKREST_ALLOW_UNSAFE_RESTORE:-0}" != "1" ]]; then
  echo "[restore] refused: could not stop Postgres (set PGBACKREST_ALLOW_UNSAFE_RESTORE=1 only for dry-run labs)" >&2
  exit 1
fi

echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
if [[ "$stopped_via_compose" == "true" && -n "$COMPOSE_VOLUME" ]]; then
  # Host pgbackrest cannot resolve minio:9000; run inside the compose network.
  NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"
  echo "[restore] running pgbackrest in compose network=$NETWORK image=$PGBACKREST_IMAGE"
  docker run --rm \
    --network "$NETWORK" \
    -v "${COMPOSE_VOLUME}:${TARGET}" \
    -v "${CONF}:/etc/pgbackrest/pgbackrest.conf:ro" \
    -e PGBACKREST_REPO1_CIPHER_PASS \
    "$PGBACKREST_IMAGE" \
    pgbackrest --config=/etc/pgbackrest/pgbackrest.conf \
      --stanza="$STANZA" --pg1-path="$TARGET" restore
else
  pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" restore
fi
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
