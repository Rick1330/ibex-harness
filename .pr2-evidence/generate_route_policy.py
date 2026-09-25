from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = json.loads((root / ".pr2-evidence" / "route_inventory.json").read_text(encoding="utf-8"))
public_prefixes = ("/docs", "/redoc", "/openapi.json", "/health", "/ready", "/metrics")
source_constants = {
    "services/api/app/routers/organizations.py": "ORGANIZATIONS_ROUTER_SOURCE",
    "services/api/app/routers/providers.py": "PROVIDERS_ROUTER_SOURCE",
}
policy = []
for row in rows:
    method = row["methods"][0]
    path = row["path"]
    if path.startswith(public_prefixes):
        auth = "public"
    elif path == "/v1/operator/session/login":
        auth = "pat_exchange"
    elif path.startswith("/v1/operator/session"):
        auth = "operator_session"
    elif path == "/v1/operator/platform/health":
        auth = "operator_permission"
    elif path == "/v1/operator/events/stream":
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

out = root / "services" / "api" / "app" / "route_policy_data.py"
body = '''"""Generated mounted route policy rows; regenerate with .pr2-evidence/generate_route_policy.py."""\n\nfrom __future__ import annotations\n\nfrom typing import Final\n\n'''
for source_path, constant in source_constants.items():
    body += f"{constant}: Final = {source_path!r}\n"
body += "\nROUTE_POLICY: Final[tuple[dict[str, object], ...]] = (\n"
for item in policy:
    row = repr(item)
    constant = source_constants.get(item["source"])
    if constant:
        row = row.replace(f"'source': {item['source']!r}", f"'source': {constant}")
    body += f"    {row},\n"
body += ")\n\n\ndef policy_keys() -> frozenset[tuple[str, str]]:\n    return frozenset((str(row['method']), str(row['path'])) for row in ROUTE_POLICY)\n"
out.write_text(body, encoding="utf-8")
print(f"wrote {len(policy)} policy rows to {out}")
