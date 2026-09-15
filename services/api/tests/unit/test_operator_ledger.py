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
