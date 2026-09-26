from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from app.main import create_app
from app.route_policy import (
    ROUTE_POLICY,
    executable_dependency_gaps,
    mounted_route_keys,
    policy_keys,
)


def test_route_policy_covers_every_mounted_route() -> None:
    app = create_app()
    assert policy_keys() == mounted_route_keys(app)


def test_protected_routes_have_executable_dependency_coverage() -> None:
    assert executable_dependency_gaps(create_app()) == ()


def test_route_policy_rows_declare_security_contract_fields() -> None:
    required = {
        "method",
        "path",
        "auth_source",
        "role",
        "permission",
        "organization_source",
        "anti_enumeration",
        "unavailable_result",
        "csrf_origin_required",
        "cache_control",
        "evidence",
    }
    assert ROUTE_POLICY
    for row in ROUTE_POLICY:
        assert required <= row.keys()


def test_same_module_unrelated_dependency_does_not_satisfy_auth_contract() -> None:
    from app.deps import get_validator
    from app.route_policy import _mounted_routes

    app = create_app()
    route = next(
        route for route in _mounted_routes(app) if getattr(route, "path", None) == "/v1/tenant/ping"
    )
    route.dependant.dependencies = [SimpleNamespace(call=get_validator, dependencies=[])]
    assert ("GET", "/v1/tenant/ping") in executable_dependency_gaps(app)


def test_route_policy_generator_preserves_helpers_and_is_deterministic(tmp_path: Path) -> None:
    repo = tmp_path
    scripts = repo / "services/api/scripts"
    app_dir = repo / "services/api/app"
    scripts.mkdir(parents=True)
    app_dir.mkdir(parents=True)
    source_script = Path(__file__).resolve().parents[2] / "scripts/generate_route_policy.py"
    source_inventory = Path(__file__).resolve().parents[2] / "scripts/route_inventory.json"
    script = scripts / "generate_route_policy.py"
    script.write_bytes(source_script.read_bytes())
    inventory = json.loads(source_inventory.read_text(encoding="utf-8"))
    (scripts / "route_inventory.json").write_text(json.dumps(inventory[:2]), encoding="utf-8")
    runtime_module = app_dir / "route_policy.py"
    preserved_helpers = (
        "def executable_dependency_gaps():\n    return ()\n\n"
        "def mounted_route_keys():\n    return frozenset()\n"
    )
    runtime_module.write_text(preserved_helpers, encoding="utf-8")

    command = [sys.executable, str(script)]
    first = subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)
    generated = app_dir / "route_policy_data.py"
    first_bytes = generated.read_bytes()
    second = subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)

    assert "wrote 2 policy rows" in first.stdout
    assert second.stdout == first.stdout
    assert generated.read_bytes() == first_bytes
    assert runtime_module.read_text(encoding="utf-8") == preserved_helpers


def test_auth_source_requires_exact_public_path_match() -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts/generate_route_policy.py"
    spec = importlib.util.spec_from_file_location("generate_route_policy", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
    assert module._auth_source("/health", public_paths) == "public"
    assert module._auth_source("/metrics", public_paths) == "public"
    assert module._auth_source("/docs/oauth2-redirect", public_paths) == "public"
    assert module._auth_source("/healthcheck", public_paths) == "bearer_pat"
    assert module._auth_source("/metrics/private", public_paths) == "bearer_pat"
    assert module._auth_source("/docs-admin", public_paths) == "bearer_pat"


def test_auth_source_is_method_aware_for_cookie_guarded_legal_hold_write() -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts/generate_route_policy.py"
    spec = importlib.util.spec_from_file_location("generate_route_policy_method", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = "/v1/organizations/{org_id}/legal-holds"
    assert module._auth_source(path, frozenset(), "GET") == "bearer_pat"
    assert module._auth_source(path, frozenset(), "POST") == "operator_session"


def _route(path: str | None, endpoint: object, dependencies: list[object] | None = None):
    return SimpleNamespace(
        path=path,
        endpoint=endpoint,
        methods={"GET"},
        dependant=SimpleNamespace(dependencies=dependencies or []),
    )


def _policy_row(path: str, endpoint: object, auth_source: str) -> dict[str, object]:
    from app.route_policy import _endpoint_identity

    return {
        "method": "GET",
        "path": path,
        "endpoint": _endpoint_identity(endpoint),
        "auth_source": auth_source,
    }


def test_mounted_route_traversal_handles_cycles_and_pathless_routes() -> None:
    from app.route_policy import _mounted_routes

    container = SimpleNamespace(routes=[])
    container.routes.extend([container, _route(None, object())])
    routes = tuple(_mounted_routes(container))
    assert len(routes) == 1
    assert mounted_route_keys(SimpleNamespace(routes=[container])) == frozenset()


def test_route_policy_rejects_missing_rows_wrong_endpoints_and_unknown_auth(monkeypatch) -> None:
    from app import route_policy

    def endpoint() -> None:
        pass

    def wrong_endpoint() -> None:
        pass

    monkeypatch.setattr(route_policy, "ROUTE_POLICY", ())
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route("/missing", endpoint)])) == (
        ("GET", "/missing"),
    )

    row = _policy_row("/protected", endpoint, "public")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    assert executable_dependency_gaps(
        SimpleNamespace(routes=[_route("/protected", wrong_endpoint)])
    ) == (("GET", "/protected"),)

    row = _policy_row("/protected", endpoint, "unsupported")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route("/protected", endpoint)])) == (
        ("GET", "/protected"),
    )


