"""Auth-owned operator session refresh (RS256 IssueOperatorSession with refresh_token)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import grpc
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.target import assert_trusted_insecure_auth_target

logger = logging.getLogger(__name__)

_ISSUE_METHOD = "/ibex.auth.v1.AuthService/IssueOperatorSession"


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        out.append(bits | (0x80 if value else 0))
        if not value:
            return bytes(out)


def encode_issue_with_refresh(refresh_token: str) -> bytes:
    """Encode IssueOperatorSessionRequest{refresh_token=...} (field 1, string)."""
    raw = refresh_token.encode("utf-8")
    return bytes([0x0A]) + _encode_varint(len(raw)) + raw


def _decode_string_field(buf: bytes, field_num: int) -> str | None:
    i = 0
    while i < len(buf):
        key = buf[i]
        i += 1
        fn, wt = key >> 3, key & 7
        if wt == 2:
            length, shift = 0, 0
            while True:
                b = buf[i]
                i += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            val = buf[i : i + length]
            i += length
            if fn == field_num:
                return val.decode("utf-8")
        elif wt == 0:
            while buf[i] & 0x80:
                i += 1
            i += 1
        else:
            return None
    return None


@dataclass(frozen=True, slots=True)
class RefreshedSession:
    access_token: str
    refresh_token: str


async def refresh_operator_session(
    *,
    auth_grpc_addr: str,
    refresh_token: str,
    timeout_seconds: float = 5.0,
) -> RefreshedSession:
    """Call Auth IssueOperatorSession with refresh_token (no PAT bearer)."""
    assert_trusted_insecure_auth_target(auth_grpc_addr)
    payload = encode_issue_with_refresh(refresh_token)
    try:
        async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                _ISSUE_METHOD,
                request_serializer=lambda b: b,
                response_deserializer=lambda b: b,
            )
            raw = await asyncio.wait_for(stub(payload), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise AuthUnavailableError("auth refresh timeout") from exc
    except grpc.aio.AioRpcError as exc:
        if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            raise AuthUnavailableError("auth unavailable") from exc
        if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            raise AuthFailedError("invalid refresh token") from exc
        logger.warning("auth refresh rpc failed code=%s", exc.code())
        raise AuthUnavailableError("auth refresh failed") from exc
    access = _decode_string_field(raw, 1)
    refresh = _decode_string_field(raw, 2)
    if not access or not refresh:
        raise AuthUnavailableError("auth refresh returned incomplete tokens")
    return RefreshedSession(access_token=access, refresh_token=refresh)
