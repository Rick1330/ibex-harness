"""Auth-owned operator session refresh (RS256 IssueOperatorSession with refresh_token)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import grpc
from authclient.channel import AuthCAError, open_auth_channel
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError

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
_SERVICE_TOKEN_HEADER = "x-ibex-service-token"
_EXPECTED_ORG_HEADER = "x-ibex-expected-org"

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
    """Shared Auth gRPC target, credentials, timeout, and optional CA bundle.

    The two credentials are separate because they carry different authority in
    AuthService: ``lifecycle_token`` authenticates validate, revoke and
    consume-step-up; ``issue_token`` authenticates issuance. Neither is valid
    for the other's methods, and a lifecycle call must also name the org it is
    acting for (see ``_call_lifecycle``).
    """

    auth_grpc_addr: str
    lifecycle_token: str = ""
    timeout_seconds: float = 5.0
    ca_file: str = ""
    issue_token: str = field(default="", kw_only=True)


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


# gRPC metadata is an ordered sequence of (key, value) string pairs.
_Metadata = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _UnaryCall:
    """One unary AuthService call: the method, its encoded request, its metadata."""

    method: str
    payload: bytes
    metadata: _Metadata


@asynccontextmanager
async def _auth_channel(rpc: AuthRPC) -> AsyncIterator[grpc.aio.Channel]:
    """Open the Auth channel, mapping a CA load failure to AuthUnavailableError.

    A CA file that disappears or becomes invalid after startup is a degraded
    dependency, not a programming error: the session routes already translate
    AuthUnavailableError into their SERVICE_DEGRADED response.
    """
    try:
        channel = open_auth_channel(rpc.auth_grpc_addr, rpc.ca_file)
    except AuthCAError as exc:
        raise AuthUnavailableError("auth CA unavailable") from exc
    async with channel as opened:
        yield opened


def _identity(payload: bytes) -> bytes:
    """Pass protobuf bytes through unchanged; the codec owns encoding."""
    return payload


async def _unary_bytes(
    channel: grpc.aio.Channel, call: _UnaryCall, *, timeout_seconds: float
) -> bytes:
    """Await one unary call on an open channel, bounded by the call timeout."""
    stub = channel.unary_unary(
        call.method,
        request_serializer=_identity,
        response_deserializer=_identity,
    )
    return await asyncio.wait_for(
        stub(call.payload, metadata=call.metadata),
        timeout=timeout_seconds,
    )


async def _unary_with_channel(
    rpc: AuthRPC, call: _UnaryCall, *, timeout_message: str
) -> bytes:
    """Open the channel, await the call, and map a timeout to AuthUnavailableError."""
    try:
        async with _auth_channel(rpc) as channel:
            return await _unary_bytes(channel, call, timeout_seconds=rpc.timeout_seconds)
    except TimeoutError as exc:
        raise AuthUnavailableError(timeout_message) from exc


def _lifecycle_metadata(rpc: AuthRPC, expected_org: str) -> _Metadata:
    """Name the org the lifecycle call acts for; refuse a call that names none."""
    if not expected_org:
        raise AuthFailedError("missing expected org")
    return (
        (_SERVICE_TOKEN_HEADER, rpc.lifecycle_token),
        (_EXPECTED_ORG_HEADER, expected_org),
    )


def _map_lifecycle_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    """Map a lifecycle RPC failure: a refused proof is a failed session, else unavailable."""
    if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
        return AuthFailedError("invalid session")
    return AuthUnavailableError("auth lifecycle unavailable")


async def _call_lifecycle(
    rpc: AuthRPC, *, method: str, payload: bytes, expected_org: str
) -> bytes:
    """Call an org-scoped lifecycle method with the credential and org assertion.

    AuthService refuses the call when the asserted org differs from the org in
    the proof it verifies, and refuses it outright when no org is asserted.
    Neither value is an authorization decision taken here: the assertion is the
    API's own reading of the session it is acting on, and AuthService compares
    it to the claims it verified.
    """
    call = _UnaryCall(
        method=method,
        payload=payload,
        metadata=_lifecycle_metadata(rpc, expected_org),
    )
    try:
        return await _unary_with_channel(rpc, call, timeout_message="auth lifecycle timeout")
    except grpc.aio.AioRpcError as exc:
        raise _map_lifecycle_error(exc) from exc


def _token_payload(token: str) -> dict[str, object]:
    """Decode an unverified session token payload, failing closed when unreadable."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError) as exc:
        raise AuthFailedError("unreadable session token") from exc
    return payload if isinstance(payload, dict) else {}


