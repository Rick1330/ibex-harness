"""Auth-owned operator session refresh (RS256 IssueOperatorSession with refresh_token)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import grpc
from authclient.codec import AuthCodecError
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.target import assert_trusted_insecure_auth_target

from app.auth.session_refresh_codec import decode_string_field, encode_issue_with_refresh

logger = logging.getLogger(__name__)

_ISSUE_METHOD = "/ibex.auth.v1.AuthService/IssueOperatorSession"

# Re-export for unit tests that previously imported private helpers.
_decode_string_field = decode_string_field


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
        access = decode_string_field(raw, 1)
        refresh = decode_string_field(raw, 2)
    except (AuthCodecError, UnicodeDecodeError) as exc:
        raise AuthUnavailableError("auth refresh codec error") from exc
    if not access or not refresh:
        raise AuthUnavailableError("auth refresh returned incomplete tokens")
    return RefreshedSession(access_token=access, refresh_token=refresh)


async def issue_operator_session(
    *,
    auth_grpc_addr: str,
    pat: str,
    timeout_seconds: float = 5.0,
) -> RefreshedSession:
    """Issue an Auth-owned session pair for a validated PAT caller."""
    assert_trusted_insecure_auth_target(auth_grpc_addr)
    try:
        async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                _ISSUE_METHOD,
                request_serializer=lambda b: b,
                response_deserializer=lambda b: b,
            )
            raw = await asyncio.wait_for(
                stub(b"", metadata=(("authorization", f"Bearer {pat}"),)),
                timeout=timeout_seconds,
            )
    except TimeoutError as exc:
        raise AuthUnavailableError("auth session issue timeout") from exc
    except grpc.aio.AioRpcError as exc:
        mapped = _map_rpc_error(exc)
        if exc.code() == grpc.StatusCode.FAILED_PRECONDITION:
            mapped = AuthUnavailableError("auth session issuer unavailable")
        raise mapped from exc
    return _parse_refreshed_session(raw)


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
