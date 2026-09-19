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

# Resolve docker-compose named volume from Compose metadata only (fail closed).
# Never pick an arbitrary docker volume ls suffix match.
resolve_compose_volume() {
  local compose_file="$1"
  local vol=""

  if [[ -n "${PGBACKREST_COMPOSE_VOLUME:-}" ]]; then
    if ! docker volume inspect "$PGBACKREST_COMPOSE_VOLUME" >/dev/null 2>&1; then
      echo "[restore] PGBACKREST_COMPOSE_VOLUME set but volume missing: $PGBACKREST_COMPOSE_VOLUME" >&2
      return 1
    fi
    printf '%s\n' "$PGBACKREST_COMPOSE_VOLUME"
    return 0
  fi

  vol="$(
    docker compose -f "$compose_file" config --format json 2>/dev/null | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
vols = cfg.get("volumes") or {}
svc = (cfg.get("services") or {}).get("postgres") or {}

def emit(key: str) -> None:
    meta = vols.get(key) or {}
    name = meta.get("name") if isinstance(meta, dict) else None
    print(name or key)
    raise SystemExit(0)

for m in svc.get("volumes") or []:
    if isinstance(m, dict):
        target = (m.get("target") or "").rstrip("/")
        source = m.get("source") or ""
        if target.endswith("postgresql/data") and source:
            emit(source)
    elif isinstance(m, str) and ":/var/lib/postgresql/data" in m:
        emit(m.split(":", 1)[0])

if "ibex_postgres_data" in vols:
    emit("ibex_postgres_data")
raise SystemExit(1)
'
  )" || true

  if [[ -z "$vol" ]]; then
    echo "[restore] could not resolve postgres volume from Compose metadata; set PGBACKREST_COMPOSE_VOLUME" >&2
    return 1
  fi
  if ! docker volume inspect "$vol" >/dev/null 2>&1; then
    echo "[restore] Compose volume name $vol does not exist locally; set PGBACKREST_COMPOSE_VOLUME" >&2
    return 1
  fi
  printf '%s\n' "$vol"
}

# Compose project network so repo1-s3-endpoint=minio:9000 resolves.
resolve_compose_network() {
  local compose_file="$1"
  local cid
  local net
  cid="$(docker compose -f "$compose_file" ps -q minio 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    cid="$(docker compose -f "$compose_file" ps -aq 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "$cid" ]]; then
    echo "[restore] could not resolve compose network (no containers)" >&2
    return 1
  fi
  # One network name per line; take the first only (avoid concatenated names).
  net="$(docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$cid" | head -n1 | tr -d '\r')"
  if [[ -z "$net" ]]; then
    echo "[restore] container $cid has no networks" >&2
    return 1
  fi
  printf '%s\n' "$net"
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
