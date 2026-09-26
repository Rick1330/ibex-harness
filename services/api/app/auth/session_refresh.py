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


@dataclass(frozen=True, slots=True)
class AuthRPC:
    """Shared Auth gRPC target + timeout for lifecycle calls."""

    auth_grpc_addr: str
    service_token: str = ""
    timeout_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class RevokeSessionParams:
    session_id: str
    family_id: str = ""
    access_jti: str = ""
    access_token: str = ""
    refresh_token: str = ""


@dataclass(frozen=True, slots=True)
class ConsumeStepUpParams:
    token: str
    subject: str
    org_id: str
    session_id: str
    action: str
    permission: int = 0


async def _call_lifecycle(rpc: AuthRPC, *, method: str, payload: bytes) -> bytes:
    assert_trusted_insecure_auth_target(rpc.auth_grpc_addr)
    try:
        async with grpc.aio.insecure_channel(rpc.auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                method, request_serializer=lambda b: b, response_deserializer=lambda b: b
            )
            return await asyncio.wait_for(
                stub(payload, metadata=(("x-ibex-service-token", rpc.service_token),)),
                timeout=rpc.timeout_seconds,
            )
    except TimeoutError as exc:
        raise AuthUnavailableError("auth lifecycle timeout") from exc
    except grpc.aio.AioRpcError as exc:
        if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            raise AuthFailedError("invalid session") from exc
        raise AuthUnavailableError("auth lifecycle unavailable") from exc


async def validate_operator_session(
    rpc: AuthRPC, *, access_token: str
) -> ValidatedSession:
    raw = await _call_lifecycle(
        rpc, method=_VALIDATE_METHOD, payload=encode_string_fields({1: access_token})
    )
    return _parse_validated_session(raw)


def _required_claim(strings: dict[int, str], field: int) -> str:
    value = strings.get(field) or ""
    if value:
        return value
    raise AuthUnavailableError("auth session validation returned incomplete claims")


def _parse_validated_session(raw: bytes) -> ValidatedSession:
    try:
        strings = decode_string_fields(raw, {1, 2, 4, 5})
        permissions = decode_int64_field(raw, 3)
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth session validation codec error") from exc
    return ValidatedSession(
        _required_claim(strings, 1),
        _required_claim(strings, 2),
        permissions or 0,
        _required_claim(strings, 4),
        _required_claim(strings, 5),
    )


async def revoke_operator_session(rpc: AuthRPC, params: RevokeSessionParams) -> None:
    await _call_lifecycle(
        rpc,
        method=_REVOKE_METHOD,
        payload=encode_string_fields(
            {
                1: params.session_id,
                2: params.family_id,
                3: params.access_jti,
                4: params.access_token,
                5: params.refresh_token,
            }
        ),
    )


async def consume_step_up(rpc: AuthRPC, params: ConsumeStepUpParams) -> None:
    payload = encode_string_fields(
        {
            1: params.token,
            2: params.subject,
            3: params.org_id,
            4: params.session_id,
            5: params.action,
        }
    )
    if params.permission:
        payload += b"\x30" + encode_varint(params.permission)
    await _call_lifecycle(rpc, method=_CONSUME_STEP_UP_METHOD, payload=payload)


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


async def issue_operator_session(rpc: AuthRPC, *, pat: str) -> RefreshedSession:
    """Issue an Auth-owned session pair for a validated PAT caller."""
    assert_trusted_insecure_auth_target(rpc.auth_grpc_addr)
    try:
        async with grpc.aio.insecure_channel(rpc.auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                _ISSUE_METHOD,
                request_serializer=lambda b: b,
                response_deserializer=lambda b: b,
            )
            raw = await asyncio.wait_for(
                stub(
                    b"",
                    metadata=(
                        ("authorization", f"Bearer {pat}"),
                        ("x-ibex-service-token", rpc.service_token),
                    ),
                ),
                timeout=rpc.timeout_seconds,
            )
    except TimeoutError as exc:
        raise AuthUnavailableError("auth session issue timeout") from exc
    except grpc.aio.AioRpcError as exc:
        mapped = _map_rpc_error(exc)
        if exc.code() == grpc.StatusCode.FAILED_PRECONDITION:
            mapped = AuthUnavailableError("auth session issuer unavailable")
        raise mapped from exc
    return _parse_refreshed_session(raw)


async def _call_issue_operator_session(rpc: AuthRPC, *, refresh_token: str) -> bytes:
    payload = encode_issue_with_refresh(refresh_token)
    try:
        async with grpc.aio.insecure_channel(rpc.auth_grpc_addr) as channel:
            stub = channel.unary_unary(
                _ISSUE_METHOD,
                request_serializer=lambda b: b,
                response_deserializer=lambda b: b,
            )
            return await asyncio.wait_for(
                stub(payload, metadata=(("x-ibex-service-token", rpc.service_token),)),
                timeout=rpc.timeout_seconds,
            )
    except TimeoutError as exc:
        raise AuthUnavailableError("auth refresh timeout") from exc
    except grpc.aio.AioRpcError as exc:
        raise _map_rpc_error(exc) from exc
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth refresh codec error") from exc


async def refresh_operator_session(rpc: AuthRPC, *, refresh_token: str) -> RefreshedSession:
    """Call Auth IssueOperatorSession with refresh_token (no PAT bearer)."""
    assert_trusted_insecure_auth_target(rpc.auth_grpc_addr)
    raw = await _call_issue_operator_session(rpc, refresh_token=refresh_token)
    return _parse_refreshed_session(raw)
