"""Protobuf wire helpers for IssueOperatorSession refresh responses."""

from __future__ import annotations

from collections.abc import Callable

from authclient.codec import AuthCodecError, encode_varint

_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_32BIT = 5
_MAX_TOKEN_FIELD = 8192
_MAX_MESSAGE = 16_384
_FIXED_WIRE_BYTES = {_WIRE_64BIT: 8, _WIRE_32BIT: 4}


def encode_issue_with_refresh(refresh_token: str) -> bytes:
    """Encode IssueOperatorSessionRequest{refresh_token=...} (field 1, string)."""
    raw = refresh_token.encode("utf-8")
    return encode_varint((1 << 3) | _WIRE_LEN) + encode_varint(len(raw)) + raw


def encode_string_fields(fields: dict[int, str]) -> bytes:
    out = bytearray()
    for field_num, value in fields.items():
        if not value:
            continue
        raw = value.encode("utf-8")
        if len(raw) > _MAX_TOKEN_FIELD:
            raise AuthCodecError("string field exceeds limit")
        out.extend(encode_varint((field_num << 3) | _WIRE_LEN))
        out.extend(encode_varint(len(raw)))
        out.extend(raw)
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
            raise AuthCodecError("invalid varint")
    raise AuthCodecError("truncated varint")


def _read_bytes(buf: bytes, idx: int, *, max_len: int) -> tuple[bytes, int]:
    length, idx = _decode_varint(buf, idx)
    if length > max_len:
        raise AuthCodecError("length-delimited field exceeds limit")
    end = idx + length
    if end > len(buf):
        raise AuthCodecError("truncated length-delimited field")
    return buf[idx:end], end


def _skip_fixed(buf: bytes, idx: int, size: int) -> int:
    end = idx + size
    if end > len(buf):
        raise AuthCodecError("truncated fixed field")
    return end


def _skip_unknown(buf: bytes, idx: int, wire: int) -> int:
    if wire == _WIRE_VARINT:
        _, idx = _decode_varint(buf, idx)
        return idx
    if wire == _WIRE_LEN:
        _, idx = _read_bytes(buf, idx, max_len=_MAX_MESSAGE)
        return idx
    size = _FIXED_WIRE_BYTES.get(wire)
    if size is None:
        raise AuthCodecError(f"unsupported wire type {wire}")
    return _skip_fixed(buf, idx, size)


def _utf8_string(val: bytes) -> str:
    try:
        return val.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthCodecError("invalid utf-8 string field") from exc


def _ensure_message_size(buf: bytes, *, too_large: str) -> None:
    if len(buf) > _MAX_MESSAGE:
        raise AuthCodecError(too_large)


def _walk_fields(
    buf: bytes,
    *,
    too_large: str,
    visit: Callable[[int, int, int], int | None],
) -> None:
    """Invoke visit(fn, wire, idx)->next_idx; stop early when visit returns None."""
    _ensure_message_size(buf, too_large=too_large)
    idx = 0
    while idx < len(buf):
        key, idx = _decode_varint(buf, idx)
        nxt = visit(key >> 3, key & 7, idx)
        if nxt is None:
            return
        idx = nxt


def decode_string_field(buf: bytes, field_num: int) -> str | None:
    """Bounded protobuf string scan; raises AuthCodecError on malformed input."""
    found: list[str] = []

    def visit(fn: int, wt: int, idx: int) -> int | None:
        if wt != _WIRE_LEN:
            return _skip_unknown(buf, idx, wt)
        val, idx = _read_bytes(buf, idx, max_len=_MAX_TOKEN_FIELD)
        if fn == field_num:
            found.append(_utf8_string(val))
            return None
        return idx

    _walk_fields(buf, too_large="auth refresh response too large", visit=visit)
    return found[0] if found else None


def decode_string_fields(buf: bytes, field_nums: set[int]) -> dict[int, str]:
    values: dict[int, str] = {}

    def visit(fn: int, wt: int, idx: int) -> int | None:
        if wt == _WIRE_LEN:
            val, idx = _read_bytes(buf, idx, max_len=_MAX_TOKEN_FIELD)
            if fn in field_nums:
                values[fn] = _utf8_string(val)
            return idx
        return _skip_unknown(buf, idx, wt)

    _walk_fields(buf, too_large="auth lifecycle response too large", visit=visit)
    return values


def decode_int64_field(buf: bytes, field_num: int) -> int | None:
    found: list[int] = []

    def visit(fn: int, wt: int, idx: int) -> int | None:
        if wt == _WIRE_VARINT:
            val, idx = _decode_varint(buf, idx)
            if fn == field_num:
                found.append(val)
                return None
            return idx
        return _skip_unknown(buf, idx, wt)

    _walk_fields(buf, too_large="auth lifecycle response too large", visit=visit)
    return found[0] if found else None