def test_route_policy_checks_bearer_and_pat_exchange_exact_dependencies(monkeypatch) -> None:
    from app import route_policy
    from app.deps import get_validator, require_token

    endpoint = lambda: None
    bearer_path = "/bearer"
    row = _policy_row(bearer_path, endpoint, "bearer_pat")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    no_guard = _route(bearer_path, endpoint)
    assert executable_dependency_gaps(SimpleNamespace(routes=[no_guard])) == (("GET", bearer_path),)
    guarded = _route(
        bearer_path,
        endpoint,
        [SimpleNamespace(call=require_token, dependencies=[])],
    )
    assert executable_dependency_gaps(SimpleNamespace(routes=[guarded])) == ()

    exchange_path = "/v1/operator/session/login"
    exchange_endpoint = lambda: None
    exchange_row = _policy_row(exchange_path, exchange_endpoint, "pat_exchange")
    exchange_row["method"] = "POST"
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (exchange_row,))
    no_exchange = _route(exchange_path, exchange_endpoint)
    no_exchange.methods = {"POST"}
    assert executable_dependency_gaps(SimpleNamespace(routes=[no_exchange])) == (
        ("POST", exchange_path),
    )
    exchange_guarded = _route(
        exchange_path,
        exchange_endpoint,
        [SimpleNamespace(call=get_validator, dependencies=[])],
    )
    exchange_guarded.methods = {"POST"}
    assert executable_dependency_gaps(SimpleNamespace(routes=[exchange_guarded])) == ()


def test_route_policy_requires_operator_session_dependencies(monkeypatch) -> None:
    from app import route_policy
    from app.routers.session import me, require_session_me

    path = "/v1/operator/session/me"
    row = _policy_row(path, me, "operator_session")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route(path, lambda: None)])) == (
        ("GET", path),
    )
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route(path, me)])) == (
        ("GET", path),
    )
    guarded = _route(
        path,
        me,
        [SimpleNamespace(call=require_session_me, dependencies=[])],
    )
    assert executable_dependency_gaps(SimpleNamespace(routes=[guarded])) == ()

    path = "/operator/unknown-protected-route"
    row = _policy_row(path, me, "operator_permission")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route(path, me)])) == (
        ("GET", path),
    )


def test_generated_policy_data_public_helper_matches_runtime_rows() -> None:
    from app.route_policy_data import policy_keys as generated_policy_keys

    assert generated_policy_keys() == policy_keys()


def test_route_policy_skips_pathless_routes_and_rejects_missing_session_dep(monkeypatch) -> None:
    from app import route_policy
    from app.routers.session import me, require_session_me

    pathless = _route(None, me)
    assert executable_dependency_gaps(SimpleNamespace(routes=[pathless])) == ()

    key = ("GET", "/v1/operator/session/me")
    row = _policy_row(key[1], me, "operator_session")
    monkeypatch.setattr(route_policy, "ROUTE_POLICY", (row,))
    assert executable_dependency_gaps(SimpleNamespace(routes=[_route(key[1], me)])) == (key,)
    guarded = _route(
        key[1],
        me,
        [SimpleNamespace(call=require_session_me, dependencies=[])],
    )
    assert executable_dependency_gaps(SimpleNamespace(routes=[guarded])) == ()


def test_operator_session_legal_hold_guard_helpers() -> None:
    from app.authz import require_operator_legal_hold_manage
    from app.route_policy import (
        _has_expected_guard,
        _has_operator_session_guard,
        _is_operator_legal_hold_guard,
    )

    key = ("POST", "/v1/organizations/{org_id}/legal-holds")
    foreign = SimpleNamespace(__module__="elsewhere", __qualname__="other")
    assert _is_operator_legal_hold_guard(foreign) is False
    assert _has_operator_session_guard(key, [foreign]) is False

    hold_dep = require_operator_legal_hold_manage()
    assert _is_operator_legal_hold_guard(hold_dep) is True
    assert _has_operator_session_guard(key, [hold_dep]) is True
    assert _has_expected_guard(key, "operator_session", [hold_dep]) is True

    wrong_exchange = ("POST", "/v1/operator/session/refresh")
    assert _has_expected_guard(wrong_exchange, "pat_exchange", []) is False


def test_dependency_calls_recurse_into_nested_dependants() -> None:
    from app.deps import require_token
    from app.route_policy import _dependency_calls

    nested = SimpleNamespace(
        call=None,
        dependencies=[SimpleNamespace(call=require_token, dependencies=[])],
    )
    assert _dependency_calls(nested) == [require_token]
