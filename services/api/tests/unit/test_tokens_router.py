"""Unit tests for token management routes and service behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from apierror_py import (
    INSUFFICIENT_PERMISSIONS,
    NOT_FOUND,
    PERMISSION_ELEVATION_DENIED,
    VALIDATION_ERROR,
)
from authclient.permissions import (
    ADMIN,
    MEMORY_READ,
    READ_ONLY,
    TOKEN_CREATE,
    TOKEN_REVOKE,
)
from authclient.tokens import FakeTokenManager, TokenMetadataWire

from app.auth.client import ValidateResult
from tests.unit.org_user_test_support import ManagedClientOpts, bearer_headers, managed_org_client


def _permission_client(
    org_id: UUID,
    permissions: int,
    *,
    mgr: FakeTokenManager | None = None,
):
    return managed_org_client(
        ManagedClientOpts(
            org_id=org_id,
            token_manager=mgr or FakeTokenManager(),
            result=ValidateResult(
                org_id=org_id,
                permissions=permissions,
                user_id=str(uuid4()),
            ),
        )
    )


def _seed_token(mgr: FakeTokenManager, org_id: UUID, token_id: UUID) -> None:
    mgr.seed(
        str(org_id),
        TokenMetadataWire(
            token_id=str(token_id),
            name="tmp",
            prefix="ibex_pat_tmp",
            permissions=MEMORY_READ,
            created_at=datetime.now(UTC),
        ),
    )


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
    with _permission_client(org_id, MEMORY_READ | TOKEN_CREATE) as (
        client,
        _res,
        _pub,
    ):
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


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/v1/tokens", None),
        ("post", "/v1/tokens", {"name": "denied"}),
        ("get", "/v1/tokens/{token_id}", None),
        ("delete", "/v1/tokens/{token_id}", None),
    ],
)
def test_token_routes_deny_viewer_bitmap(
    method: str, path: str, payload: dict | None
) -> None:
    org_id = uuid4()
    with _permission_client(org_id, READ_ONLY) as (client, _res, _pub):
        kwargs: dict = {"headers": bearer_headers()}
        if payload is not None:
            kwargs["json"] = payload
        resp = getattr(client, method)(path.format(token_id=uuid4()), **kwargs)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


def test_token_create_list_get_with_token_create_permission() -> None:
    org_id = uuid4()
    with _permission_client(org_id, TOKEN_CREATE) as (client, _res, _pub):
        created = client.post(
            "/v1/tokens", headers=bearer_headers(), json={"name": "ci"}
        )
        assert created.status_code == 201, created.text
        token_id = created.json()["id"]
        assert client.get("/v1/tokens", headers=bearer_headers()).status_code == 200
        assert (
            client.get(f"/v1/tokens/{token_id}", headers=bearer_headers()).status_code
            == 200
        )


@pytest.mark.parametrize(
    ("permissions", "expected_status"),
    [(TOKEN_REVOKE, 204), (TOKEN_CREATE, 403)],
)
def test_token_delete_requires_token_revoke(
    permissions: int, expected_status: int
) -> None:
    org_id = uuid4()
    token_id = uuid4()
    mgr = FakeTokenManager()
    _seed_token(mgr, org_id, token_id)
    with _permission_client(org_id, permissions, mgr=mgr) as (client, _res, _pub):
        resp = client.delete(f"/v1/tokens/{token_id}", headers=bearer_headers())
    assert resp.status_code == expected_status
    if expected_status == 204:
        assert (str(org_id), str(token_id)) in mgr.revoked
    else:
        assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


@pytest.mark.parametrize(
    ("permissions", "expected_status"),
    [(TOKEN_CREATE, 201), (TOKEN_REVOKE, 403)],
)
def test_token_create_requires_token_create(
    permissions: int, expected_status: int
) -> None:
    org_id = uuid4()
    with _permission_client(org_id, permissions) as (client, _res, _pub):
        resp = client.post(
            "/v1/tokens", headers=bearer_headers(), json={"name": "ci"}
        )
    assert resp.status_code == expected_status
    if expected_status == 403:
        assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS
