"""Unit tests for permission string ↔ bitmap codec."""

from __future__ import annotations

import pytest
from apierror_py import VALIDATION_ERROR

from app.errors import ApiError
from app.permissions_codec import (
    KNOWN_PERMISSION_STRINGS,
    bitmap_to_strings,
    strings_to_bitmap,
)


def test_every_catalog_string_round_trips() -> None:
    for name in sorted(KNOWN_PERMISSION_STRINGS):
        bitmap = strings_to_bitmap([name])
        assert bitmap_to_strings(bitmap) == [name]


def test_empty_list_is_zero() -> None:
    assert strings_to_bitmap([]) == 0
    assert bitmap_to_strings(0) == []


def test_multi_bit_or() -> None:
    bitmap = strings_to_bitmap(["memory:read", "session:create", "admin:token_create"])
    assert bitmap == (1 << 0) | (1 << 16) | (1 << 36)
    assert bitmap_to_strings(bitmap) == [
        "memory:read",
        "session:create",
        "admin:token_create",
    ]


def test_admin_org_manage_is_bit_35_not_9() -> None:
    bitmap = strings_to_bitmap(["admin:org_manage"])
    assert bitmap == 1 << 35
    assert bitmap != 1 << 9
    assert bitmap_to_strings(bitmap) == ["admin:org_manage"]


def test_unknown_string_rejected() -> None:
    with pytest.raises(ApiError) as exc:
        strings_to_bitmap(["agent:read"])
    assert exc.value.code == VALIDATION_ERROR
    assert exc.value.field_errors is not None
    assert exc.value.field_errors[0].field == "permissions"


def test_case_sensitive_rejection() -> None:
    with pytest.raises(ApiError) as exc:
        strings_to_bitmap(["Memory:Read"])
    assert exc.value.code == VALIDATION_ERROR


def test_unbacked_sketch_strings_rejected() -> None:
    for bad in ("agent:write", "admin:billing", "admin:audit_log"):
        with pytest.raises(ApiError) as exc:
            strings_to_bitmap([bad])
        assert exc.value.code == VALIDATION_ERROR