def _session_org_claim(token: str) -> str:
    """Return the ``org_id`` claim from an unverified session token payload.

    Only the payload is read: AuthService verifies the signature and compares
    this value with the org it finds in the verified claims, so a forged token
    is refused there, not here. Raising ``AuthFailedError`` on an unreadable
    token is a fail-closed shortcut, not a validation step.
    """
    org_id = str(_token_payload(token).get("org_id") or "")
    if not org_id:
        raise AuthFailedError("session token carries no org")
    return org_id


async def validate_operator_session(
    rpc: AuthRPC, *, access_token: str
) -> ValidatedSession:
    raw = await _call_lifecycle(
        rpc,
        method=_VALIDATE_METHOD,
        payload=encode_string_fields({1: access_token}),
        expected_org=_session_org_claim(access_token),
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
        # The org of the proof being revoked. When both proofs are present the
        # access token names the org and AuthService compares it with the claims
        # of whichever proof it verified, so a mixed-org pair is refused.
        expected_org=_session_org_claim(params.access_token or params.refresh_token),
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
    # The org of the operator session that is asking for the action, not the org
    # of the proof: AuthService refuses before consuming when they differ.
    await _call_lifecycle(
        rpc,
        method=_CONSUME_STEP_UP_METHOD,
        payload=payload,
        expected_org=params.org_id,
    )


def _map_rpc_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
        return AuthUnavailableError("auth unavailable")
    if exc.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
        return AuthFailedError("invalid refresh token")
    logger.warning("auth refresh rpc failed code=%s", exc.code())
    return AuthUnavailableError("auth refresh failed")


def _map_issue_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    """Map an issuance failure, reporting an unconfigured issuer as unavailable."""
    mapped = _map_rpc_error(exc)
    if exc.code() == grpc.StatusCode.FAILED_PRECONDITION:
        return AuthUnavailableError("auth session issuer unavailable")
    return mapped


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
    call = _UnaryCall(
        method=_ISSUE_METHOD,
        payload=b"",
        # Login authenticates as the PAT. Sending a service credential too would
        # take the auth interceptor's service path and leave the caller context
        # unset. Refresh (below) is the service path, and presents the issue
        # credential.
        metadata=(("authorization", f"Bearer {pat}"),),
    )
    try:
        raw = await _unary_with_channel(rpc, call, timeout_message="auth session issue timeout")
    except grpc.aio.AioRpcError as exc:
        raise _map_issue_error(exc) from exc
    return _parse_refreshed_session(raw)


async def _call_issue_operator_session(rpc: AuthRPC, *, refresh_token: str) -> bytes:
    try:
        payload = encode_issue_with_refresh(refresh_token)
        call = _UnaryCall(
            method=_ISSUE_METHOD,
            payload=payload,
            metadata=((_SERVICE_TOKEN_HEADER, rpc.issue_token),),
        )
        return await _unary_with_channel(rpc, call, timeout_message="auth refresh timeout")
    except grpc.aio.AioRpcError as exc:
        raise _map_rpc_error(exc) from exc
    except AuthCodecError as exc:
        raise AuthUnavailableError("auth refresh codec error") from exc


async def refresh_operator_session(rpc: AuthRPC, *, refresh_token: str) -> RefreshedSession:
    """Call Auth IssueOperatorSession with refresh_token (no PAT bearer)."""
    raw = await _call_issue_operator_session(rpc, refresh_token=refresh_token)
    return _parse_refreshed_session(raw)
