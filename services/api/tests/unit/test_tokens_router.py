"""Unit tests for token management routes and service behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from apierror_py import NOT_FOUND, PERMISSION_ELEVATION_DENIED, VALIDATION_ERROR
from authclient.permissions import ADMIN, MEMORY_READ, TOKEN_CREATE
from authclient.tokens import FakeTokenManager, TokenMetadataWire

from app.auth.client import ValidateResult
from tests.unit.org_user_test_support import ManagedClientOpts, bearer_headers, managed_org_client


def test_create_returns_plaintext_once_list_omits_token() -> None:
    org_id = uuid4()
    mgr = FakeTokenManager()
    with managed_org_client(
        ManagedClientOpts(
            org_id=org_id,
            token_manager=mgr,
            result=ValidateResult(
                org_id=org_id,
                permissions=ADMIN,
                user_id=str(uuid4()),
            ),
        )
    ) as (client, _res, _pub):
        created = client.post(
            "/v1/tokens",
            headers=bearer_headers(),
            json={"name": "ci", "permissions": ["memory:read", "session:create"]},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert "token" in body
        assert body["token"].startswith("ibex_pat_")
        assert "allowed_ips" not in body
        assert set(body["permissions"]) == {"memory:read", "session:create"}

        listed = client.get("/v1/tokens", headers=bearer_headers())
        assert listed.status_code == 200
        rows = listed.json()["data"]
        assert len(rows) == 1
        assert "token" not in rows[0]
        assert rows[0]["id"] == body["id"]

        got = client.get(f"/v1/tokens/{body['id']}", headers=bearer_headers())
        assert got.status_code == 200
        assert "token" not in got.json()


def test_permission_elevation_denied() -> None:
    org_id = uuid4()
    with managed_org_client(
        ManagedClientOpts(
            org_id=org_id,
            token_manager=FakeTokenManager(),
            result=ValidateResult(
                org_id=org_id,
                permissions=MEMORY_READ | TOKEN_CREATE,
                user_id=str(uuid4()),
            ),
        )
    ) as (client, _res, _pub):
        resp = client.post(
            "/v1/tokens",
            headers=bearer_headers(),
            json={"name": "elev", "permissions": ["admin:user_manage"]},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == PERMISSION_ELEVATION_DENIED


def test_invalid_cidr_validation_error() -> None:
    org_id = uuid4()
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, token_manager=FakeTokenManager())
    ) as (client, _res, _pub):
        resp = client.post(
            "/v1/tokens",
            headers=bearer_headers(),
            json={
                "name": "bad-cidr",
                "permissions": ["memory:read"],
                "allowed_ips": ["not-a-cidr"],
            },
        )
        # Project maps VALIDATION_ERROR → 400 (sketch said 422).
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == VALIDATION_ERROR
        fields = resp.json()["error"].get("field_errors") or []
        assert any("allowed_ips" in fe.get("field", "") for fe in fields)


def test_delete_revokes_and_missing_is_404() -> None:
    org_id = uuid4()
    mgr = FakeTokenManager()
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, token_manager=mgr)
    ) as (client, _res, _pub):
        created = client.post(
            "/v1/tokens",
            headers=bearer_headers(),
            json={"name": "tmp", "permissions": ["memory:read"]},
        )
        tid = created.json()["id"]
        deleted = client.delete(f"/v1/tokens/{tid}", headers=bearer_headers())
        assert deleted.status_code == 204
        assert (str(org_id), tid) in mgr.revoked

        missing = client.delete(f"/v1/tokens/{uuid4()}", headers=bearer_headers())
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == NOT_FOUND


def test_get_unknown_token_404() -> None:
    org_id = uuid4()
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, token_manager=FakeTokenManager())
    ) as (client, _res, _pub):
        resp = client.get(f"/v1/tokens/{uuid4()}", headers=bearer_headers())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == NOT_FOUND


def test_iso_token_cross_tenant_get_delete_404() -> None:
    """TestAPI_ISO_TOKEN_*: org A cannot read/revoke org B's tokens (anti-enumeration 404)."""
    org_a = uuid4()
    org_b = uuid4()
    foreign_id = uuid4()
    mgr = FakeTokenManager()
    mgr.seed(
        str(org_b),
        TokenMetadataWire(
            token_id=str(foreign_id),
            name="foreign",
            prefix="ibex_pat_foreign",
            permissions=MEMORY_READ,
            created_at=datetime.now(UTC),
        ),
    )
    with managed_org_client(
        ManagedClientOpts(org_id=org_a, token_manager=mgr)
    ) as (client, _res, _pub):
        get_resp = client.get(f"/v1/tokens/{foreign_id}", headers=bearer_headers())
        assert get_resp.status_code == 404
        assert get_resp.json()["error"]["code"] == NOT_FOUND

        del_resp = client.delete(f"/v1/tokens/{foreign_id}", headers=bearer_headers())
        assert del_resp.status_code == 404
        assert del_resp.json()["error"]["code"] == NOT_FOUND

        listed = client.get("/v1/tokens", headers=bearer_headers())
        assert listed.status_code == 200
        ids = {UUID(row["id"]) for row in listed.json()["data"]}
        assert foreign_id not in ids
