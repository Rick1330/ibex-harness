from __future__ import annotations

import argparse
import inspect
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / "services" / "api"))
from app.main import create_app

_EXCLUDED_SOURCE_PARTS = frozenset({".venv", "site-packages"})


def _call_identity(call: object) -> str | None:
    module = getattr(call, "__module__", None)
    qualified_name = getattr(call, "__qualname__", None)
    if not module or not qualified_name:
        return None
    return f"{module}.{qualified_name}"


def _repository_source(endpoint: object) -> str | None:
    source = inspect.getsourcefile(endpoint)
    if not source:
        return None
    try:
        relative = Path(source).resolve().relative_to(repo)
    except ValueError:
        # Do not bake local virtualenv/site-packages or runner paths into the
        # checked-in API contract inventory.
        return None
    if any(part in _EXCLUDED_SOURCE_PARTS for part in relative.parts):
        return None
    return relative.as_posix()


def _iter_routes(routes: Iterable[object]) -> Iterator[object]:
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested is not None:
            yield from _iter_routes(nested)
        elif hasattr(route, "original_router"):
            yield from _iter_routes(route.original_router.routes)
        else:
            yield route


def generate_inventory() -> list[dict[str, object]]:
    application = create_app()
    rows: list[dict[str, object]] = []
    for route in _iter_routes(application.routes):
        route_methods = getattr(route, "methods", None)
        methods = sorted((route_methods or set()) - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        endpoint = getattr(route, "endpoint", None)
        dependencies = getattr(route, "dependant", None)
        rows.append(
            {
                "methods": methods,
                "path": getattr(route, "path", ""),
                "name": getattr(route, "name", ""),
                "endpoint": (
                    f"{endpoint.__module__}.{endpoint.__qualname__}" if endpoint else ""
                ),
                "source": _repository_source(endpoint) if endpoint else None,
                "security": sorted(
                    identity
                    for dependency in getattr(dependencies, "dependencies", ())
                    if (identity := _call_identity(getattr(dependency, "call", None)))
                ),
                "response_model": repr(getattr(route, "response_model", None)),
            }
        )
    return sorted(rows, key=lambda row: (row["path"], row["methods"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or check the mounted API route inventory.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the checked-in inventory differs from the current mounted API",
    )
    args = parser.parse_args()

    output = Path(__file__).with_name("route_inventory.json")
    generated = json.dumps(generate_inventory(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != generated:
            print(f"route inventory is stale: {output}", file=sys.stderr)
            return 1
        print(f"route inventory is fresh: {output}")
        return 0

    output.write_text(generated, encoding="utf-8")
    print(f"wrote mounted API route inventory to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
