"""Unit tests for request ID helpers."""

from __future__ import annotations

from uuid import UUID, uuid4

from uuid6 import uuid7

from app.reqid import new_id, resolve_inbound


def test_new_id_is_uuid_v7() -> None:
    value = new_id()
    parsed = UUID(value)
    # RFC 9562 version nibble is 7 for UUID v7.
    assert parsed.version == 7


def test_resolve_inbound_honors_valid_uuid() -> None:
    inbound = str(uuid4())
    assert resolve_inbound(inbound) == inbound
    inbound_v7 = str(uuid7())
    assert resolve_inbound(inbound_v7) == inbound_v7


def test_resolve_inbound_replaces_invalid() -> None:
    replaced = resolve_inbound("not-a-uuid")
    assert UUID(replaced).version == 7
    assert UUID(resolve_inbound("")).version == 7
    assert UUID(resolve_inbound(None)).version == 7
    assert UUID(resolve_inbound("   ")).version == 7
