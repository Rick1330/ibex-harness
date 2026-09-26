#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCHEMA="$ROOT/infra/assurance/p6/manifest.schema.json"
VALIDATOR="$ROOT/infra/assurance/p6/validate_manifest.py"

python3 -m py_compile "$VALIDATOR"
python3 - <<'PY' "$SCHEMA"
import json
import sys
from pathlib import Path

schema = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert schema["$id"].endswith("p6-evidence-manifest.v1.json")
assert schema["properties"]["manifest_version"]["const"] == "p6-bootstrap.v1"
assert "checks" in schema["required"]
assert "rollback" in schema["required"]
print("P6 manifest schema is structurally present")
PY

echo "P6 bootstrap validator and schema checks passed"
