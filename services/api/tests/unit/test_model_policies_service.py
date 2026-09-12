"""Service-layer tests for org model-policy persistence (m4.C.2).

One behavior per test; failure paths are explicit (not bundled with happy path).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import (
    INTERNAL_ERROR,
    MODEL_POLICY_PATTERN_CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
)
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.model_policy_publish import RecordingModelPolicyPublisher
from app.pagination import encode_cursor
from app.schemas.model_policies import ModelPolicyCreate, ModelPolicyPatch
from app.services import model_policies as svc

_ORG_PATTERN_UNIQUE = "org_model_policies_org_pattern_unique"


class _UnsetType:
    pass


_UNSET = _UnsetType()


def _policy_row(**overrides) -> SimpleNamespace:
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "org_id": uuid4(),
        "model_pattern": "claude-*",
        "allowed": True,
        "priority": 100,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _Rows:
    """Minimal SQLAlchemy Result stand-in."""

    def __init__(self, *, rows: list | None = None, row: object = _UNSET) -> None:
        self._rows = list(rows or [])
        self._use_row = row is not _UNSET
        self._row = None if row is _UNSET else row

    def all(self):
        return self._rows

    def first(self):
        if self._use_row:
            return self._row
        return self._rows[0] if self._rows else None


def _integrity(constraint: str) -> IntegrityError:
    return IntegrityError(
        "INSERT", {}, SimpleNamespace(constraint_name=constraint, diag=None)
    )


async def _expect_api_error(coro, code: str) -> None:
    with pytest.raises(ApiError) as caught:
        await coro
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_list_rejects_malformed_cursor() -> None:
    await _expect_api_error(
        svc.list_policies(AsyncMock(), uuid4(), cursor="!!!", limit=10),
        VALIDATION_ERROR,
    )


@pytest.mark.asyncio
async def test_list_returns_empty_page() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(rows=[]))
    page = await svc.list_policies(session, uuid4(), cursor=None, limit=10)
    assert page.data == []
    assert page.pagination.has_more is False


@pytest.mark.asyncio
async def test_list_encodes_next_cursor_when_page_full() -> None:
    org_id = uuid4()
    rows = [
        _policy_row(org_id=org_id, priority=1, model_pattern="a*"),
        _policy_row(org_id=org_id, priority=2, model_pattern="b*"),
        _policy_row(org_id=org_id, priority=3, model_pattern="c*"),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(rows=rows))
    page = await svc.list_policies(session, org_id, cursor=None, limit=2)
    assert [p.model_pattern for p in page.data] == ["a*", "b*"]
    assert page.pagination.has_more is True
    assert page.pagination.next_cursor


@pytest.mark.asyncio
async def test_list_applies_decoded_cursor_to_query() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(rows=[]))
    cursor = encode_cursor({"priority": 7, "pattern": "gpt-*"})
    await svc.list_policies(session, uuid4(), cursor=cursor, limit=5)
    params = session.execute.await_args.args[1]
    assert params["cursor_priority"] == 7
    assert params["cursor_pattern"] == "gpt-*"


@pytest.mark.asyncio
async def test_get_returns_policy() -> None:
    org_id, policy_id = uuid4(), uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=_Rows(row=_policy_row(id=policy_id, org_id=org_id))
    )
    got = await svc.get_policy(session, org_id, policy_id)
    assert got.id == policy_id
    assert got.org_id == org_id


@pytest.mark.asyncio
async def test_get_missing_policy_is_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(row=None))
    await _expect_api_error(svc.get_policy(session, uuid4(), uuid4()), NOT_FOUND)


@pytest.mark.asyncio
async def test_create_persists_and_publishes() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=_Rows(row=_policy_row(org_id=org_id, model_pattern="gpt-*"))
    )
    session.commit = AsyncMock()
    publisher = RecordingModelPolicyPublisher()
    body = ModelPolicyCreate(model_pattern="gpt-*", allowed=True, priority=5)
    got = await svc.create_policy(
        session, org_id, body, deps=svc.WriteDeps(publisher=publisher)
    )
    assert got.model_pattern == "gpt-*"
    assert publisher.published == [str(org_id)]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_duplicate_pattern_is_conflict() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_integrity(_ORG_PATTERN_UNIQUE))
    session.rollback = AsyncMock()
    body = ModelPolicyCreate(model_pattern="gpt-*", allowed=False)
    await _expect_api_error(
        svc.create_policy(session, uuid4(), body, deps=svc.WriteDeps()),
        MODEL_POLICY_PATTERN_CONFLICT,
    )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_unknown_integrity_error_is_internal() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_integrity("some_other_constraint"))
    session.rollback = AsyncMock()
    body = ModelPolicyCreate(model_pattern="x*", allowed=True)
    await _expect_api_error(
        svc.create_policy(session, uuid4(), body, deps=svc.WriteDeps()),
        INTERNAL_ERROR,
    )


@pytest.mark.asyncio
async def test_create_missing_returning_row_is_internal() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(row=None))
    session.commit = AsyncMock()
    body = ModelPolicyCreate(model_pattern="x*", allowed=True)
    await _expect_api_error(
        svc.create_policy(session, uuid4(), body, deps=svc.WriteDeps()),
        INTERNAL_ERROR,
    )


@pytest.mark.asyncio
async def test_create_survives_publish_failure_after_commit() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(row=_policy_row(org_id=org_id)))
    session.commit = AsyncMock()

    class _FailingPublisher:
        async def publish_policy_update(self, _org_id: str) -> None:
            raise RuntimeError("redis unavailable")

    body = ModelPolicyCreate(model_pattern="claude-*", allowed=True)
    got = await svc.create_policy(
        session, org_id, body, deps=svc.WriteDeps(publisher=_FailingPublisher())
    )
    assert got.org_id == org_id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_applies_partial_fields_and_publishes() -> None:
    org_id, policy_id = uuid4(), uuid4()
    current = _policy_row(
        id=policy_id, org_id=org_id, model_pattern="old-*", allowed=True, priority=1
    )
    updated = _policy_row(
        id=policy_id, org_id=org_id, model_pattern="old-*", allowed=False, priority=1
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_Rows(row=current), _Rows(row=updated)]
    )
    session.commit = AsyncMock()
    publisher = RecordingModelPolicyPublisher()
    got = await svc.patch_policy(
        session,
        svc.PatchArgs(
            org_id=org_id,
            policy_id=policy_id,
            body=ModelPolicyPatch(allowed=False),
            deps=svc.WriteDeps(publisher=publisher),
        ),
    )
    assert got.allowed is False
    assert publisher.published == [str(org_id)]


@pytest.mark.asyncio
async def test_patch_duplicate_pattern_is_conflict() -> None:
    org_id, policy_id = uuid4(), uuid4()
    current = _policy_row(id=policy_id, org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_Rows(row=current), _integrity(_ORG_PATTERN_UNIQUE)]
    )
    session.rollback = AsyncMock()
    await _expect_api_error(
        svc.patch_policy(
            session,
            svc.PatchArgs(
                org_id=org_id,
                policy_id=policy_id,
                body=ModelPolicyPatch(model_pattern="dup-*"),
                deps=svc.WriteDeps(),
            ),
        ),
        MODEL_POLICY_PATTERN_CONFLICT,
    )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_race_deleted_row_is_not_found() -> None:
    org_id, policy_id = uuid4(), uuid4()
    current = _policy_row(id=policy_id, org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_Rows(row=current), _Rows(row=None)]
    )
    session.commit = AsyncMock()
    await _expect_api_error(
        svc.patch_policy(
            session,
            svc.PatchArgs(
                org_id=org_id,
                policy_id=policy_id,
                body=ModelPolicyPatch(priority=9),
                deps=svc.WriteDeps(),
            ),
        ),
        NOT_FOUND,
    )


@pytest.mark.asyncio
async def test_delete_publishes_after_commit() -> None:
    org_id, policy_id = uuid4(), uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(row=SimpleNamespace(id=policy_id)))
    session.commit = AsyncMock()
    publisher = RecordingModelPolicyPublisher()
    await svc.delete_policy(
        session, org_id, policy_id, deps=svc.WriteDeps(publisher=publisher)
    )
    assert publisher.published == [str(org_id)]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_missing_policy_is_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows(row=None))
    session.rollback = AsyncMock()
    await _expect_api_error(
        svc.delete_policy(session, uuid4(), uuid4(), deps=svc.WriteDeps()),
        NOT_FOUND,
    )
    session.rollback.assert_awaited_once()


def test_pattern_conflict_detected_from_diag_constraint_name() -> None:
    orig = SimpleNamespace(
        constraint_name=None,
        diag=SimpleNamespace(constraint_name=_ORG_PATTERN_UNIQUE),
    )
    assert svc._is_pattern_conflict(IntegrityError("x", {}, orig)) is True


def test_constraint_name_falls_back_to_orig_string() -> None:
    orig = SimpleNamespace(constraint_name=None, diag=None)
    name = svc._constraint_name(IntegrityError("x", {}, orig))
    assert name  # non-empty fallback


def test_constraint_name_ignores_empty_diag_name() -> None:
    orig = SimpleNamespace(
        constraint_name=None,
        diag=SimpleNamespace(constraint_name=""),
    )
    name = svc._constraint_name(IntegrityError("x", {}, orig))
    assert name
    assert svc._is_pattern_conflict(IntegrityError("x", {}, orig)) is False


def test_row_mapping_accepts_uuid_strings() -> None:
    org_id, policy_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    got = svc._row_to_response(
        SimpleNamespace(
            id=str(policy_id),
            org_id=str(org_id),
            model_pattern="x*",
            allowed=1,
            priority=3,
            created_at=now,
            updated_at=now,
        )
    )
    assert got.id == policy_id
    assert got.org_id == org_id
    assert got.allowed is True
