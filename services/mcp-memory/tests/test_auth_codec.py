"""gRPC wire codec unit tests for ValidateToken (no network)."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.errors import AuthUnavailableError
from app.proto_wire import decode_validate_token_response, encode_validate_token_request


def test_encode_decode_roundtrip_shape() -> None:
    org = "11111111-1111-1111-1111-111111111111"
    org_b = org.encode()
    payload = b"\x0a" + bytes([len(org_b)]) + org_b
    payload += b"\x10\x03"
    got = decode_validate_token_response(payload)
    assert got.org_id == UUID(org)
    assert got.permissions == 3


def test_encode_request_contains_token_bytes() -> None:
    raw = encode_validate_token_request("abc")
    assert b"abc" in raw


def test_decode_missing_org_fails() -> None:
    with pytest.raises(AuthUnavailableError):
        decode_validate_token_response(b"\x10\x01")


def test_decode_skips_unknown_len_binary_without_utf8() -> None:
    org = "11111111-1111-1111-1111-111111111111"
    org_b = org.encode()
    # field 9 (unknown) length-delimited with non-UTF8 bytes, then org_id.
    junk = b"\xff\xfe\x00\x01"
    payload = b"\x4a" + bytes([len(junk)]) + junk
    payload += b"\x0a" + bytes([len(org_b)]) + org_b
    got = decode_validate_token_response(payload)
    assert got.org_id == UUID(org)


def test_decode_rejects_oversized_message() -> None:
    with pytest.raises(AuthUnavailableError):
        decode_validate_token_response(b"\x00" * 5000)


def test_decode_rejects_truncated_len_field() -> None:
    with pytest.raises(AuthUnavailableError):
        decode_validate_token_response(b"\x0a\x05ab")
