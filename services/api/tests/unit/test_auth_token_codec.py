"""Unit tests for authclient CreateToken / ListTokens codecs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from authclient.codec import (
    TOKEN_TYPE_PAT,
    decode_create_token_response,
    decode_list_tokens_response,
    encode_create_token_request,
    encode_list_tokens_request,
    encode_varint,
)


def _tag(field: int, wire: int) -> bytes:
    return encode_varint((field << 3) | wire)


def _string_field(field: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return _tag(field, 2) + encode_varint(len(data)) + data


def _varint_field(field: int, value: int) -> bytes:
    return _tag(field, 0) + encode_varint(value)


def _message_field(field: int, raw: bytes) -> bytes:
    return _tag(field, 2) + encode_varint(len(raw)) + raw


def _timestamp(value: datetime) -> bytes:
    seconds = int(value.timestamp())
    return _varint_field(1, seconds)


def test_encode_create_token_request_contains_fields() -> None:
    org = str(uuid4())
    agent = str(uuid4())
    expires = datetime(2030, 1, 1, tzinfo=UTC)
    raw = encode_create_token_request(
        org_id=org,
        name="ci",
        permissions=(1 << 0) | (1 << 36),
        description="d",
        token_type=TOKEN_TYPE_PAT,
        expires_at=expires,
        user_id="user-1",
        agent_id=agent,
    )
    assert org.encode() in raw
    assert b"ci" in raw
    assert agent.encode() in raw


def test_decode_create_token_response() -> None:
    created = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    payload = (
        _string_field(1, "tok-1")
        + _string_field(2, "ibex_pat_tok-1_secret")
        + _string_field(3, "ibex_pat_tok")
        + _message_field(4, _timestamp(created))
    )
    wire = decode_create_token_response(payload)
    assert wire.token_id == "tok-1"
    assert wire.plaintext.startswith("ibex_pat_")
    assert wire.prefix == "ibex_pat_tok"
    assert wire.created_at == created


def test_decode_list_tokens_response() -> None:
    created = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    meta = (
        _string_field(1, "tok-1")
        + _string_field(2, "name")
        + _string_field(3, "pfx")
        + _varint_field(4, 1)
        + _message_field(6, _timestamp(created))
        + _varint_field(8, 0)
    )
    payload = _message_field(1, meta) + _string_field(2, "cursor-next")
    wire = decode_list_tokens_response(payload)
    assert len(wire.tokens) == 1
    assert wire.tokens[0].token_id == "tok-1"
    assert wire.tokens[0].permissions == 1
    assert wire.next_cursor == "cursor-next"


def test_encode_list_tokens_request() -> None:
    org = str(uuid4())
    raw = encode_list_tokens_request(org_id=org, cursor="c1", limit=25)
    assert org.encode() in raw
    assert b"c1" in raw
    assert _tag(3, 0) + encode_varint(25) in raw
