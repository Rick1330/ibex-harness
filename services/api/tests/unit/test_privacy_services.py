"""Unit tests for legal hold + capture policy services."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import LEGAL_HOLD_SCOPE_CONFLICT, NOT_FOUND
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.schemas.capture_policies import CapturePolicyCreate, CapturePolicyPatch
from app.schemas.legal_holds import LegalHoldCreate
from app.services import capture_policies as capture_svc
from app.services import legal_holds as hold_svc

_TS = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)


def _integrity(constraint: str) -> IntegrityError:
    class _Orig(Exception):
        def __init__(self) -> None:
            self.constraint_name = constraint

    return IntegrityError("stmt", {}, _Orig())


@pytest.mark.asyncio
async def test_set_hold_conflict_when_active() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    org = uuid4()
    user = uuid4()
    session.execute = AsyncMock(side_effect=_integrity("legal_holds_one_active_per_scope"))
    with pytest.raises(ApiError) as ei:
        await hold_svc.set_hold(session, org, LegalHoldCreate(reason="x"), set_by=user)
    assert ei.value.code == LEGAL_HOLD_SCOPE_CONFLICT
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_clear_hold_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )
    with pytest.raises(ApiError) as ei:
        await hold_svc.clear_hold(session, uuid4(), uuid4(), cleared_by=uuid4())
    assert ei.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_resolve_mode_default() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    mode = await capture_svc.resolve_mode(session, uuid4())
    assert mode == "metadata_only"


@pytest.mark.asyncio
async def test_get_policy_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )
    with pytest.raises(ApiError) as ei:
        await capture_svc.get_policy(session, uuid4(), uuid4())
    assert ei.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_delete_policy_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    with pytest.raises(ApiError) as ei:
        await capture_svc.delete_policy(session, uuid4(), uuid4())
    assert ei.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_create_policy_happy() -> None:
    session = AsyncMock()
    org = uuid4()
    pid = uuid4()
    row = {
        "id": pid,
        "org_id": org,
        "agent_id": None,
        "mode": "redacted",
        "priority": 10,
        "created_at": _TS,
        "updated_at": _TS,
    }
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=row)))
        )
    )
    session.commit = AsyncMock()
    out = await capture_svc.create_policy(
        session, org, CapturePolicyCreate(mode="redacted", priority=10)
    )
    assert out.id == pid
    assert out.mode == "redacted"


@pytest.mark.asyncio
async def test_patch_policy_updates() -> None:
    session = AsyncMock()
    org = uuid4()
    pid = uuid4()
    current = {
        "id": pid,
        "org_id": org,
        "agent_id": None,
        "mode": "none",
        "priority": 1,
        "created_at": _TS,
        "updated_at": _TS,
    }
    updated = {**current, "mode": "full", "priority": 2}
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(
                mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=current)))
            ),
            MagicMock(
                mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=updated)))
            ),
        ]
    )
    session.commit = AsyncMock()
    out = await capture_svc.patch_policy(
        session, org, pid, CapturePolicyPatch(mode="full", priority=2)
    )
    assert out.mode == "full"
    assert out.priority == 2
