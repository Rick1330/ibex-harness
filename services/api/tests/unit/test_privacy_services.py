"""Unit tests for legal hold + capture policy services."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import (
    CAPTURE_POLICY_CONFLICT,
    LEGAL_HOLD_SCOPE_CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
)
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


def _hold_row(*, org, hold_id=None, cleared=False):
    return {
        "id": hold_id or uuid4(),
        "org_id": org,
        "scope": "org",
        "reason": "investigation",
        "set_by": uuid4(),
        "cleared_by": uuid4() if cleared else None,
        "created_at": _TS,
        "cleared_at": _TS if cleared else None,
    }


def _policy_row(*, org, pid=None, mode="redacted", priority=1):
    return {
        "id": pid or uuid4(),
        "org_id": org,
        "agent_id": None,
        "mode": mode,
        "priority": priority,
        "created_at": _TS,
        "updated_at": _TS,
    }


def _mappings_first(row):
    return MagicMock(
        mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value=row)))
    )


def _mappings_all(rows):
    return MagicMock(
        mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    )


@pytest.mark.asyncio
async def test_set_hold_conflict_when_active() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    org = uuid4()
    user = uuid4()
    body = LegalHoldCreate(reason="x")
    session.execute = AsyncMock(side_effect=_integrity("legal_holds_one_active_per_scope"))
    with pytest.raises(ApiError) as ei:
        await hold_svc.set_hold(session, org, body, set_by=user)
    assert ei.value.code == LEGAL_HOLD_SCOPE_CONFLICT
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_set_hold_requires_user() -> None:
    session = AsyncMock()
    org = uuid4()
    body = LegalHoldCreate(reason="x")
    with pytest.raises(ApiError) as ei:
        await hold_svc.set_hold(session, org, body, set_by=None)  # type: ignore[arg-type]
    assert ei.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_set_hold_happy() -> None:
    session = AsyncMock()
    org = uuid4()
    user = uuid4()
    row = _hold_row(org=org)
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(),  # advisory lock
            _mappings_first(row),
        ]
    )
    session.commit = AsyncMock()
    out = await hold_svc.set_hold(session, org, LegalHoldCreate(reason="investigation"), set_by=user)
    assert out.id == row["id"]
    assert out.reason == "investigation"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_set_hold_insert_no_row() -> None:
    session = AsyncMock()
    org = uuid4()
    body = LegalHoldCreate(reason="x")
    user = uuid4()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            _mappings_first(None),
        ]
    )
    with pytest.raises(ApiError) as ei:
        await hold_svc.set_hold(session, org, body, set_by=user)
    assert ei.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_set_hold_other_integrity_reraises() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    org = uuid4()
    body = LegalHoldCreate(reason="x")
    user = uuid4()
    session.execute = AsyncMock(side_effect=_integrity("some_other_constraint"))
    with pytest.raises(IntegrityError):
        await hold_svc.set_hold(session, org, body, set_by=user)


@pytest.mark.asyncio
async def test_list_active_holds() -> None:
    session = AsyncMock()
    org = uuid4()
    row = _hold_row(org=org)
    session.execute = AsyncMock(return_value=_mappings_all([row]))
    out = await hold_svc.list_active_holds(session, org)
    assert len(out) == 1
    assert out[0].id == row["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind",),
    [
        ("clear_hold",),
        ("get_policy",),
        ("delete_policy",),
    ],
)
async def test_privacy_not_found(kind: str) -> None:
    session = AsyncMock()
    org, oid, actor = uuid4(), uuid4(), uuid4()
    if kind == "delete_policy":
        session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        call = capture_svc.delete_policy(session, org, oid)
    elif kind == "get_policy":
        session.execute = AsyncMock(return_value=_mappings_first(None))
        call = capture_svc.get_policy(session, org, oid)
    else:
        session.execute = AsyncMock(return_value=_mappings_first(None))
        call = hold_svc.clear_hold(session, org, oid, cleared_by=actor)
    with pytest.raises(ApiError) as ei:
        await call
    assert ei.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_clear_hold_happy() -> None:
    session = AsyncMock()
    org = uuid4()
    row = _hold_row(org=org, cleared=True)
    session.execute = AsyncMock(return_value=_mappings_first(row))
    session.commit = AsyncMock()
    out = await hold_svc.clear_hold(session, org, row["id"], cleared_by=uuid4())
    assert out.cleared_at is not None
    session.commit.assert_awaited()


def test_constraint_name_from_diag() -> None:
    class _Diag:
        constraint_name = "legal_holds_one_active_per_scope"

    class _Orig(Exception):
        diag = _Diag()

    exc = IntegrityError("stmt", {}, _Orig())
    assert hold_svc._is_scope_conflict(exc)


def test_constraint_name_fallback_str() -> None:
    exc = IntegrityError("stmt", {}, Exception("legal_holds_one_active_per_scope boom"))
    assert hold_svc._is_scope_conflict(exc)


@pytest.mark.asyncio
async def test_resolve_mode_default() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    mode = await capture_svc.resolve_mode(session, uuid4())
    assert mode == "metadata_only"


@pytest.mark.asyncio
async def test_resolve_mode_with_agent() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=("full",))))
    mode = await capture_svc.resolve_mode(session, uuid4(), agent_id=uuid4())
    assert mode == "full"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "mode", "priority"),
    [
        ("list", "redacted", 1),
        ("create", "redacted", 10),
    ],
)
async def test_policy_list_and_create(kind: str, mode: str, priority: int) -> None:
    session = AsyncMock()
    org = uuid4()
    row = _policy_row(org=org, mode=mode, priority=priority)
    if kind == "list":
        session.execute = AsyncMock(return_value=_mappings_all([row]))
        out = await capture_svc.list_policies(session, org)
        assert len(out) == 1
        assert out[0].mode == mode
        return
    session.execute = AsyncMock(return_value=_mappings_first(row))
    session.commit = AsyncMock()
    created = await capture_svc.create_policy(
        session, org, CapturePolicyCreate(mode=mode, priority=priority)
    )
    assert created.id == row["id"]
    assert created.mode == mode


@pytest.mark.asyncio
async def test_delete_policy_happy() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(uuid4(),))))
    session.commit = AsyncMock()
    await capture_svc.delete_policy(session, uuid4(), uuid4())
    session.commit.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execute_side",),
    [
        (Exception("org_capture_policies_org_agent_unique violated"),),
        ("no_row",),
    ],
)
async def test_create_policy_conflict_paths(execute_side: object) -> None:
    session = AsyncMock()
    org = uuid4()
    body = CapturePolicyCreate(mode="none", priority=1)
    if execute_side == "no_row":
        session.execute = AsyncMock(return_value=_mappings_first(None))
    else:
        session.execute = AsyncMock(side_effect=execute_side)
    with pytest.raises(ApiError) as ei:
        await capture_svc.create_policy(session, org, body)
    assert ei.value.code == CAPTURE_POLICY_CONFLICT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("updated_mode", "expect_ok"),
    [
        ("full", True),
        (None, False),
    ],
)
async def test_patch_policy_paths(updated_mode: str | None, expect_ok: bool) -> None:
    session = AsyncMock()
    org = uuid4()
    pid = uuid4()
    current = _policy_row(org=org, pid=pid, mode="none", priority=1)
    updated = None if updated_mode is None else {**current, "mode": updated_mode, "priority": 2}
    session.execute = AsyncMock(
        side_effect=[_mappings_first(current), _mappings_first(updated)]
    )
    body = CapturePolicyPatch(mode="full", priority=2) if expect_ok else CapturePolicyPatch(mode="full")
    if expect_ok:
        session.commit = AsyncMock()
        out = await capture_svc.patch_policy(session, org, pid, body)
        assert out.mode == "full"
        assert out.priority == 2
        return
    with pytest.raises(ApiError) as ei:
        await capture_svc.patch_policy(session, org, pid, body)
    assert ei.value.code == NOT_FOUND
