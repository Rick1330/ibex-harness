"""HTTP proof that unhandled exceptions use the IBEX envelope."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import create_app


def test_unhandled_exception_returns_ibex_envelope() -> None:
    """Prove unhandled_error_handler runs over HTTP (not only unit-invoked)."""
    settings = Settings(database_url=None)
    application = create_app(settings=settings, validator=StaticTokenValidator({}))

    @application.get("/__test/boom")
    async def _boom() -> None:
        raise RuntimeError("deliberate unhandled failure")

    inbound = str(uuid4())
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/__test/boom", headers={"X-Request-ID": inbound})

    assert response.status_code == 500
    body = response.json()
    err = body["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["request_id"] == inbound
    assert err["timestamp"]
    assert response.headers.get("X-Request-ID") == inbound
