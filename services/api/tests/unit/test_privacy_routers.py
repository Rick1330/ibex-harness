"""Direct unit tests for privacy router handlers (deps injected)."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS
from authclient.permissions import (
    LEGAL_HOLD_MANAGE,
    OPERATOR_METADATA_READ,
    READ_ONLY,
)

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.routers import capture_policies as capture_router
from app.routers import legal_holds as holds_router
from app.schemas.capture_policies import (
    CapturePolicyCreate,
    CapturePolicyPatch,
    CapturePolicyResponse,
)
from app.schemas.legal_holds import LegalHoldCreate, LegalHoldResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
)

_TS = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)


def _token(org_id, *, user_id=None, permissions: int = 0) -> ValidateResult:
    return ValidateResult(org_id=org_id, permissions=permissions, user_id=user_id)


def _client_result(org_id: UUID, permissions: int) -> ValidateResult:
    return ValidateResult(
        org_id=org_id,
        permissions=permissions,
        user_id=str(uuid4()),
    )


def _hold_resp(org: UUID, *, user: UUID, cleared: bool = False) -> LegalHoldResponse:
    return LegalHoldResponse(
        id=uuid4(),
        org_id=org,
        scope="org",
        reason="x",
        set_by=user,
        cleared_by=user if cleared else None,
        created_at=_TS,
        cleared_at=_TS if cleared else None,
    )


@pytest.mark.asyncio
async def test_list_holds_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    expected = [_hold_resp(org, user=uuid4())]
    monkeypatch.setattr(
        holds_router.hold_service, "list_active_holds", AsyncMock(return_value=expected)
    )
    out = await holds_router.list_holds(
        org, _token(org, permissions=LEGAL_HOLD_MANAGE), AsyncMock()
    )
    assert out == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call",),
    [
        ("set",),
        ("clear",),
    ],
)
async def test_hold_mutations_require_user_id(call: str) -> None:
    org = uuid4()
    token = _token(org, user_id=None)
    session = AsyncMock()
    if call == "set":
        pending = holds_router.set_hold(org, LegalHoldCreate(reason="x"), token, session)
    else:
        pending = holds_router.clear_hold(org, uuid4(), token, session)
    with pytest.raises(ApiError) as ei:
        await pending
    assert ei.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "cleared"),
    [
        ("set", False),
        ("clear", True),
    ],
)
async def test_hold_mutations_ok(
    monkeypatch: pytest.MonkeyPatch, call: str, cleared: bool
) -> None:
    org = uuid4()
    user = uuid4()
    resp = _hold_resp(org, user=user, cleared=cleared)
    mock = AsyncMock(return_value=resp)
    attr = "set_hold" if call == "set" else "clear_hold"
    monkeypatch.setattr(holds_router.hold_service, attr, mock)
    token = _token(org, user_id=str(user))
    if call == "set":
        out = await holds_router.set_hold(org, LegalHoldCreate(reason="x"), token, AsyncMock())
        assert out.id == resp.id
    else:
        out = await holds_router.clear_hold(org, resp.id, token, AsyncMock())
        assert out.cleared_at is not None
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_capture_list_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    ctx = capture_router._Ctx(org_id=org, session=AsyncMock())
    expected = [
        CapturePolicyResponse(
            id=uuid4(),
            org_id=org,
            agent_id=None,
            mode="metadata_only",
            priority=1,
            created_at=_TS,
            updated_at=_TS,
        )
    ]
    monkeypatch.setattr(
        capture_router.capture_service, "list_policies", AsyncMock(return_value=expected)
    )
    assert await capture_router.list_capture_policies(ctx) == expected


@pytest.mark.asyncio
async def test_capture_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    ctx = capture_router._Ctx(org_id=org, session=AsyncMock())
    monkeypatch.setattr(
        capture_router.capture_service, "resolve_mode", AsyncMock(return_value="full")
    )
    assert await capture_router.resolve_capture_mode(ctx, agent_id=None) == {"mode": "full"}


@pytest.mark.asyncio
async def test_capture_create_patch_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    ctx = capture_router._Ctx(org_id=org, session=AsyncMock())
    pid = uuid4()
    row = CapturePolicyResponse(
        id=pid,
        org_id=org,
        agent_id=None,
        mode="redacted",
        priority=2,
        created_at=_TS,
        updated_at=_TS,
    )
    monkeypatch.setattr(
        capture_router.capture_service, "create_policy", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(
        capture_router.capture_service, "patch_policy", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(capture_router.capture_service, "delete_policy", AsyncMock())
    assert (
        await capture_router.create_capture_policy(CapturePolicyCreate(mode="redacted"), ctx)
    ).id == pid
    assert (
        await capture_router.patch_capture_policy(pid, CapturePolicyPatch(priority=3), ctx)
    ).id == pid
    await capture_router.delete_capture_policy(pid, ctx)


def test_make_ctx_asserts_org() -> None:
    org = uuid4()
    session = MagicMock()
    ctx = capture_router._make_ctx(org, org, session)
    assert ctx.org_id == org
    other = uuid4()
    with pytest.raises(ApiError):
        capture_router._make_ctx(org, other, session)


@dataclass(frozen=True)
class _OrgRead:
    """One org-scoped GET: path suffix, optional stubbed capture service, gate state."""

    suffix: str
    operator_feature_enabled: bool = True
    service: str | None = None
    value: object = None


_CAPTURE_READ_SUFFIXES = ("/capture-policies", "/capture-policies/resolved")

_CAPTURE_READS = (
    pytest.param(
        _OrgRead("/capture-policies", service="list_policies", value=[]),
        id="list-policies",
    ),
    pytest.param(
        _OrgRead("/capture-policies/resolved", service="resolve_mode", value="full"),
        id="resolved-mode",
    ),
)


def _org_read_response(case: _OrgRead, permissions: int):
    org = uuid4()
    opts = ManagedClientOpts(org_id=org, result=_client_result(org, permissions))
    with ExitStack() as stack:
        client, _res, _pub = stack.enter_context(managed_org_client(opts))
        if case.service is not None:
            stack.enter_context(
                patch(
                    f"app.services.capture_policies.{case.service}",
                    new=AsyncMock(return_value=case.value),
                )
            )
        client.app.state.settings.operator_feature_enabled = case.operator_feature_enabled
        return client.get(f"/v1/organizations/{org}{case.suffix}", headers=bearer_headers())


def _assert_org_read_allowed(case: _OrgRead) -> None:
    assert _org_read_response(case, OPERATOR_METADATA_READ).status_code == 200


def _assert_org_read_denied(case: _OrgRead) -> None:
    resp = _org_read_response(case, READ_ONLY)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == INSUFFICIENT_PERMISSIONS


@pytest.mark.parametrize("suffix", ("/legal-holds", *_CAPTURE_READ_SUFFIXES))
def test_org_read_routes_deny_viewer_bitmap(suffix: str) -> None:
    _assert_org_read_denied(_OrgRead(suffix))


def test_list_holds_with_legal_hold_manage() -> None:
    org = uuid4()
    with (
        managed_org_client(
            ManagedClientOpts(
                org_id=org,
                result=_client_result(org, LEGAL_HOLD_MANAGE),
            )
        ) as (client, _res, _pub),
        patch(
            "app.services.legal_holds.list_active_holds",
            new=AsyncMock(return_value=[]),
        ),
    ):
        resp = client.get(
            f"/v1/organizations/{org}/legal-holds", headers=bearer_headers()
        )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize("case", _CAPTURE_READS)
def test_capture_policy_reads_with_operator_metadata_read(case: _OrgRead) -> None:
    _assert_org_read_allowed(case)


@pytest.mark.parametrize("case", _CAPTURE_READS)
def test_capture_policy_reads_survive_disabled_operator_feature(
    case: _OrgRead,
) -> None:
    """The operator feature gate covers the operator surface, not these org reads."""
    _assert_org_read_allowed(replace(case, operator_feature_enabled=False))


@pytest.mark.parametrize("suffix", _CAPTURE_READ_SUFFIXES)
def test_capture_policy_reads_still_deny_missing_bit_with_operator_disabled(
    suffix: str,
) -> None:
    _assert_org_read_denied(_OrgRead(suffix, operator_feature_enabled=False))
