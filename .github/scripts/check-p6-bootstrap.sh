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
assert "evidence_state" in schema["properties"]["checks"]["items"]["required"]
print("P6 manifest schema is structurally present")
PY

MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
python3 - <<'PY' "$MANIFEST" "$ROOT" "$(git -C "$ROOT" rev-parse HEAD)"
import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
root = Path(sys.argv[2])
commit = sys.argv[3]
schema = root / "infra/assurance/p6/manifest.schema.json"
artifact_sha = hashlib.sha256(schema.read_bytes()).hexdigest()
manifest = {
    "manifest_version": "p6-bootstrap.v1",
    "run_id": f"local-p6-{commit[:12]}",
    "commit_sha": commit,
    "environment": "local",
    "topology": {
        "ui_origin": "http://localhost",
        "api_origin": "http://localhost:8010",
        "sse_origin": "http://localhost:8010",
    },
    "artifacts": [{
        "name": "manifest-schema",
        "sha256": artifact_sha,
        "uri": f"file://{schema}",
        "evidence_state": "declared",
        "producer": "check-p6-bootstrap",
    }],
    "versions": {"fixture": "none", "schema": "repository", "migration": "unverified"},
    "checks": [{
        "name": "p6-manifest-schema",
        "expected": True,
        "applicability": "applicable",
        "result": "passed",
        "evidence_state": "contract-tested",
        "artifact_uris": [f"file://{schema}"],
    }],
    "rollback": {
        "prior_digest": "unverified",
        "current_digest": "unverified",
        "schema_compatible": False,
        "command": "not-applicable-local-bootstrap",
        "verified": False,
    },
    "owner": "ci-local",
}
out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
python3 "$VALIDATOR" "$MANIFEST" --sha256

python3 - <<'PY' "$MANIFEST" "$VALIDATOR"
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validator = sys.argv[2]

def expect_invalid(label, mutate):
    candidate = copy.deepcopy(manifest)
    mutate(candidate)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
        json.dump(candidate, handle)
        handle.flush()
        result = subprocess.run(
            [sys.executable, validator, handle.name],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode != 0, f"{label}: malformed manifest was accepted"
    print(f"P6 negative fixture rejected: {label}")

expect_invalid("applicable failed check", lambda value: value["checks"][0].update(result="failed"))
expect_invalid("applicable skipped check", lambda value: value["checks"][0].update(result="skipped"))
expect_invalid("malformed commit_sha", lambda value: value.update(commit_sha="not-a-commit"))
expect_invalid("missing artifact URI", lambda value: value["checks"][0].pop("artifact_uris"))
expect_invalid(
    "unlinked artifact URI",
    lambda value: value["checks"][0].update(artifact_uris=["file:///not-declared"]),
)
PY

echo "P6 bootstrap validator, schema, and revision-bound manifest checks passed"
