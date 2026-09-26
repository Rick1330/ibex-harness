from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


def source_constant_name(source: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", source).strip("_").upper()
    return f"ROUTE_SOURCE_{suffix}"


def _auth_source(path: str, public_paths: frozenset[str], method: str = "GET") -> str:
    if path in public_paths:
        return "public"
    if path == "/v1/operator/session/login":
        return "pat_exchange"
    if path in {
        "/v1/operator/context",
        "/v1/operator/overview",
        "/v1/organizations/{org_id}/legal-holds/{hold_id}/clear",
    }:
        return "operator_session"
    if path.startswith("/v1/operator/session"):
        return "operator_session"
    if path in {"/v1/operator/platform/health", "/v1/operator/events/stream"}:
        return "operator_permission"
    if method == "POST" and path in {
        "/v1/organizations/{org_id}/legal-holds",
        "/v1/organizations/{org_id}/legal-holds/{hold_id}/clear",
    }:
        return "operator_session"
    return "bearer_pat"


def _source_path(root: Path, raw_source: str | None) -> str | None:
    if not raw_source:
        return None
    source_path = Path(raw_source).resolve()
    app_root = root / "services" / "api" / "app"
    if not str(source_path).startswith(str(app_root)):
        return None
    return str(source_path.relative_to(root))


def _policy_row(
    root: Path, row: dict[str, object], public_paths: frozenset[str]
) -> dict[str, object]:
    method = str(row["methods"][0])
    path = str(row["path"])
    auth = _auth_source(path, public_paths, method)
    source = _source_path(root, row.get("source"))
    return {
        "method": method,
        "path": path,
        "auth_source": auth,
        "role": "explicit_route_dependency",
        "permission": "declared_by_endpoint_dependency",
        "organization_source": "verified_token_or_session",
        "action": None,
        "anti_enumeration": "route_dependency_contract",
        "unavailable_result": "503_without_side_effect",
        "csrf_origin_required": method in {"POST", "PATCH", "PUT", "DELETE"}
        and auth == "operator_session",
        "cache_control": "no-store" if auth != "public" else "default",
        "evidence": "inventory_only",
        "endpoint": row["endpoint"],
        "source": source,
    }


def _constants(
    policy: list[dict[str, object]],
) -> tuple[dict[str, str], dict[str, str]]:
    sources = {
        "services/api/app/routers/organizations.py": "ORGANIZATIONS_ROUTER_SOURCE",
        "services/api/app/routers/providers.py": "PROVIDERS_ROUTER_SOURCE",
    }
    for item in policy:
        if item["source"] is not None:
            sources.setdefault(
                str(item["source"]), source_constant_name(str(item["source"]))
            )
    counts = Counter(str(item["path"]) for item in policy)
    paths = {
        path: f"ROUTE_PATH_{re.sub(r'[^A-Za-z0-9]+', '_', path).strip('_').upper()}"
        for path, count in counts.items()
        if count >= 3
    }
    return sources, paths


def _render(
    root: Path,
    policy: list[dict[str, object]],
    sources: dict[str, str],
    paths: dict[str, str],
) -> None:
    out = root / "services" / "api" / "app" / "route_policy_data.py"
    body = '''"""Generated mounted route policy rows; regenerate with services/api/scripts/generate_route_policy.py."""\n\nfrom __future__ import annotations\n\nfrom typing import Final\n\n'''
    body += "".join(
        f"{constant}: Final = {value!r}\n" for value, constant in sources.items()
    )
    body += "".join(
        f"{constant}: Final = {value!r}\n" for value, constant in paths.items()
    )
    body += "\nROUTE_POLICY: Final[tuple[dict[str, object], ...]] = (\n"
    for item in policy:
        row = repr(item)
        if item["source"] in sources:
            row = row.replace(
                f"'source': {item['source']!r}", f"'source': {sources[item['source']]}"
            )
        if item["path"] in paths:
            row = row.replace(
                f"'path': {item['path']!r}", f"'path': {paths[item['path']]}"
            )
        body += f"    {row},\n"
    body += ")\n\n\ndef policy_keys() -> frozenset[tuple[str, str]]:\n    return frozenset((str(row['method']), str(row['path'])) for row in ROUTE_POLICY)\n"
    out.write_text(body, encoding="utf-8")
    print(f"wrote {len(policy)} policy rows to {out}")


def generate() -> None:
    root = Path(__file__).resolve().parents[3]
    rows = json.loads(
        (Path(__file__).resolve().parent / "route_inventory.json").read_text(encoding="utf-8")
    )
    public_paths = frozenset(
        {
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/openapi.json",
            "/health",
            "/ready",
            "/metrics",
        }
    )
    policy = [_policy_row(root, row, public_paths) for row in rows]
    sources, paths = _constants(policy)
    _render(root, policy, sources, paths)


if __name__ == "__main__":
    generate()
