"""Direct unit tests for privacy router handlers (deps injected)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS

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

_TS = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)


def _token(org_id, *, user_id=None) -> ValidateResult:
    return ValidateResult(org_id=org_id, permissions=0, user_id=user_id)


@pytest.mark.asyncio
async def test_list_holds_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    expected = [
        LegalHoldResponse(
            id=uuid4(),
            org_id=org,
            scope="org",
            reason="r",
            set_by=uuid4(),
            cleared_by=None,
            created_at=_TS,
            cleared_at=None,
        )
    ]
    monkeypatch.setattr(
        holds_router.hold_service, "list_active_holds", AsyncMock(return_value=expected)
    )
    out = await holds_router.list_holds(org, _token(org), AsyncMock())
    assert out == expected


@pytest.mark.asyncio
async def test_set_hold_requires_user_id() -> None:
    org = uuid4()
    with pytest.raises(ApiError) as ei:
        await holds_router.set_hold(
            org, LegalHoldCreate(reason="x"), _token(org, user_id=None), AsyncMock()
        )
    assert ei.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
async def test_set_hold_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    user = uuid4()
    resp = LegalHoldResponse(
        id=uuid4(),
        org_id=org,
        scope="org",
        reason="x",
        set_by=user,
        cleared_by=None,
        created_at=_TS,
        cleared_at=None,
    )
    mock = AsyncMock(return_value=resp)
    monkeypatch.setattr(holds_router.hold_service, "set_hold", mock)
    out = await holds_router.set_hold(
        org, LegalHoldCreate(reason="x"), _token(org, user_id=str(user)), AsyncMock()
    )
    assert out.id == resp.id
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_clear_hold_requires_user_id() -> None:
    org = uuid4()
    with pytest.raises(ApiError) as ei:
        await holds_router.clear_hold(org, uuid4(), _token(org, user_id=None), AsyncMock())
    assert ei.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
async def test_clear_hold_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid4()
    user = uuid4()
    resp = LegalHoldResponse(
        id=uuid4(),
        org_id=org,
        scope="org",
        reason="x",
        set_by=user,
        cleared_by=user,
        created_at=_TS,
        cleared_at=_TS,
    )
    mock = AsyncMock(return_value=resp)
    monkeypatch.setattr(holds_router.hold_service, "clear_hold", mock)
    out = await holds_router.clear_hold(
        org, resp.id, _token(org, user_id=str(user)), AsyncMock()
    )
    assert out.cleared_at is not None


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
    assert (await capture_router.create_capture_policy(CapturePolicyCreate(mode="redacted"), ctx)).id == pid
    assert (
        await capture_router.patch_capture_policy(pid, CapturePolicyPatch(priority=3), ctx)
    ).id == pid
    await capture_router.delete_capture_policy(pid, ctx)


def test_make_ctx_asserts_org() -> None:
    org = uuid4()
    ctx = capture_router._make_ctx(org, org, MagicMock())
    assert ctx.org_id == org
    with pytest.raises(ApiError):
        capture_router._make_ctx(org, uuid4(), MagicMock())
