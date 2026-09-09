"""gRPC wire codec unit tests for ValidateToken / ValidateAgent (no network)."""

from __future__ import annotations

from uuid import UUID

import pytest
from authclient import (
    AuthCodecError,
    decode_validate_agent_response,
    decode_validate_token_response,
    encode_validate_agent_request,
    encode_validate_token_request,
)


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
    with pytest.raises(AuthCodecError):
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
    with pytest.raises(AuthCodecError):
        decode_validate_token_response(b"\x00" * 5000)


def test_decode_rejects_truncated_len_field() -> None:
    with pytest.raises(AuthCodecError):
        decode_validate_token_response(b"\x0a\x05ab")


def test_validate_agent_request_roundtrip_bytes() -> None:
    agent = "33333333-3333-3333-3333-333333333333"
    org = "11111111-1111-1111-1111-111111111111"
    raw = encode_validate_agent_request(agent_id=agent, org_id=org)
    assert agent.encode() in raw
    assert org.encode() in raw


def test_validate_agent_response_roundtrip() -> None:
    agent = "33333333-3333-3333-3333-333333333333"
    org = "11111111-1111-1111-1111-111111111111"
    status = "active"
    payload = encode_validate_agent_request(agent_id=agent, org_id=org)
    # Append status as field 3 (request encoder only does 1+2).
    status_b = status.encode()
    payload += b"\x1a" + bytes([len(status_b)]) + status_b
    got = decode_validate_agent_response(payload)
    assert got.agent_id == UUID(agent)
    assert got.org_id == UUID(org)
    assert got.status == "active"


def test_validate_agent_response_missing_status() -> None:
    agent = "33333333-3333-3333-3333-333333333333"
    org = "11111111-1111-1111-1111-111111111111"
    payload = encode_validate_agent_request(agent_id=agent, org_id=org)
    with pytest.raises(AuthCodecError, match="status"):
        decode_validate_agent_response(payload)