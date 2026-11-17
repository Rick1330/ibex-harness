"""create_app wiring: the transport posture must reach the MCP server."""

from __future__ import annotations

from typing import Any

import pytest

from app import main
from tests.fixtures import AppOptions, make_app, make_settings


def _capture_wiring(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch build_mcp_server so a test can inspect the wiring create_app builds."""
    captured: dict[str, Any] = {}
    real_build = main.build_mcp_server

    def spy(wiring: Any, **kwargs: Any) -> Any:
        captured["wiring"] = wiring
        return real_build(wiring, **kwargs)

    monkeypatch.setattr(main, "build_mcp_server", spy)
    return captured


def test_staging_keeps_dns_rebinding_protection_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # Staging requires Redis and the AuthService CA, so it is a protected
    # profile. Accepting the SDK's test hosts there turned DNS-rebinding
    # protection off in exactly the environment it exists to cover.
    captured = _capture_wiring(monkeypatch)
    client, _ = make_app(
        AppOptions(
            settings=make_settings(
                env="staging",
                redis_url="redis://redis:6379/0",
                auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
            )
        )
    )
    with client:
        assert client.get("/health").status_code == 200
    assert captured["wiring"].allow_test_hosts is False


def test_development_accepts_the_sdk_test_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_wiring(monkeypatch)
    client, _ = make_app(AppOptions(settings=make_settings(env="development")))
    with client:
        assert client.get("/health").status_code == 200
    assert captured["wiring"].allow_test_hosts is True
