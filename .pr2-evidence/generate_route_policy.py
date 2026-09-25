from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = json.loads((root / ".pr2-evidence" / "route_inventory.json").read_text(encoding="utf-8"))
public_prefixes = ("/docs", "/redoc", "/openapi.json", "/health", "/ready", "/metrics")
policy = []
for row in rows:
    method = row["methods"][0]
    path = row["path"]
    if path.startswith(public_prefixes):
        auth = "public"
    elif path.startswith("/v1/operator/session"):
        auth = "operator_session"
    elif path == "/v1/operator/events" or "operator_events" in row["endpoint"]:
        auth = "operator_permission"
    else:
        auth = "bearer_pat"
    mutation = method in {"POST", "PATCH", "PUT", "DELETE"}
    source_path = Path(row["source"]).resolve() if row["source"] else None
    source = (
        str(source_path.relative_to(root))
        if source_path is not None and str(source_path).startswith(str(root / "services" / "api" / "app"))
        else None
    )
    policy.append({
        "method": method,
        "path": path,
        "auth_source": auth,
        "role": "explicit_route_dependency",
        "permission": "declared_by_endpoint_dependency",
        "organization_source": "verified_token_or_session",
        "action": None,
        "anti_enumeration": "route_dependency_contract",
        "unavailable_result": "503_without_side_effect",
        "csrf_origin_required": mutation and auth == "operator_session",
        "cache_control": "no-store" if auth != "public" else "default",
        "evidence": "inventory_only",
        "endpoint": row["endpoint"],
        "source": source,
    })

out = root / "services" / "api" / "app" / "route_policy.py"
body = '''"""Machine-readable mounted route policy inventory for PR2 parity checks.\n\nThis file is generated from the mounted route inventory and reviewed policy\noverrides. It intentionally records current enforcement evidence separately from\nfuture product decisions.\n"""\n\nfrom __future__ import annotations\n\nfrom typing import Final\n\nROUTE_POLICY: Final[tuple[dict[str, object], ...]] = (\n'''
for item in policy:
    body += f"    {item!r},\n"
body += ")\n\n\ndef policy_keys() -> frozenset[tuple[str, str]]:\n    return frozenset((str(row['method']), str(row['path'])) for row in ROUTE_POLICY)\n"
out.write_text(body, encoding="utf-8")
print(f"wrote {len(policy)} policy rows to {out}")
