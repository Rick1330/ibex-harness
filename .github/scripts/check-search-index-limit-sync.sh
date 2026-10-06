#!/usr/bin/env bash
# Keep SEARCH_INDEX_MAX_BYTES defaults aligned across extract + smoke + deploy.
# Drift here fails main web-deploy after upload (see #938).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

read_defaults() {
  python3 - "$ROOT" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
extract = (root / "web/scripts/extract-search-index.mjs").read_text(encoding="utf-8")
smoke = (root / ".github/scripts/web-smoke.sh").read_text(encoding="utf-8")
deploy = (root / ".github/workflows/web-deploy.yml").read_text(encoding="utf-8")

em = re.search(r"SEARCH_INDEX_MAX_BYTES\s*\?\?\s*([0-9_]+)", extract)
sm = re.search(r"SEARCH_INDEX_MAX_BYTES:-\$\{SEARCH_INDEX_MAX_BYTES:-([0-9]+)\}", smoke) or re.search(
    r"SEARCH_INDEX_MAX_BYTES:-([0-9]+)", smoke
)
dm = re.search(r"SEARCH_INDEX_MAX_BYTES:\s*[\"']?([0-9]+)", deploy)
if not em or not sm or not dm:
    raise SystemExit(
        f"parse failed extract={bool(em)} smoke={bool(sm)} deploy={bool(dm)}"
    )
print(em.group(1).replace("_", ""), sm.group(1), dm.group(1))
PY
}

read -r extract_default smoke_default deploy_env <<<"$(read_defaults)"

if [[ "$extract_default" != "$smoke_default" || "$extract_default" != "$deploy_env" ]]; then
  echo "SEARCH_INDEX_MAX_BYTES defaults drifted:"
  echo "  extract-search-index.mjs: $extract_default"
  echo "  web-smoke.sh:             $smoke_default"
  echo "  web-deploy.yml:           $deploy_env"
  echo "Keep these equal so Pages smoke cannot reject a build that extract allowed."
  exit 1
fi

echo "SEARCH_INDEX_MAX_BYTES defaults aligned at $extract_default"
