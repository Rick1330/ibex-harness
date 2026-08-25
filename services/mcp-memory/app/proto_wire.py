"""Bounded protobuf3 wire helpers for AuthService.ValidateToken.

Generated stubs are not committed (ADR-0004). This codec is intentionally
minimal: only the scalar fields we need, with length caps and unknown-field
skipping so auth responses remain forward-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.errors import AuthUnavailableError

# Keep auth payloads small; AuthService never returns large ValidateToken bodies.
_MAX_MESSAGE_BYTES = 4096
_MAX_STRING_BYTES = 512
_MAX_TOKEN_BYTES = 8192

_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_32BIT = 5


@dataclass(frozen=True, slots=True)
class ValidateTokenWire:
    org_id: UUID
    permissions: int
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None


@dataclass(slots=True)
class _DecodeState:
    org_id: UUID | None = None
    permissions: int = 0
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None


def encode_validate_token_request(access_token: str) -> bytes:
    """Encode ValidateTokenRequest { access_token = 1 }."""
    data = access_token.encode("utf-8")
    if len(data) > _MAX_TOKEN_BYTES:
        raise AuthUnavailableError("access token exceeds codec limit")
    return _tag(1, _WIRE_LEN) + _encode_varint(len(data)) + data


def decode_validate_token_response(payload: bytes) -> ValidateTokenWire:
    """Decode ValidateTokenResponse fields 1–5 (org, permissions, agent, user, token)."""
    if len(payload) > _MAX_MESSAGE_BYTES:
        raise AuthUnavailableError("auth response too large")
    return _finish_decode(_decode_all_fields(payload))


def _decode_all_fields(payload: bytes) -> _DecodeState:
    state = _DecodeState()
    idx = 0
    while idx < len(payload):
        idx = _decode_one_field(payload, idx, state)
    return state


def _decode_one_field(buf: bytes, idx: int, state: _DecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field = key >> 3
    wire = key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx)
        _apply_len_field(state, field, raw)
        return idx
    if wire == _WIRE_VARINT:
        num, idx = _decode_varint(buf, idx)
        _apply_varint_field(state, field, num)
        return idx
    return _skip_unknown(buf, idx, wire)


def _finish_decode(state: _DecodeState) -> ValidateTokenWire:
    if state.org_id is None:
        raise AuthUnavailableError("auth response missing org_id")
    return ValidateTokenWire(
        org_id=state.org_id,
        permissions=state.permissions,
        agent_id=state.agent_id,
        user_id=state.user_id,
        token_id=state.token_id,
    )


def _apply_len_field(state: _DecodeState, field: int, raw: bytes) -> None:
    text = _decode_utf8(raw)
    if field == 1:
        state.org_id = _parse_uuid(text, "org_id")
    elif field == 3:
        state.agent_id = _parse_uuid(text, "agent_id")
    elif field == 4:
        state.user_id = _bounded_string(text, "user_id")
    elif field == 5:
        state.token_id = _bounded_string(text, "token_id")


def _apply_varint_field(state: _DecodeState, field: int, num: int) -> None:
    if field == 2:
        state.permissions = int(num)


def _tag(field: int, wire: int) -> bytes:
    return _encode_varint((field << 3) | wire)


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise AuthUnavailableError("negative varint")
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        out.append(bits | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _decode_varint(buf: bytes, idx: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while idx < len(buf):
        b = buf[idx]
        idx += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, idx
        shift += 7
        if shift > 63:
            raise AuthUnavailableError("invalid varint")
    raise AuthUnavailableError("truncated varint")


def _read_bytes(buf: bytes, idx: int) -> tuple[bytes, int]:
    length, idx = _decode_varint(buf, idx)
    if length > _MAX_STRING_BYTES:
        raise AuthUnavailableError("length-delimited field exceeds limit")
    end = idx + length
    if end > len(buf):
        raise AuthUnavailableError("truncated length-delimited field")
    return buf[idx:end], end


def _skip_unknown(buf: bytes, idx: int, wire: int) -> int:
    if wire == _WIRE_VARINT:
        return _skip_varint(buf, idx)
    if wire == _WIRE_64BIT:
        return _skip_fixed(buf, idx, 8, "fixed64")
    if wire == _WIRE_32BIT:
        return _skip_fixed(buf, idx, 4, "fixed32")
    if wire == _WIRE_LEN:
        _, idx = _read_bytes(buf, idx)
        return idx
    raise AuthUnavailableError(f"unsupported wire type {wire}")


def _skip_varint(buf: bytes, idx: int) -> int:
    _, idx = _decode_varint(buf, idx)
    return idx


def _skip_fixed(buf: bytes, idx: int, size: int, label: str) -> int:
    end = idx + size
    if end > len(buf):
        raise AuthUnavailableError(f"truncated {label} field")
    return end


def _decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthUnavailableError("auth response is not utf-8") from exc


def _parse_uuid(text: str, label: str) -> UUID:
    try:
        return UUID(text)
    except ValueError as exc:
        raise AuthUnavailableError(f"invalid {label}") from exc


def _bounded_string(text: str, label: str) -> str:
    if len(text) > _MAX_STRING_BYTES:
        raise AuthUnavailableError(f"{label} exceeds limit")
    return text
