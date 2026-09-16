"""Legal hold authz dependency unit tests."""

from __future__ import annotations

from uuid import uuid4

from authclient.permissions import LEGAL_HOLD_MANAGE, requires_step_up, bitmap_for_role


def test_legal_hold_bit_in_admin_role_bitmap() -> None:
    bmp = bitmap_for_role("admin")
    assert bmp & LEGAL_HOLD_MANAGE == LEGAL_HOLD_MANAGE
    assert bitmap_for_role("owner") & LEGAL_HOLD_MANAGE == LEGAL_HOLD_MANAGE
    assert bitmap_for_role("member") & LEGAL_HOLD_MANAGE == 0


def test_legal_hold_requires_step_up() -> None:
    assert requires_step_up(LEGAL_HOLD_MANAGE)
    assert LEGAL_HOLD_MANAGE == 1 << 49


def test_legal_hold_user_id_shape() -> None:
    # Ensure UUID round-trip used by routers
    uid = uuid4()
    assert str(uid)
