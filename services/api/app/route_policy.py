"""Executable parity checks for the generated mounted-route policy inventory."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.deps import get_validator, require_token
from app.route_policy_data import ROUTE_POLICY

SUPPORTED_AUTH_SOURCES: Final[frozenset[str]] = frozenset(
    {"public", "bearer_pat", "pat_exchange", "operator_session", "operator_permission"}
)

_INLINE_SESSION_ENDPOINTS: Final[dict[tuple[str, str], str]] = {
    ("POST", "/v1/operator/session/refresh"): "app.routers.session.refresh_session",
    ("POST", "/v1/operator/session/logout"): "app.routers.session.logout",
    ("GET", "/v1/operator/session/me"): "app.routers.session.me",
}


def policy_keys() -> frozenset[tuple[str, str]]:
    """Return the method/path keys represented by the generated inventory."""
    return frozenset((str(row["method"]), str(row["path"])) for row in ROUTE_POLICY)


def _endpoint_identity(endpoint: object) -> str:
    """Return a stable module-qualified identity for a mounted endpoint."""
    module = getattr(endpoint, "__module__", "")
    qualified_name = getattr(endpoint, "__qualname__", "")
    return f"{module}.{qualified_name}" if module and qualified_name else ""


def _dependency_calls(dependant: object | None) -> list[object]:
    """Collect dependency callables recursively from FastAPI's resolved graph."""
    calls: list[object] = []
    for child in getattr(dependant, "dependencies", ()):
        call = getattr(child, "call", None)
        if call is not None:
            calls.append(call)
        calls.extend(_dependency_calls(child))
    return calls


def _mounted_routes(application: object) -> Iterable[object]:
    """Yield concrete routes from FastAPI and nested router containers."""
    seen_containers: set[int] = set()

    def visit(routes: object) -> Iterable[object]:
        if not isinstance(routes, Iterable) or id(routes) in seen_containers:
            return
        seen_containers.add(id(routes))
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                yield from visit(original.routes)
                continue
            nested = getattr(route, "routes", None)
            if nested is not None:
                yield from visit(nested)
                continue
            yield route

    yield from visit(getattr(application, "routes", ()))


def _operator_permission_dependencies() -> dict[tuple[str, str], object]:
    from app.routers.operator_events import require_operator_event_session
    from app.routers.platform import _require_operator_session

    return {
        ("GET", "/v1/operator/events/stream"): require_operator_event_session,
        ("GET", "/v1/operator/platform/health"): _require_operator_session,
    }


def _has_expected_guard(
    key: tuple[str, str],
    auth_source: str,
    endpoint_identity: str,
    calls: list[object],
) -> bool:
    if auth_source == "public":
        return True
    if auth_source == "bearer_pat":
        return require_token in calls
    if auth_source == "pat_exchange":
        return key == ("POST", "/v1/operator/session/login") and get_validator in calls
    if auth_source == "operator_session":
        return _INLINE_SESSION_ENDPOINTS.get(key) == endpoint_identity
    if auth_source == "operator_permission":
        return _operator_permission_dependencies().get(key) in calls
    return False


def executable_dependency_gaps(app: object) -> tuple[tuple[str, str], ...]:
    """Return policy rows whose concrete endpoint or authorization guard is missing."""
    rows = {(str(row["method"]), str(row["path"])): row for row in ROUTE_POLICY}
    gaps: set[tuple[str, str]] = set()
    for route in _mounted_routes(app):
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if path is None:
            continue
        endpoint_identity = _endpoint_identity(getattr(route, "endpoint", None))
        calls = _dependency_calls(getattr(route, "dependant", None))
        for method in methods - {"HEAD", "OPTIONS"}:
            key = (str(method), str(path))
            row = rows.get(key)
            if row is None or endpoint_identity != str(row.get("endpoint", "")):
                gaps.add(key)
                continue
            auth_source = str(row.get("auth_source", ""))
            if not _has_expected_guard(key, auth_source, endpoint_identity, calls):
                gaps.add(key)
    return tuple(sorted(gaps))


def mounted_route_keys(application: object) -> frozenset[tuple[str, str]]:
    """Return concrete method/path pairs from a FastAPI application."""
    keys: set[tuple[str, str]] = set()
    for route in _mounted_routes(application):
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if path is not None:
            keys.update(
                (str(method), str(path)) for method in methods if method not in {"HEAD", "OPTIONS"}
            )
    return frozenset(keys)
