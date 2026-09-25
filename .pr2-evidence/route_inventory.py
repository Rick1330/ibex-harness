from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "services" / "api"))
from app.main import create_app  # noqa: E402

app = create_app()
rows = []
def iter_routes(routes):
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested is not None:
            yield from iter_routes(nested)
        elif hasattr(route, "original_router"):
            yield from iter_routes(route.original_router.routes)
        else:
            yield route


for route in iter_routes(app.routes):
    route_methods = getattr(route, "methods", None)
    methods = sorted((route_methods or set()) - {"HEAD", "OPTIONS"})
    if not methods:
        continue
    endpoint = getattr(route, "endpoint", None)
    rows.append(
        {
            "methods": methods,
            "path": getattr(route, "path", ""),
            "name": getattr(route, "name", ""),
            "endpoint": f"{endpoint.__module__}.{endpoint.__qualname__}" if endpoint else "",
            "source": inspect.getsourcefile(endpoint) if endpoint else None,
            "security": [repr(dep.call) for dep in getattr(route, "dependant", None).dependencies] if getattr(route, "dependant", None) else [],
            "response_model": repr(getattr(route, "response_model", None)),
        }
    )
rows.sort(key=lambda row: (row["path"], row["methods"]))
out = Path(__file__).with_name("route_inventory.json")
out.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {len(rows)} routes to {out}")
for row in rows:
    print(f"{'/'.join(row['methods']):20} {row['path']:65} {row['endpoint']}")
