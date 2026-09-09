"""Auth dependency and error envelope HTTP tests."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app


def _app(*, available: bool = True) -> TestClient:
    settings = Settings(database_url=None)
    org = uuid4()
    validator = StaticTokenValidator(
        {"good": ValidateResult(org_id=org, permissions=1)},
        available=available,
    )
    return TestClient(create_app(settings=settings, validator=validator))


def test_missing_token_uses_ibex_envelope() -> None:
    with _app() as client:
        response = client.get("/v1/tenant/ping")
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["code"] == "MISSING_TOKEN"
        assert "request_id" in body["error"]
        assert "timestamp" in body["error"]


def test_invalid_token_envelope() -> None:
    with _app() as client:
        response = client.get(
            "/v1/tenant/ping",
            headers={"Authorization": "Bearer bad"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_org_suspended_envelope() -> None:
    from authclient.revoke import NoopTokenRevoker
    from fastapi.testclient import TestClient

    from app.auth.client import StaticTokenValidator
    from app.auth.errors import OrgSuspendedError
    from app.config import Settings
    from app.main import ApiRuntimeOverrides, create_app

    class _Suspended(StaticTokenValidator):
        async def validate(self, access_token: str) -> ValidateResult:
            del access_token
            raise OrgSuspendedError("organization is suspended")

    settings = Settings(database_url=None)
    app = create_app(
        settings=settings,
        validator=_Suspended({}),
        runtime=ApiRuntimeOverrides(token_revoker=NoopTokenRevoker()),
    )
    with TestClient(app) as client:
        resp = client.get(
            "/v1/tenant/ping",
            headers={"Authorization": "Bearer any"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ORG_SUSPENDED"
