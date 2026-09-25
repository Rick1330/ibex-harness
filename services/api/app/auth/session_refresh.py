"""Auth-owned operator session refresh (RS256 IssueOperatorSession with refresh_token)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import grpc
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.target import assert_trusted_insecure_auth_target

from app.auth.session_refresh_codec import (
    decode_int64_field,
    decode_string_field,
    decode_string_fields,
    encode_issue_with_refresh,
    encode_string_fields,
)

logger = logging.getLogger(__name__)

_ISSUE_METHOD = "/ibex.auth.v1.AuthService/IssueOperatorSession"
_VALIDATE_METHOD = "/ibex.auth.v1.AuthService/ValidateOperatorSession"
_REVOKE_METHOD = "/ibex.auth.v1.AuthService/RevokeOperatorSession"
_CONSUME_STEP_UP_METHOD = "/ibex.auth.v1.AuthService/ConsumeStepUp"

# Re-export for unit tests that previously imported private helpers.
_decode_string_field = decode_string_field


@dataclass(frozen=True, slots=True)
class RefreshedSession:
    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class ValidatedSession:
    subject: str
    org_id: str
    permissions: int
    session_id: str
    jti: str


async def _call_lifecycle(
    *, auth_grpc_addr: str, method: str, payload: bytes, timeout_seconds: float
) -> bytes:
    assert_trusted_insecure_auth_target(auth_grpc_addr)
    try:
        async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
            stub = channel.unary_unary(method, request_serializer=lambda b: b, response_deserializer=lambda b: b)
            return await asyncio.wait_for(stub(payload), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise AuthUnavailableError("auth lifecycle timeout") from exc
    except grpc.aio.AioRpcError as exc:
        if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            raise AuthFailedError("invalid session") from exc
        raise AuthUnavailableError("auth lifecycle unavailable") from exc


async def validate_operator_session(*, auth_grpc_addr: str, access_token: str, timeout_seconds: float = 5.0) -> ValidatedSession:
    raw = await _call_lifecycle(
        auth_grpc_addr=auth_grpc_addr,
        method=_VALIDATE_METHOD,
        payload=encode_string_fields({1: access_token}),
        timeout_seconds=timeout_seconds,
    )
    try:
        strings = decode_string_fields(raw, {1, 2, 4, 5})
        permissions = decode_int64_field(raw, 3)
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth session validation codec error") from exc
    if not strings.get(1) or not strings.get(2) or not strings.get(4) or not strings.get(5):
        raise AuthUnavailableError("auth session validation returned incomplete claims")
    return ValidatedSession(strings[1], strings[2], permissions or 0, strings[4], strings[5])


async def revoke_operator_session(*, auth_grpc_addr: str, session_id: str, family_id: str = "", access_jti: str = "", access_token: str = "", refresh_token: str = "", timeout_seconds: float = 5.0) -> None:
    await _call_lifecycle(
        auth_grpc_addr=auth_grpc_addr,
        method=_REVOKE_METHOD,
        payload=encode_string_fields(
            {1: session_id, 2: family_id, 3: access_jti, 4: access_token, 5: refresh_token}
        ),
        timeout_seconds=timeout_seconds,
    )


async def consume_step_up(*, auth_grpc_addr: str, token: str, subject: str, org_id: str, session_id: str, action: str, permission: int, timeout_seconds: float = 5.0) -> None:
    payload = encode_string_fields({1: token, 2: subject, 3: org_id, 4: session_id, 5: action})
    if permission:
        payload += b"\x30" + encode_varint(permission)
    await _call_lifecycle(auth_grpc_addr=auth_grpc_addr, method=_CONSUME_STEP_UP_METHOD, payload=payload, timeout_seconds=timeout_seconds)


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
