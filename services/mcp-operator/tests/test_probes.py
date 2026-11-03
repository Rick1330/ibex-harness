"""Probe/discovery routes and RFC 9728 metadata."""

from __future__ import annotations

from app.probes import OPERATOR_SCOPES, build_protected_resource_metadata
from tests.fixtures import AppOptions, disabled_settings, make_app, make_settings


def test_build_protected_resource_metadata() -> None:
    meta = build_protected_resource_metadata(
        make_settings(
            resource_url="https://mcp.example.com/mcp", auth_server_url="https://auth.example.com"
        )
    )
    assert meta["resource"] == "https://mcp.example.com/mcp"
    assert meta["authorization_servers"] == ["https://auth.example.com"]
    assert meta["scopes_supported"] == list(OPERATOR_SCOPES)
    assert meta["bearer_methods_supported"] == ["header"]


def test_disabled_app_serves_health_and_ready_without_mcp() -> None:
    client, _ = make_app(AppOptions(settings=disabled_settings(), executor=None, validator=None))
    with client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["enabled"] is False
        assert client.post("/mcp", json={}).status_code == 404
        discovery = client.get("/.well-known/oauth-protected-resource")
        assert discovery.status_code == 404
        assert discovery.json()["error"]["code"] == "not_found"


def test_metrics_and_discovery_served_when_enabled() -> None:
    client, _ = make_app()
    with client:
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "ibex_mcp_operator_http_requests_total" in metrics.text
        discovery = client.get("/.well-known/oauth-protected-resource")
        assert discovery.status_code == 200
        assert discovery.json()["resource"] == "http://testserver/mcp"
