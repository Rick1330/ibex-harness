"""Unit tests for operator ledger deny-without-preview hooks."""

from __future__ import annotations

from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS

from app.errors import ApiError
from app.services.operator_ledger import assert_dual_approval_satisfied, assert_preview_token


def test_assert_preview_token_denies_empty() -> None:
    with pytest.raises(ApiError) as exc:
        assert_preview_token("")
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_assert_preview_token_accepts_nonempty() -> None:
    assert assert_preview_token(" preview-1 ") == "preview-1"


def test_dual_approval_hook_denies_without_second_actor() -> None:
    actor = uuid4()
    with pytest.raises(ApiError) as exc:
        assert_dual_approval_satisfied(
            requires_second_actor=True,
            second_actor_user_id=None,
            actor_user_id=actor,
        )
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_dual_approval_hook_denies_same_actor() -> None:
    actor = uuid4()
    with pytest.raises(ApiError):
        assert_dual_approval_satisfied(
            requires_second_actor=True,
            second_actor_user_id=actor,
            actor_user_id=actor,
        )


def test_dual_approval_hook_ok_when_different_actor() -> None:
    assert_dual_approval_satisfied(
        requires_second_actor=True,
        second_actor_user_id=uuid4(),
        actor_user_id=uuid4(),
    )


def test_dual_approval_noop_when_not_required() -> None:
    assert_dual_approval_satisfied(
        requires_second_actor=False,
        second_actor_user_id=None,
        actor_user_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_record_ledger_row_inserts_via_repo() -> None:
    from unittest.mock import AsyncMock

    from app.services.operator_ledger import record_ledger_row

    session = AsyncMock()
    row_id = uuid4()

    async def fake_insert(session, **kwargs):
        assert kwargs["preview_token"] == "preview-1"
        assert kwargs["org_id"]
        return row_id

    got = await record_ledger_row(
        session,
        org_id=uuid4(),
        actor_user_id=uuid4(),
        action="export",
        preview_token=" preview-1 ",
        idempotency_key="idem-1",
        insert=fake_insert,
    )
    assert got == row_id
