"""Unit tests for auth protobuf wire codec."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.auth.errors import AuthUnavailableError
from app.auth.proto_wire import (
    ValidateTokenWire,
    _encode_varint,
    decode_validate_token_response,
    encode_validate_token_request,
)


def _encode_response(wire: ValidateTokenWire) -> bytes:
    parts: list[bytes] = []
    parts.append(bytes([0x0A]) + _encode_varint(len(str(wire.org_id))) + str(wire.org_id).encode())
    parts.append(bytes([0x10]) + _encode_varint(wire.permissions))
    if wire.agent_id is not None:
        aid = str(wire.agent_id).encode()
        parts.append(bytes([0x1A]) + _encode_varint(len(aid)) + aid)
    if wire.user_id is not None:
        uid = wire.user_id.encode()
        parts.append(bytes([0x22]) + _encode_varint(len(uid)) + uid)
    if wire.token_id is not None:
        tid = wire.token_id.encode()
        parts.append(bytes([0x2A]) + _encode_varint(len(tid)) + tid)
    return b"".join(parts)


def test_encode_validate_token_request_roundtrip() -> None:
    token = "test-access-token"
    payload = encode_validate_token_request(token)
    assert payload.startswith(b"\x0a")
    assert token.encode() in payload


def test_encode_rejects_oversized_token() -> None:
    with pytest.raises(AuthUnavailableError, match="codec limit"):
        encode_validate_token_request("x" * 9000)


def test_decode_validate_token_response_full() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    wire = ValidateTokenWire(
        org_id=org_id,
        permissions=42,
        agent_id=agent_id,
        user_id="user-1",
        token_id="tok-1",
    )
    decoded = decode_validate_token_response(_encode_response(wire))
    assert decoded.org_id == org_id
    assert decoded.permissions == 42
    assert decoded.agent_id == agent_id
    assert decoded.user_id == "user-1"
    assert decoded.token_id == "tok-1"


def test_decode_missing_org_id() -> None:
    # permissions only (field 2)
    payload = bytes([0x10, 0x05])
    with pytest.raises(AuthUnavailableError, match="missing org_id"):
        decode_validate_token_response(payload)


def test_decode_oversized_message() -> None:
    with pytest.raises(AuthUnavailableError, match="too large"):
        decode_validate_token_response(b"\x00" * 5000)


def test_decode_invalid_uuid() -> None:
    bad = bytes([0x0A, 0x04]) + b"oops"
    with pytest.raises(AuthUnavailableError, match="invalid org_id"):
        decode_validate_token_response(bad)


def test_decode_truncated_varint() -> None:
    with pytest.raises(AuthUnavailableError, match="truncated varint"):
        decode_validate_token_response(bytes([0x80]))


def test_decode_invalid_varint() -> None:
    with pytest.raises(AuthUnavailableError, match="invalid varint"):
        decode_validate_token_response(bytes([0x80] * 12))


def test_decode_skips_unknown_wire_types() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    # org_id field + fixed64 unknown field (wire type 1)
    payload = (
        bytes([0x0A]) + _encode_varint(len(org_bytes)) + org_bytes + bytes([0x09]) + b"\x00" * 8
    )
    decoded = decode_validate_token_response(payload)
    assert decoded.org_id == org_id


def test_decode_truncated_length_delimited() -> None:
    with pytest.raises(AuthUnavailableError, match="truncated length-delimited"):
        decode_validate_token_response(bytes([0x0A, 0x10]) + b"short")


def test_decode_string_exceeds_limit() -> None:
    org_id = uuid4()
    org_bytes = str(org_id).encode()
    huge = b"x" * 600
    payload = bytes([0x22]) + _encode_varint(len(huge)) + huge
    payload = bytes([0x0A]) + _encode_varint(len(org_bytes)) + org_bytes + payload
    with pytest.raises(AuthUnavailableError, match="exceeds limit"):
        decode_validate_token_response(payload)


def test_encode_varint_negative() -> None:
    with pytest.raises(AuthUnavailableError, match="negative varint"):
        _encode_varint(-1)


def test_decode_invalid_utf8() -> None:
    org_bytes = b"\xff\xfe"
    payload = bytes([0x0A]) + _encode_varint(len(org_bytes)) + org_bytes
    with pytest.raises(AuthUnavailableError, match="not utf-8"):
        decode_validate_token_response(payload)


def test_decode_fixed32_skip() -> None:
    org_id = UUID("00000000-0000-4000-8000-000000000001")
    org_bytes = str(org_id).encode()
    payload = bytes([0x0A]) + _encode_varint(len(org_bytes)) + org_bytes + bytes([0x2D]) + b"\x00" * 4
    decoded = decode_validate_token_response(payload)
    assert decoded.org_id == org_id
