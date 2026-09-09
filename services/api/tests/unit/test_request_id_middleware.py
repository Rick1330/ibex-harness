"""HTTP request-ID middleware round-trip."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app
from app.reqid import HEADER


def _client() -> TestClient:
    settings = Settings(database_url=None)
    org = uuid4()
    validator = StaticTokenValidator(
        {"tok": ValidateResult(org_id=org, permissions=0)},
    )
    application = create_app(settings=settings, validator=validator)
    return TestClient(application)


def test_echoes_generated_request_id() -> None:
    with _client() as client:
        response = client.get("/health")
        assert response.status_code == 200
        rid = response.headers.get(HEADER)
        assert rid is not None
        assert UUID(rid).version == 7


def test_honors_valid_inbound_request_id() -> None:
    inbound = str(uuid4())
    with _client() as client:
        response = client.get("/health", headers={HEADER: inbound})
        assert response.headers.get(HEADER) == inbound


def test_replaces_invalid_inbound_request_id() -> None:
    with _client() as client:
        response = client.get("/health", headers={HEADER: "garbage"})
        rid = response.headers.get(HEADER)
        assert rid is not None
        assert rid != "garbage"
        assert UUID(rid).version == 7


def test_ready_envelope_has_single_request_id_header() -> None:
    with _client() as client:
        response = client.get("/ready")
        assert response.status_code == 503
        # Starlette/httpx expose get_list for multi-value headers when present.
        values = response.headers.get_list(HEADER) if hasattr(response.headers, "get_list") else None
        if values is not None:
            assert len(values) == 1
            assert values[0] == response.json()["error"]["request_id"]
        else:
            raw = response.headers.get(HEADER)
            assert raw is not None
            assert "," not in raw
            assert raw == response.json()["error"]["request_id"]
