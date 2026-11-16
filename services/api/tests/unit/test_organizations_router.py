"""HTTP-level anti-enumeration and authz for org routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from authclient.permissions import (
    ADMIN,
    OPERATOR_METADATA_READ,
    OPERATOR_REDACTED_READ,
    ORG_SETTINGS_WRITE,
    READ_ONLY,
    USER_MANAGE,
)

from app.auth.client import AuthFailedError, ValidateResult
from app.authz import assert_path_org
from app.errors import ApiError
from app.schemas.organizations import OrganizationResponse, OrgDeletionJobResponse
from app.session_stub import SESSION_KIND_STEP_UP, TokenIssueOpts, issue_token_opts
from tests.unit.org_user_test_support import (
    ApiClientOpts,
    ManagedClientOpts,
    api_client,
    bearer_headers,
    managed_org_client,
    override_org_session,
    owner_result,
    patched_managed_client,
    sample_org_row,
)


def test_assert_path_org_anti_enumeration() -> None:
    try:
        assert_path_org(uuid4(), uuid4())
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.code == "NOT_FOUND"


def test_cross_tenant_org_get_returns_404() -> None:
    token_org = uuid4()
    other_org = uuid4()
    with api_client(ApiClientOpts(result=owner_result(org_id=token_org))) as (client, _res, _pub):
        override_org_session(client.app)
        try:
            resp = client.get(f"/v1/organizations/{other_org}", headers=bearer_headers())
        finally:
            client.app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "case",
    [
        ("member", "weak", READ_ONLY, "post", "/suspend", None),
        ("member", "mem", ADMIN, "patch", "", {"name": "Nope"}),
    ],
)
def test_org_mutations_denied_for_non_owners(case: tuple) -> None:
    role, token, perms, method, path_suffix, json_body = case
    org_id = uuid4()
    result = ValidateResult(org_id=org_id, permissions=perms, user_id=str(uuid4()))
    with managed_org_client(
        ManagedClientOpts(org_id=org_id, role=role, token=token, result=result)
    ) as (client, _res, _pub):
        call = getattr(client, method)
        kwargs: dict = {"headers": bearer_headers(token)}
        if json_body is not None:
            kwargs["json"] = json_body
        resp = call(f"/v1/organizations/{org_id}{path_suffix}", **kwargs)
    assert resp.status_code == 403


def test_get_and_patch_org_happy_paths() -> None:
    org_id = uuid4()
    get_row = sample_org_row(org_id)
    patch_row = sample_org_row(org_id, name="Renamed")

    async def _fake_get(_session, oid):
        assert oid == org_id
        return OrganizationResponse(**get_row)

    async def _fake_patch(session, oid, body):
        del session, body
        return OrganizationResponse(**patch_row)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="member"),
        "app.routers.organizations.org_service.get_organization",
        _fake_get,
    ) as (client, _res, _pub):
        got = client.get(f"/v1/organizations/{org_id}", headers=bearer_headers())
    assert got.status_code == 200
    assert got.json()["id"] == str(org_id)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="admin"),
        "app.routers.organizations.org_service.patch_organization",
        _fake_patch,
    ) as (client, _res, _pub):
        patched = client.patch(
            f"/v1/organizations/{org_id}",
            headers=bearer_headers(),
            json={"name": "Renamed"},
        )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"


def test_org_read_survives_disabled_operator_feature() -> None:
    """The operator feature gate covers the operator surface, not this org read."""
    org_id = uuid4()
    row = sample_org_row(org_id)

    async def _fake_get(_session, oid):
        assert oid == org_id
        return OrganizationResponse(**row)

    with patched_managed_client(
        ManagedClientOpts(
            org_id=org_id,
            role="viewer",
            result=ValidateResult(
                org_id=org_id,
                permissions=OPERATOR_METADATA_READ,
                user_id="viewer-1",
            ),
        ),
        "app.routers.organizations.org_service.get_organization",
        _fake_get,
    ) as (client, _res, _pub):
        client.app.state.settings.operator_feature_enabled = False
        resp = client.get(f"/v1/organizations/{org_id}", headers=bearer_headers())

    assert resp.status_code == 200
    assert resp.json()["id"] == str(org_id)


def test_org_read_denies_missing_bit_with_operator_disabled() -> None:
    org_id = uuid4()
    with patched_managed_client(
        ManagedClientOpts(
            org_id=org_id,
            result=ValidateResult(org_id=org_id, permissions=READ_ONLY, user_id="member-1"),
        ),
        "app.routers.organizations.org_service.get_organization",
        AsyncMock(),
    ) as (client, _res, _pub):
        client.app.state.settings.operator_feature_enabled = False
        resp = client.get(f"/v1/organizations/{org_id}", headers=bearer_headers())

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_suspend_owner_publishes() -> None:
    org_id = uuid4()
    row = sample_org_row(org_id, status="suspended")

    async def _fake_suspend(session, oid, publisher):
        del session
        await publisher.publish_org_suspend(str(oid))
        return OrganizationResponse(**row)

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="owner"),
        "app.routers.organizations.org_service.suspend_organization",
        _fake_suspend,
    ) as (client, _res, pub):
        resp = client.post(f"/v1/organizations/{org_id}/suspend", headers=bearer_headers())
    assert resp.status_code == 200
    assert pub.org_ids == [str(org_id)]


def test_delete_org_and_job_lookup() -> None:
    org_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)
    calls: list[tuple[str, str]] = []

    async def _fake_enqueue(session, oid, *, enqueue_fn):
        del session
        enqueue_fn(str(job_id), str(oid))
        return OrgDeletionJobResponse(
            id=job_id,
            org_id=oid,
            status="pending",
            error=None,
            created_at=now,
            updated_at=now,
        )

    async def _fake_job(session, oid, jid):
        del session
        return OrgDeletionJobResponse(
            id=jid,
            org_id=oid,
            status="running",
            error=None,
            created_at=now,
            updated_at=now,
            started_at=now,
        )

    with patched_managed_client(
        ManagedClientOpts(
            org_id=org_id,
            role="owner",
            result=_owner_with_token(org_id),
            enqueue_calls=calls,
        ),
        "app.routers.organizations.org_service.enqueue_org_deletion",
        _fake_enqueue,
    ) as (client, _res, _pub):
        deleted = client.delete(
            f"/v1/organizations/{org_id}",
            headers=_delete_headers(
                _step_up_proof(
                    _ProofSpec(
                        org_id=org_id,
                        subject="owner-1",
                        session_id=_DELETE_TOKEN_ID,
                    )
                )
            ),
        )
    assert deleted.status_code == 202
    assert deleted.json()["status"] == "pending"
    assert calls == [(str(job_id), str(org_id))]

    with patched_managed_client(
        ManagedClientOpts(org_id=org_id, role="owner"),
        "app.routers.organizations.org_service.get_deletion_job",
        _fake_job,
    ) as (client, _res, _pub):
        job = client.get(
            f"/v1/organizations/{org_id}/deletion-jobs/{job_id}",
            headers=bearer_headers(),
        )
    assert job.status_code == 200
    assert job.json()["status"] == "running"


# ---------------------------------------------------------------------------
# S02: org deletion requires a bearer-bound step-up proof.
# ---------------------------------------------------------------------------

_DELETE_TOKEN_ID = "tok-delete"


@dataclass(frozen=True)
class _ProofSpec:
    org_id: UUID
    subject: str
    session_id: str
    action: str = "org.delete"
    ttl: int = 300


def _owner_with_token(org_id: UUID, *, user_id: str | None = "owner-1") -> ValidateResult:
    return ValidateResult(
        org_id=org_id,
        permissions=ADMIN | USER_MANAGE | OPERATOR_METADATA_READ | OPERATOR_REDACTED_READ,
        user_id=user_id,
        token_id=_DELETE_TOKEN_ID,
    )


def _owner_opts(
    org_id: UUID,
    *,
    user_id: str | None = "owner-1",
    calls: list[tuple[str, str]] | None = None,
) -> ManagedClientOpts:
    """Managed owner client options; ``calls`` records enqueues when supplied."""
    return ManagedClientOpts(
        org_id=org_id,
        role="owner",
        result=_owner_with_token(org_id, user_id=user_id),
        enqueue_calls=calls,
    )


def _step_up_proof(spec: _ProofSpec) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret="h" * 32,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            org_id=spec.org_id,
            permissions=ORG_SETTINGS_WRITE,
            subject=spec.subject,
            session_kind=SESSION_KIND_STEP_UP,
            ttl_seconds=spec.ttl,
            session_id=spec.session_id,
            action=spec.action,
        )
    )


def _delete_headers(proof: str) -> dict[str, str]:
    return {**bearer_headers(), "X-IBEX-Step-Up": proof}


def _pending_job(org_id: UUID) -> OrgDeletionJobResponse:
    now = datetime.now(UTC)
    return OrgDeletionJobResponse(
        id=uuid4(),
        org_id=org_id,
        status="pending",
        error=None,
        created_at=now,
        updated_at=now,
    )


def _enqueue_fake(calls: list[tuple[str, str]]):
    async def _fake_enqueue(_session, org_id, *, enqueue_fn):
        job = _pending_job(org_id)
        enqueue_fn(str(job.id), str(org_id))
        return job

    return _fake_enqueue


def _refused_delete(
    org_id: UUID, headers: dict[str, str], *, operator_enabled: bool = True
) -> None:
    """Assert the step-up gate refuses the delete and enqueues no job.

    ``headers`` carries the refusal under test: a bare bearer token, or a proof
    that is misbound or expired.
    """
    service = AsyncMock()
    with patched_managed_client(
        _owner_opts(org_id),
        "app.routers.organizations.org_service.enqueue_org_deletion",
        service,
    ) as (client, _res, _pub):
        if not operator_enabled:
            client.app.state.settings.operator_feature_enabled = False
        resp = client.delete(f"/v1/organizations/{org_id}", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    assert resp.json()["error"]["message"] == "Step-up authentication required"
    service.assert_not_awaited()


def _accepted_delete(
    org_id: UUID,
    proof: str,
    *,
    user_id: str | None = "owner-1",
    operator_enabled: bool = True,
) -> httpx.Response:
    """Assert the delete is accepted and enqueues exactly one job."""
    calls: list[tuple[str, str]] = []
    with patched_managed_client(
        _owner_opts(org_id, user_id=user_id, calls=calls),
        "app.routers.organizations.org_service.enqueue_org_deletion",
        _enqueue_fake(calls),
    ) as (client, _res, _pub):
        if not operator_enabled:
            client.app.state.settings.operator_feature_enabled = False
        resp = client.delete(f"/v1/organizations/{org_id}", headers=_delete_headers(proof))

    assert resp.status_code == 202
    assert len(calls) == 1
    return resp


def test_delete_org_without_proof_is_refused_and_enqueues_nothing() -> None:
    _refused_delete(uuid4(), bearer_headers())


def test_delete_org_with_valid_proof_enqueues_pending_job() -> None:
    org_id = uuid4()
    proof = _step_up_proof(
        _ProofSpec(org_id=org_id, subject="owner-1", session_id=_DELETE_TOKEN_ID)
    )
    resp = _accepted_delete(org_id, proof)
    assert resp.json()["status"] == "pending"


@pytest.mark.parametrize(
    "spec",
    [
        pytest.param({"org_id": "other"}, id="wrong-org"),
        pytest.param({"subject": "other-user"}, id="wrong-subject"),
        pytest.param({"session_id": "other-session"}, id="wrong-session"),
        pytest.param({"action": "org.suspend"}, id="wrong-action"),
        pytest.param({"ttl": -10}, id="expired"),
    ],
)
def test_delete_org_refuses_misbound_or_expired_proof(spec: dict[str, object]) -> None:
    org_id = uuid4()
    values: dict[str, object] = {
        "org_id": org_id,
        "subject": "owner-1",
        "session_id": _DELETE_TOKEN_ID,
        "action": "org.delete",
        "ttl": 300,
    }
    values.update(spec)
    if values["org_id"] == "other":
        values["org_id"] = uuid4()
    proof = _step_up_proof(
        _ProofSpec(
            org_id=values["org_id"],  # type: ignore[arg-type]
            subject=str(values["subject"]),
            session_id=str(values["session_id"]),
            action=str(values["action"]),
            ttl=int(values["ttl"]),  # type: ignore[arg-type]
        )
    )
    _refused_delete(org_id, _delete_headers(proof))


def test_delete_org_binds_a_userless_token_to_its_own_id() -> None:
    """The binding derivation for a userless token, with the role gate stubbed out.

    A PAT has no user id, so the proof binds to the token id the caller cannot
    choose. This pins the derivation, not a capability: the real role gate
    refuses a userless caller before step-up is reached (the next test), and no
    proof is issued for one.
    """
    org_id = uuid4()
    proof = _step_up_proof(
        _ProofSpec(org_id=org_id, subject=_DELETE_TOKEN_ID, session_id=_DELETE_TOKEN_ID)
    )
    _accepted_delete(org_id, proof, user_id=None)


def test_delete_org_refuses_a_userless_token_at_the_role_gate() -> None:
    """A userless PAT never reaches the step-up check.

    ``RequireOwnerOrgSettings`` depends on ``load_caller_role``, which requires a
    user id, so ``org.delete`` is not reachable with a bearer-only identity. The
    userless branch of the binding is therefore not a deletion capability.
    """
    org_id = uuid4()
    calls: list[tuple[str, str]] = []

    with api_client(
        ApiClientOpts(
            token="owner-token",
            result=_owner_with_token(org_id, user_id=None),
            enqueue_calls=calls,
        )
    ) as (client, _res, _pub):
        override_org_session(client.app)
        resp = client.delete(
            f"/v1/organizations/{org_id}",
            headers=_delete_headers("unused-proof"),
        )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    assert resp.json()["error"]["message"] == "User-scoped token required"
    assert calls == []


def test_delete_org_rejects_a_replayed_proof() -> None:
    """AuthService consumes the proof's jti; a second use of the same proof is refused."""
    org_id = uuid4()
    calls: list[tuple[str, str]] = []
    consumed: set[str] = set()

    async def _single_use(_rpc, params) -> None:
        if params.token in consumed:
            raise AuthFailedError("step-up already consumed")
        consumed.add(params.token)

    with (
        patch("app.step_up.consume_step_up", new=_single_use),
        patched_managed_client(
            ManagedClientOpts(
                org_id=org_id,
                role="owner",
                result=_owner_with_token(org_id),
                enqueue_calls=calls,
                environment="staging",
                # The delete route is bearer-only, so the operator surface is
                # irrelevant here; a staging client cannot fabricate the full
                # non-development operator material the settings validators want.
                operator_feature_enabled=False,
            ),
            "app.routers.organizations.org_service.enqueue_org_deletion",
            _enqueue_fake(calls),
        ) as (client, _res, _pub),
    ):
        headers = _delete_headers("opaque-proof")
        first = client.delete(f"/v1/organizations/{org_id}", headers=headers)
        second = client.delete(f"/v1/organizations/{org_id}", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 403
    assert second.json()["error"]["message"] == "Step-up authentication required"
    assert len(calls) == 1


def test_delete_org_step_up_is_independent_of_the_operator_feature_flag() -> None:
    org_id = uuid4()
    proof = _step_up_proof(
        _ProofSpec(org_id=org_id, subject="owner-1", session_id=_DELETE_TOKEN_ID)
    )
    _refused_delete(org_id, bearer_headers(), operator_enabled=False)
    _accepted_delete(org_id, proof, operator_enabled=False)
