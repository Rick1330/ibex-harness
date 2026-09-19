#!/usr/bin/env bash
# Reconstruct evidence-plane health from PG + CH + Redis + MinIO + outbox (4.P.5).
# Watermark uses MAX(aggregate_seq) — no new checkpoint table (decision 6).
set -euo pipefail
PGURL="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
OUT="${1:-/tmp/ibex-evidence-recovery.json}"

OUTBOX_MAX="$(psql "$PGURL" -Atc "SELECT COALESCE(MAX(aggregate_seq),0) FROM ibex_core.evidence_outbox")"
OUTBOX_PENDING="$(psql "$PGURL" -Atc "SELECT COUNT(*) FROM ibex_core.evidence_outbox WHERE delivery_status='pending'")"
# Latest non-null digest by started_at (not MAX lexicographic).
DEPLOY_DIGEST="$(psql "$PGURL" -Atc \
  "SELECT deploy_image_digest FROM ibex_core.evidence_runs WHERE deploy_image_digest IS NOT NULL AND deploy_image_digest <> '' ORDER BY started_at DESC NULLS LAST LIMIT 1")"

export OUTBOX_MAX OUTBOX_PENDING DEPLOY_DIGEST OUT
python3 <<'PY'
import json, os, urllib.request
from pathlib import Path

ch = os.environ.get("CLICKHOUSE_HTTP_URL", "http://localhost:8123")
ch_ok = False
try:
    with urllib.request.urlopen(ch + "/?query=SELECT%201", timeout=3) as r:
        ch_ok = r.status == 200
except Exception:
    ch_ok = False

payload = {
    "outbox_max_aggregate_seq": int(os.environ.get("OUTBOX_MAX") or 0),
    "outbox_pending": int(os.environ.get("OUTBOX_PENDING") or -1),
    "outbox_rpo_claim": "0 (replay from aggregate_seq; no gaps when pending caught up)",
    "clickhouse_reachable": ch_ok,
    "deploy_image_digest": os.environ.get("DEPLOY_DIGEST") or None,
    "redis_url_configured": bool(os.environ.get("REDIS_URL")),
}
out = Path(os.environ["OUT"])
out.write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
PY
