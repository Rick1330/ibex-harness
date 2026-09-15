"""Auth-owned operator session refresh (RS256 IssueOperatorSession with refresh_token)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import grpc
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.target import assert_trusted_insecure_auth_target

logger = logging.getLogger(__name__)

_ISSUE_METHOD = "/ibex.auth.v1.AuthService/IssueOperatorSession"
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


def _decode_string_field(buf: bytes, field_num: int) -> str | None:
    """Bounded protobuf string scan; raises AuthCodecError on malformed input."""
    if len(buf) > _MAX_MESSAGE:
        raise AuthCodecError("auth refresh response too large")
    idx = 0
    while idx < len(buf):
        key, idx = _decode_varint(buf, idx)
        fn, wt = key >> 3, key & 7
        if wt == _WIRE_LEN:
            val, idx = _read_bytes(buf, idx, max_len=_MAX_TOKEN_FIELD)
            if fn == field_num:
                return val.decode("utf-8")
            continue
        idx = _skip_unknown(buf, idx, wt)
    return None


@dataclass(frozen=True, slots=True)
class RefreshedSession:
    access_token: str
    refresh_token: str


def _map_rpc_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
        return AuthUnavailableError("auth unavailable")
    if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
        return AuthFailedError("invalid refresh token")
    logger.warning("auth refresh rpc failed code=%s", exc.code())
    return AuthUnavailableError("auth refresh failed")


def _parse_refreshed_session(raw: bytes) -> RefreshedSession:
    try:
        access = _decode_string_field(raw, 1)
        refresh = _decode_string_field(raw, 2)
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth refresh codec error") from exc
    if not access or not refresh:
        raise AuthUnavailableError("auth refresh returned incomplete tokens")
    return RefreshedSession(access_token=access, refresh_token=refresh)


async def _call_issue_operator_session(
    *,
    auth_grpc_addr: str,
    refresh_token: str,
    timeout_seconds: float,
) -> bytes:
    payload = encode_issue_with_refresh(refresh_token)
    try:
        async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                _ISSUE_METHOD,
                request_serializer=lambda b: b,
                response_deserializer=lambda b: b,
            )
            return await asyncio.wait_for(stub(payload), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise AuthUnavailableError("auth refresh timeout") from exc
    except grpc.aio.AioRpcError as exc:
        raise _map_rpc_error(exc) from exc
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth refresh codec error") from exc


async def refresh_operator_session(
    *,
    auth_grpc_addr: str,
    refresh_token: str,
    timeout_seconds: float = 5.0,
) -> RefreshedSession:
    """Call Auth IssueOperatorSession with refresh_token (no PAT bearer)."""
    assert_trusted_insecure_auth_target(auth_grpc_addr)
    raw = await _call_issue_operator_session(
        auth_grpc_addr=auth_grpc_addr,
        refresh_token=refresh_token,
        timeout_seconds=timeout_seconds,
    )
    return _parse_refreshed_session(raw)
