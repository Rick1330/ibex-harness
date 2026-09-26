"""Unit tests for Auth-owned operator session refresh (protobuf + gRPC mapping)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError

from app.auth.session_refresh import (
    AuthRPC,
    ConsumeStepUpParams,
    RevokeSessionParams,
    _decode_string_field,
    consume_step_up,
    encode_issue_with_refresh,
    issue_operator_session,
    refresh_operator_session,
    revoke_operator_session,
    validate_operator_session,
)
from app.auth.session_refresh_codec import (
    decode_int64_field,
    decode_string_fields,
    encode_string_fields,
)


def _proto_string(field_num: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return encode_varint((field_num << 3) | 2) + encode_varint(len(raw)) + raw


def _proto_varint(field_num: int, value: int) -> bytes:
    return encode_varint((field_num << 3) | 0) + encode_varint(value)


def _rpc(addr: str = "127.0.0.1:50051", token: str = "", timeout: float = 5.0) -> AuthRPC:
    return AuthRPC(addr, token, timeout)



def test_encode_issue_with_refresh_multi_byte() -> None:
    long_tok = "r" * 200
    payload = encode_issue_with_refresh(long_tok)
    assert payload[0] == 0x0A
    assert long_tok.encode() in payload


def test_lifecycle_codec_round_trip() -> None:
    payload = encode_string_fields({1: "subject", 2: "org", 4: "sid", 5: "jti"}) + _proto_varint(
        3, 9
    )
    assert decode_string_fields(payload, {1, 2, 4, 5}) == {
        1: "subject",
        2: "org",
        4: "sid",
        5: "jti",
    }
    assert decode_int64_field(payload, 3) == 9


def test_decode_string_field_skips_other_fields_and_varints() -> None:
    buf = (
        _proto_varint(3, 42) + _proto_string(1, "access-token") + _proto_string(2, "refresh-token")
    )
    assert _decode_string_field(buf, 1) == "access-token"
    assert _decode_string_field(buf, 2) == "refresh-token"
    assert _decode_string_field(buf, 9) is None
    assert _decode_string_field(b"", 1) is None


def test_decode_string_field_multi_byte_key_and_length() -> None:
    long_val = "x" * 200
    # Field 16 requires a multi-byte protobuf key; length >= 128 is multi-byte too.
    buf = _proto_varint(7, 300) + _proto_string(16, long_val) + _proto_string(1, "access")
    assert _decode_string_field(buf, 16) == long_val
    assert _decode_string_field(buf, 1) == "access"


def test_decode_string_field_skips_fixed64() -> None:
    # wire type 1 (64-bit) is skipped, then field 1 is found.
    buf = bytes([0x09, 0, 0, 0, 0, 0, 0, 0, 0]) + _proto_string(1, "ok")
    assert _decode_string_field(buf, 1) == "ok"


def test_decode_string_field_rejects_unsupported_wire() -> None:
    with pytest.raises(AuthCodecError, match="unsupported wire type"):
        _decode_string_field(bytes([0x0F]), 1)


def _patch_channel(stub: AsyncMock):
    channel = MagicMock()
    channel.unary_unary.return_value = stub

    @asynccontextmanager
    async def _cm(_addr: str):
        yield channel

    return patch("app.auth.session_refresh.grpc.aio.insecure_channel", side_effect=_cm)


@pytest.mark.asyncio
async def test_refresh_operator_session_success() -> None:
    resp = _proto_string(1, "access-rs") + _proto_string(2, "refresh-rs")
    stub = AsyncMock(return_value=resp)
    with _patch_channel(stub):
        pair = await refresh_operator_session(
            _rpc("127.0.0.1:50051", "service-token"),
            refresh_token="old-refresh",
        )
    assert pair.access_token == "access-rs"
    assert pair.refresh_token == "refresh-rs"
    stub.assert_awaited_once()
    assert stub.await_args.kwargs["metadata"] == (("x-ibex-service-token", "service-token"),)


@pytest.mark.asyncio
async def test_refresh_operator_session_timeout() -> None:
    stub = AsyncMock(side_effect=TimeoutError())
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="timeout"):
        await refresh_operator_session(
            _rpc("localhost:50051", "", 0.01),
            refresh_token="r",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "exc_type", "match"),
    [
        (grpc.StatusCode.UNAVAILABLE, AuthUnavailableError, "unavailable"),
        (grpc.StatusCode.DEADLINE_EXCEEDED, AuthUnavailableError, "unavailable"),
        (grpc.StatusCode.UNAUTHENTICATED, AuthFailedError, "invalid refresh"),
        (grpc.StatusCode.PERMISSION_DENIED, AuthFailedError, "invalid refresh"),
        (grpc.StatusCode.INTERNAL, AuthUnavailableError, "refresh failed"),
    ],
)
async def test_refresh_operator_session_rpc_errors(code, exc_type, match) -> None:
    stub = AsyncMock(side_effect=grpc.aio.AioRpcError(code, details="boom"))
    with _patch_channel(stub), pytest.raises(exc_type, match=match):
        await refresh_operator_session(_rpc("127.0.0.1:50051"), refresh_token="r")


@pytest.mark.asyncio
async def test_refresh_operator_session_incomplete_response() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "access-only"))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="incomplete"):
        await refresh_operator_session(_rpc("127.0.0.1:50051"), refresh_token="r")


@pytest.mark.asyncio
async def test_refresh_operator_session_codec_error_maps_unavailable() -> None:
    stub = AsyncMock(return_value=bytes([0x0F]))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="codec"):
        await refresh_operator_session(_rpc("127.0.0.1:50051"), refresh_token="r")


def test_decode_string_field_skips_fixed32() -> None:
    # wire type 5 (32-bit) then field 1.
    buf = bytes([0x0D, 1, 2, 3, 4]) + _proto_string(1, "ok")
    assert _decode_string_field(buf, 1) == "ok"


def test_decode_string_field_rejects_oversized_message() -> None:
    from app.auth import session_refresh_codec as mod

    huge = b"\x00" * (mod._MAX_MESSAGE + 1)
    with pytest.raises(AuthCodecError, match="too large"):
        _decode_string_field(huge, 1)


def test_decode_string_field_rejects_truncated_varint_and_len() -> None:
    with pytest.raises(AuthCodecError, match="truncated varint"):
        _decode_string_field(bytes([0x80]), 1)
    # length-delimited key for field 1, then truncated length/body
    with pytest.raises(AuthCodecError, match="truncated"):
        _decode_string_field(bytes([0x0A, 0x05, 0x01]), 1)


def test_decode_string_field_rejects_field_over_max_token() -> None:
    from app.auth import session_refresh_codec as mod

    raw = b"x" * (mod._MAX_TOKEN_FIELD + 1)
    buf = encode_varint((1 << 3) | 2) + encode_varint(len(raw)) + raw
    with pytest.raises(AuthCodecError, match="exceeds limit"):
        _decode_string_field(buf, 1)


def test_decode_string_field_skips_length_delimited_other_field() -> None:
    buf = _proto_string(9, "skip-me") + _proto_string(1, "access")
    assert _decode_string_field(buf, 1) == "access"


def test_decode_string_field_rejects_overlong_varint() -> None:
    # 10 continuation bytes → shift > 63
    with pytest.raises(AuthCodecError, match="invalid varint"):
        _decode_string_field(bytes([0x80] * 10), 1)


def test_decode_string_field_rejects_truncated_fixed64() -> None:
    with pytest.raises(AuthCodecError, match="truncated fixed field"):
        _decode_string_field(bytes([0x09, 1, 2, 3]), 1)


def test_decode_string_field_rejects_truncated_fixed32() -> None:
    with pytest.raises(AuthCodecError, match="truncated fixed field"):
        _decode_string_field(bytes([0x0D, 1, 2]), 1)


@pytest.mark.asyncio
async def test_refresh_operator_session_empty_tokens() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "") + _proto_string(2, ""))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="incomplete"):
        await refresh_operator_session(_rpc("127.0.0.1:50051"), refresh_token="r")


@pytest.mark.asyncio
async def test_refresh_operator_session_auth_codec_error_from_rpc() -> None:
    stub = AsyncMock(side_effect=AuthCodecError("boom"))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="codec"):
        await refresh_operator_session(_rpc("127.0.0.1:50051"), refresh_token="r")


@pytest.mark.asyncio
async def test_lifecycle_rpc_clients() -> None:
    validate_resp = (
        _proto_string(1, "subject")
        + _proto_string(2, "org")
        + _proto_varint(3, 9)
        + _proto_string(4, "sid")
        + _proto_string(5, "jti")
    )
    stub = AsyncMock(return_value=validate_resp)
    with _patch_channel(stub):
        claims = await validate_operator_session(
            _rpc("127.0.0.1:50051", "service-token"),
            access_token="a",
        )
        await revoke_operator_session(
            _rpc("127.0.0.1:50051", "service-token"),
            RevokeSessionParams(
                session_id="sid",
                family_id="fid",
                access_jti="jti",
                access_token="a",
                refresh_token="r",
            ),
        )
        await consume_step_up(
            _rpc("127.0.0.1:50051", "service-token"),
            ConsumeStepUpParams(
                token="service-token",
                subject="subject",
                org_id="org",
                session_id="sid",
                action="legal_hold.manage",
                permission=8,
            ),
        )
    assert claims.subject == "subject"
    assert claims.permissions == 9
    revoke_payload = stub.await_args_list[1].args[0]
    assert decode_string_fields(revoke_payload, {1, 2, 3, 4, 5}) == {
        1: "sid",
        2: "fid",
        3: "jti",
        4: "a",
        5: "r",
    }
    assert all(
        call.kwargs["metadata"] == (("x-ibex-service-token", "service-token"),)
        for call in stub.await_args_list
    )


@pytest.mark.asyncio
async def test_validate_operator_session_defaults_omitted_proto3_permissions_to_zero() -> None:
    response = (
        _proto_string(1, "subject")
        + _proto_string(2, "org")
        + _proto_string(4, "sid")
        + _proto_string(5, "jti")
    )
    with _patch_channel(AsyncMock(return_value=response)):
        claims = await validate_operator_session(
            _rpc("127.0.0.1:50051"),
            access_token="access",
        )
    assert claims.permissions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _proto_string(2, "org") + _proto_string(4, "sid") + _proto_string(5, "jti"),
        _proto_string(1, "subject") + _proto_string(4, "sid") + _proto_string(5, "jti"),
        _proto_string(1, "subject") + _proto_string(2, "org") + _proto_string(5, "jti"),
        _proto_string(1, "subject") + _proto_string(2, "org") + _proto_string(4, "sid"),
    ],
)
async def test_validate_operator_session_rejects_each_missing_identity_claim(
    response: bytes,
) -> None:
    with (
        _patch_channel(AsyncMock(return_value=response)),
        pytest.raises(AuthUnavailableError, match="incomplete claims"),
    ):
        await validate_operator_session(_rpc("127.0.0.1:50051"), access_token="access")


@pytest.mark.asyncio
async def test_validate_operator_session_maps_malformed_wire_to_unavailable() -> None:
    with (
        _patch_channel(AsyncMock(return_value=b"\x0f")),
        pytest.raises(AuthUnavailableError, match="codec error"),
    ):
        await validate_operator_session(_rpc("127.0.0.1:50051"), access_token="access")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected", "message"),
    [
        (grpc.StatusCode.UNAUTHENTICATED, AuthFailedError, "invalid session"),
        (grpc.StatusCode.PERMISSION_DENIED, AuthFailedError, "invalid session"),
        (grpc.StatusCode.UNAVAILABLE, AuthUnavailableError, "unavailable"),
        (grpc.StatusCode.INTERNAL, AuthUnavailableError, "unavailable"),
    ],
)
async def test_validate_operator_session_maps_auth_service_errors(code, expected, message) -> None:
    stub = AsyncMock(side_effect=grpc.aio.AioRpcError(code, details="failure"))
    with _patch_channel(stub), pytest.raises(expected, match=message):
        await validate_operator_session(_rpc("127.0.0.1:50051"), access_token="access")


@pytest.mark.asyncio
async def test_validate_operator_session_maps_timeout_to_unavailable() -> None:
    with (
        _patch_channel(AsyncMock(side_effect=TimeoutError())),
        pytest.raises(AuthUnavailableError, match="timeout"),
    ):
        await validate_operator_session(
            _rpc("localhost:50051", "", 0.01),
            access_token="access",
        )


@pytest.mark.asyncio
async def test_consume_step_up_omits_zero_permission_wire_field() -> None:
    stub = AsyncMock(return_value=b"")
    with _patch_channel(stub):
        await consume_step_up(
            _rpc("127.0.0.1:50051"),
            ConsumeStepUpParams(
                token="step",
                subject="subject",
                org_id="org",
                session_id="sid",
                action="operator.export",
                permission=0,
            ),
        )
    payload = stub.await_args.args[0]
    assert decode_string_fields(payload, {1, 2, 3, 4, 5}) == {
        1: "step",
        2: "subject",
        3: "org",
        4: "sid",
        5: "operator.export",
    }
    assert decode_int64_field(payload, 6) is None


@pytest.mark.asyncio
async def test_issue_operator_session_sends_pat_and_service_metadata() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "access") + _proto_string(2, "refresh"))
    with _patch_channel(stub):
        pair = await issue_operator_session(
            _rpc("127.0.0.1:50051", "service-token"),
            pat="ibex_pat_private",
        )
    assert pair.access_token == "access"
    assert pair.refresh_token == "refresh"
    assert stub.await_args.args == (b"",)
    assert stub.await_args.kwargs["metadata"] == (
        ("authorization", "Bearer ibex_pat_private"),
        ("x-ibex-service-token", "service-token"),
    )


@pytest.mark.asyncio
async def test_issue_operator_session_maps_failed_precondition_without_leaking_details() -> None:
    stub = AsyncMock(
        side_effect=grpc.aio.AioRpcError(
            grpc.StatusCode.FAILED_PRECONDITION, details="internal key configuration"
        )
    )
    with (
        _patch_channel(stub),
        pytest.raises(AuthUnavailableError, match="issuer unavailable") as exc,
    ):
        await issue_operator_session(_rpc("127.0.0.1:50051"), pat="pat")
    assert "internal key configuration" not in str(exc.value)


@pytest.mark.asyncio
async def test_issue_operator_session_rejects_untrusted_insecure_target_before_dial() -> None:
    with pytest.raises(ValueError, match="refusing target"):
        await issue_operator_session(_rpc("auth.example.com:50051"), pat="pat")


@pytest.mark.parametrize("field_num", [1, 2])
def test_encode_string_fields_omits_empty_values_and_rejects_oversize(field_num: int) -> None:
    from app.auth.session_refresh_codec import _MAX_TOKEN_FIELD

    assert encode_string_fields({field_num: ""}) == b""
    with pytest.raises(AuthCodecError, match="exceeds limit"):
        encode_string_fields({field_num: "x" * (_MAX_TOKEN_FIELD + 1)})


def test_lifecycle_decoders_reject_oversized_messages() -> None:
    from app.auth import session_refresh_codec as codec

    huge = b"\x00" * (codec._MAX_MESSAGE + 1)
    with pytest.raises(AuthCodecError, match="too large"):
        decode_string_fields(huge, {1})
    with pytest.raises(AuthCodecError, match="too large"):
        decode_int64_field(huge, 3)


def test_lifecycle_string_decoder_rejects_invalid_utf8() -> None:
    malformed = encode_varint((1 << 3) | 2) + encode_varint(1) + b"\xff"
    with pytest.raises(AuthCodecError, match="utf-8"):
        decode_string_fields(malformed, {1})


@pytest.mark.asyncio
async def test_issue_operator_session_timeout_maps_to_unavailable() -> None:
    stub = AsyncMock(side_effect=TimeoutError())
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="issue timeout"):
        await issue_operator_session(
            _rpc("127.0.0.1:50051", "", 0.01),
            pat="pat",
        )
