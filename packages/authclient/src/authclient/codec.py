"""Bounded protobuf wire codec for AuthService.ValidateToken / ValidateAgent / tokens."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

MAX_MESSAGE_BYTES = 4096
MAX_LIST_MESSAGE_BYTES = 512 * 1024
MAX_STRING_BYTES = 512
MAX_TOKEN_BYTES = 8192
MAX_SUBMESSAGE_BYTES = 4096

TOKEN_TYPE_PAT = 1

_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_32BIT = 5


class AuthCodecError(Exception):
    """Auth wire encode/decode failure."""


@dataclass(frozen=True, slots=True)
class ValidateTokenWire:
    org_id: UUID
    permissions: int
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidateAgentWire:
    agent_id: UUID
    org_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class CreateTokenEncodeFields:
    """CreateTokenRequest wire fields (single-arg encode keeps CodeScene arity low)."""

    org_id: str
    name: str
    permissions: int
    description: str = ""
    token_type: int = TOKEN_TYPE_PAT
    expires_at: datetime | None = None
    user_id: str | None = None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateTokenWire:
    token_id: str
    plaintext: str
    prefix: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TokenMetadataWire:
    token_id: str
    name: str
    prefix: str
    permissions: int
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    is_revoked: bool = False


@dataclass(frozen=True, slots=True)
class ListTokensWire:
    tokens: list[TokenMetadataWire]
    next_cursor: str = ""


@dataclass(slots=True)
class _TokenDecodeState:
    org_id: UUID | None = None
    permissions: int = 0
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None


@dataclass(slots=True)
class _AgentDecodeState:
    agent_id: UUID | None = None
    org_id: UUID | None = None
    status: str | None = None


@dataclass(slots=True)
class _CreateDecodeState:
    token_id: str | None = None
    plaintext: str | None = None
    prefix: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class _MetaDecodeState:
    token_id: str | None = None
    name: str | None = None
    prefix: str | None = None
    permissions: int = 0
    expires_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None
    is_revoked: bool = False


@dataclass(slots=True)
class _ListDecodeState:
    tokens: list[TokenMetadataWire] = field(default_factory=list)
    next_cursor: str = ""


def encode_validate_token_request(access_token: str) -> bytes:
    data = access_token.encode("utf-8")
    if len(data) > MAX_TOKEN_BYTES:
        raise AuthCodecError("access token exceeds codec limit")
    return _tag(1, _WIRE_LEN) + encode_varint(len(data)) + data


def decode_validate_token_response(payload: bytes) -> ValidateTokenWire:
    state = _TokenDecodeState()
    _walk_fields(payload, lambda buf, idx: _decode_token_field(buf, idx, state))
    if state.org_id is None:
        raise AuthCodecError("auth response missing org_id")
    return ValidateTokenWire(
        org_id=state.org_id,
        permissions=state.permissions,
        agent_id=state.agent_id,
        user_id=state.user_id,
        token_id=state.token_id,
    )


def encode_validate_agent_request(*, agent_id: str, org_id: str) -> bytes:
    """Encode ValidateAgentRequest (agent_id=1, org_id=2)."""
    return _encode_string_field(1, agent_id) + _encode_string_field(2, org_id)


def encode_revoke_token_request(*, org_id: str, token_id: str, reason: str | None = None) -> bytes:
    """Encode RevokeTokenRequest (org_id=1, token_id=2, optional revoke_reason=3)."""
    out = _encode_string_field(1, org_id) + _encode_string_field(2, token_id)
    if reason:
        out += _encode_string_field(3, reason)
    return out


def encode_create_token_request(fields: CreateTokenEncodeFields) -> bytes:
    """Encode CreateTokenRequest (org_id=1 … agent_id=8)."""
    out = (
        _encode_string_field(1, fields.org_id)
        + _encode_string_field(2, fields.name)
        + _encode_string_field(3, fields.description)
        + _encode_varint_field(4, fields.token_type)
        + _encode_varint_field(5, fields.permissions)
    )
    if fields.expires_at is not None:
        out += _encode_message_field(6, _encode_timestamp(fields.expires_at))
    if fields.user_id:
        out += _encode_string_field(7, fields.user_id)
    if fields.agent_id:
        out += _encode_string_field(8, fields.agent_id)
    return out


def decode_create_token_response(payload: bytes) -> CreateTokenWire:
    """Decode CreateTokenResponse (token_id=1, plaintext=2, prefix=3, created_at=4)."""
    state = _CreateDecodeState()
    _walk_fields(
        payload,
        lambda buf, idx: _decode_create_field(buf, idx, state),
        max_bytes=MAX_MESSAGE_BYTES,
    )
    return _finish_create_wire(state)


def _finish_create_wire(state: _CreateDecodeState) -> CreateTokenWire:
    ctx = "create token response"
    return CreateTokenWire(
        token_id=_require_present(state.token_id, ctx, "token_id"),
        plaintext=_require_present(state.plaintext, ctx, "plaintext"),
        prefix=_require_present(state.prefix, ctx, "prefix"),
        created_at=_require_present(state.created_at, ctx, "created_at"),
    )


def encode_list_tokens_request(*, org_id: str, cursor: str = "", limit: int = 0) -> bytes:
    """Encode ListTokensRequest (org_id=1, cursor=2, limit=3)."""
    out = _encode_string_field(1, org_id)
    if cursor:
        out += _encode_string_field(2, cursor)
    if limit:
        out += _encode_varint_field(3, limit)
    return out


def decode_list_tokens_response(payload: bytes) -> ListTokensWire:
    """Decode ListTokensResponse (tokens=1 repeated, next_cursor=2)."""
    state = _ListDecodeState()
    _walk_fields(
        payload,
        lambda buf, idx: _decode_list_field(buf, idx, state),
        max_bytes=MAX_LIST_MESSAGE_BYTES,
    )
    return ListTokensWire(tokens=state.tokens, next_cursor=state.next_cursor)


def decode_validate_agent_response(payload: bytes) -> ValidateAgentWire:
    """Decode ValidateAgentResponse (agent_id=1, org_id=2, status=3)."""
    state = _AgentDecodeState()
    _walk_fields(payload, lambda buf, idx: _decode_agent_field(buf, idx, state))
    return _finish_agent_wire(state)


def _walk_fields(
    payload: bytes,
    decode_one: Callable[[bytes, int], int],
    *,
    max_bytes: int = MAX_MESSAGE_BYTES,
) -> None:
    if len(payload) > max_bytes:
        raise AuthCodecError("auth response too large")
    idx = 0
    while idx < len(payload):
        idx = decode_one(payload, idx)


def _finish_agent_wire(state: _AgentDecodeState) -> ValidateAgentWire:
    if state.agent_id is None:
        raise AuthCodecError("auth response missing agent_id")
    if state.org_id is None:
        raise AuthCodecError("auth response missing org_id")
    if not state.status:
        raise AuthCodecError("auth response missing status")
    return ValidateAgentWire(
        agent_id=state.agent_id,
        org_id=state.org_id,
        status=_bounded_string(state.status, "status"),
    )


def _encode_string_field(field: int, value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > MAX_STRING_BYTES:
        raise AuthCodecError("string field exceeds codec limit")
    return _tag(field, _WIRE_LEN) + encode_varint(len(data)) + data


def _encode_varint_field(field: int, value: int) -> bytes:
    return _tag(field, _WIRE_VARINT) + encode_varint(value)


def _encode_message_field(field: int, raw: bytes) -> bytes:
    if len(raw) > MAX_SUBMESSAGE_BYTES:
        raise AuthCodecError("submessage exceeds codec limit")
    return _tag(field, _WIRE_LEN) + encode_varint(len(raw)) + raw


def _encode_timestamp(value: datetime) -> bytes:
    dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    seconds = int(dt.timestamp())
    nanos = dt.microsecond * 1000
    out = _encode_varint_field(1, seconds)
    if nanos:
        out += _encode_varint_field(2, nanos)
    return out


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise AuthCodecError("negative varint")
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        out.append(bits | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _decode_token_field(buf: bytes, idx: int, state: _TokenDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx)
        _apply_token_len(state, field, raw)
        return idx
    if wire == _WIRE_VARINT:
        return _apply_token_varint(buf, idx, state, field)
    return _skip_unknown(buf, idx, wire)


def _apply_token_len(state: _TokenDecodeState, field: int, raw: bytes) -> None:
    if field == 1:
        state.org_id = _parse_uuid(_decode_utf8(raw), "org_id")
        return
    if field == 3:
        state.agent_id = _parse_uuid(_decode_utf8(raw), "agent_id")
        return
    if field == 4:
        state.user_id = _bounded_string(_decode_utf8(raw), "user_id")
        return
    if field == 5:
        state.token_id = _bounded_string(_decode_utf8(raw), "token_id")


def _apply_token_varint(
    buf: bytes, idx: int, state: _TokenDecodeState, field: int
) -> int:
    num, idx = _decode_varint(buf, idx)
    if field == 2:
        state.permissions = int(num)
    return idx


def _decode_agent_field(buf: bytes, idx: int, state: _AgentDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx)
        _apply_agent_len(state, field, raw)
        return idx
    if wire == _WIRE_VARINT:
        _, idx = _decode_varint(buf, idx)
        return idx
    return _skip_unknown(buf, idx, wire)


def _apply_agent_len(state: _AgentDecodeState, field: int, raw: bytes) -> None:
    if field == 1:
        state.agent_id = _parse_uuid(_decode_utf8(raw), "agent_id")
        return
    if field == 2:
        state.org_id = _parse_uuid(_decode_utf8(raw), "org_id")
        return
    if field == 3:
        state.status = _bounded_string(_decode_utf8(raw), "status")


def _decode_create_field(buf: bytes, idx: int, state: _CreateDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx, max_len=MAX_TOKEN_BYTES)
        _apply_create_len(state, field, raw)
        return idx
    return _skip_unknown(buf, idx, wire)


def _apply_create_len(state: _CreateDecodeState, field: int, raw: bytes) -> None:
    if field == 1:
        state.token_id = _bounded_string(_decode_utf8(raw), "token_id")
        return
    if field == 2:
        state.plaintext = _decode_plaintext(raw)
        return
    if field == 3:
        state.prefix = _bounded_string(_decode_utf8(raw), "prefix")
        return
    if field == 4:
        state.created_at = _decode_timestamp(raw)


def _decode_plaintext(raw: bytes) -> str:
    text = _decode_utf8(raw)
    if len(text) > MAX_TOKEN_BYTES:
        raise AuthCodecError("plaintext exceeds limit")
    return text


def _decode_list_field(buf: bytes, idx: int, state: _ListDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx, max_len=MAX_SUBMESSAGE_BYTES)
        if field == 1:
            state.tokens.append(_decode_token_metadata(raw))
        elif field == 2:
            state.next_cursor = _bounded_string(_decode_utf8(raw), "next_cursor")
        return idx
    return _skip_unknown(buf, idx, wire)


def _decode_token_metadata(raw: bytes) -> TokenMetadataWire:
    state = _MetaDecodeState()
    _walk_fields(
        raw,
        lambda buf, idx: _decode_meta_field(buf, idx, state),
        max_bytes=MAX_SUBMESSAGE_BYTES,
    )
    return _finish_meta_wire(state)


def _decode_meta_field(buf: bytes, idx: int, state: _MetaDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        data, idx = _read_bytes(buf, idx, max_len=MAX_SUBMESSAGE_BYTES)
        _apply_meta_len(state, field, data)
        return idx
    if wire == _WIRE_VARINT:
        return _apply_meta_varint(buf, idx, state, field)
    return _skip_unknown(buf, idx, wire)


def _apply_meta_len(state: _MetaDecodeState, field: int, data: bytes) -> None:
    if field == 1:
        state.token_id = _bounded_string(_decode_utf8(data), "token_id")
        return
    if field == 2:
        state.name = _bounded_string(_decode_utf8(data), "name")
        return
    if field == 3:
        state.prefix = _bounded_string(_decode_utf8(data), "prefix")
        return
    if field == 5:
        state.expires_at = _decode_timestamp(data)
        return
    if field == 6:
        state.created_at = _decode_timestamp(data)
        return
    if field == 7:
        state.revoked_at = _decode_timestamp(data)


def _apply_meta_varint(
    buf: bytes, idx: int, state: _MetaDecodeState, field: int
) -> int:
    num, idx = _decode_varint(buf, idx)
    if field == 4:
        state.permissions = int(num)
    elif field == 8:
        state.is_revoked = bool(num)
    return idx


def _finish_meta_wire(state: _MetaDecodeState) -> TokenMetadataWire:
    ctx = "token metadata"
    return TokenMetadataWire(
        token_id=_require_present(state.token_id, ctx, "token_id"),
        name=_require_present(state.name, ctx, "name"),
        prefix=_require_present(state.prefix, ctx, "prefix"),
        permissions=state.permissions,
        created_at=_require_present(state.created_at, ctx, "created_at"),
        expires_at=state.expires_at,
        revoked_at=state.revoked_at,
        is_revoked=state.is_revoked,
    )


def _require_present[T](value: T | None, context: str, field: str) -> T:
    if value is None:
        raise AuthCodecError(f"{context} missing {field}")
    return value


def _decode_timestamp(raw: bytes) -> datetime:
    seconds = 0
    nanos = 0
    idx = 0
    while idx < len(raw):
        key, idx = _decode_varint(raw, idx)
        field, wire = key >> 3, key & 0x07
        if wire != _WIRE_VARINT:
            idx = _skip_unknown(raw, idx, wire)
            continue
        num, idx = _decode_varint(raw, idx)
        if field == 1:
            seconds = int(num)
        elif field == 2:
            nanos = int(num)
    if nanos < 0 or nanos > 999_999_999:
        raise AuthCodecError("timestamp nanos out of range")
    try:
        return datetime.fromtimestamp(seconds + nanos / 1_000_000_000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise AuthCodecError("invalid timestamp") from exc


def _tag(field: int, wire: int) -> bytes:
    return encode_varint((field << 3) | wire)


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
            raise AuthCodecError("invalid varint")
    raise AuthCodecError("truncated varint")


def _read_bytes(buf: bytes, idx: int, *, max_len: int = MAX_STRING_BYTES) -> tuple[bytes, int]:
    length, idx = _decode_varint(buf, idx)
    if length > max_len:
        raise AuthCodecError("length-delimited field exceeds limit")
    end = idx + length
    if end > len(buf):
        raise AuthCodecError("truncated length-delimited field")
    return buf[idx:end], end


def _skip_unknown(buf: bytes, idx: int, wire: int) -> int:
    if wire == _WIRE_VARINT:
        return _skip_varint(buf, idx)
    if wire == _WIRE_64BIT:
        return _skip_fixed(buf, idx, 8, "fixed64")
    if wire == _WIRE_32BIT:
        return _skip_fixed(buf, idx, 4, "fixed32")
    if wire == _WIRE_LEN:
        _, idx = _read_bytes(buf, idx, max_len=MAX_SUBMESSAGE_BYTES)
        return idx
    raise AuthCodecError(f"unsupported wire type {wire}")


def _skip_varint(buf: bytes, idx: int) -> int:
    _, idx = _decode_varint(buf, idx)
    return idx


def _skip_fixed(buf: bytes, idx: int, size: int, label: str) -> int:
    end = idx + size
    if end > len(buf):
        raise AuthCodecError(f"truncated {label} field")
    return end


def _decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthCodecError("auth response is not utf-8") from exc


def _parse_uuid(text: str, label: str) -> UUID:
    try:
        return UUID(text)
    except ValueError as exc:
        raise AuthCodecError(f"invalid {label}") from exc


def _bounded_string(text: str, label: str) -> str:
    if len(text) > MAX_STRING_BYTES:
        raise AuthCodecError(f"{label} exceeds limit")
    return text
