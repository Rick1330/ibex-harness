"""Unit tests for CreateStepUpToken issuance (codec, mapping, caller PAT)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import grpc
import pytest
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError

from app.auth.session_refresh import (
    CreateStepUpParams,
    StepUpAttemptLimitError,
    create_step_up,
)
from app.auth.session_refresh_codec import decode_string_fields, decode_timestamp_field
from tests.unit.session_refresh_test_support import (
    _assert_rpc_raises,
    _patch_channel,
    _proto_string,
    _proto_varint,
    _rpc,
)

_EPOCH_SECONDS = 1_767_268_800  # 2026-01-01T12:00:00Z


def _proto_timestamp(field_num: int, seconds: int, nanos: int = 0) -> bytes:
    inner = _proto_varint(1, seconds)
    if nanos:
        inner += _proto_varint(2, nanos)
    return encode_varint((field_num << 3) | 2) + encode_varint(len(inner)) + inner


def _create_step_up_params(**overrides: str) -> CreateStepUpParams:
    values = {
        "subject": "user-1",
        "org_id": "org-1",
        "session_id": "sid-1",
        "action": "org.delete",
        "code": "123456",
    }
    values.update(overrides)
    return CreateStepUpParams(**values)


@pytest.mark.asyncio
async def test_create_step_up_sends_the_bearer_metadata_and_bound_fields() -> None:
    stub = AsyncMock(
        return_value=_proto_string(1, "proof-1") + _proto_timestamp(2, _EPOCH_SECONDS, 123_456_000)
    )
    with _patch_channel(stub):
        issued = await create_step_up(
            _rpc("127.0.0.1:50051", "lifecycle-token"), _create_step_up_params(), pat="ibex_pat"
        )

    assert issued.token == "proof-1"
    assert issued.expires_at is not None
    assert issued.expires_at.isoformat() == "2026-01-01T12:00:00.123456+00:00"
    payload = stub.await_args.args[0]
    assert decode_string_fields(payload, {1, 2, 3, 4, 5}) == {
        1: "org-1",
        2: "user-1",
        3: "123456",
        4: "sid-1",
        5: "org.delete",
    }
    # Auth asserts the caller is the subject: a service credential would leave
    # the caller context unset and be refused.
    assert stub.await_args.kwargs["metadata"] == (("authorization", "Bearer ibex_pat"),)


@pytest.mark.asyncio
async def test_create_step_up_tolerates_a_response_without_an_expiry() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "proof-1"))
    with _patch_channel(stub):
        issued = await create_step_up(_rpc("127.0.0.1:50051"), _create_step_up_params(), pat="pat")
    assert issued.token == "proof-1"
    assert issued.expires_at is None


@pytest.mark.parametrize(
    ("code", "exc_type", "match"),
    [
        (grpc.StatusCode.RESOURCE_EXHAUSTED, StepUpAttemptLimitError, "attempt limit"),
        (grpc.StatusCode.UNAVAILABLE, AuthUnavailableError, "auth unavailable"),
        (grpc.StatusCode.DEADLINE_EXCEEDED, AuthUnavailableError, "auth unavailable"),
        # An AuthService outage is a retryable dependency error, not a wrong code.
        (grpc.StatusCode.INTERNAL, AuthUnavailableError, "auth unavailable"),
        (grpc.StatusCode.UNKNOWN, AuthUnavailableError, "auth unavailable"),
        (grpc.StatusCode.FAILED_PRECONDITION, AuthUnavailableError, "totp not configured"),
        (grpc.StatusCode.UNAUTHENTICATED, AuthFailedError, "step-up refused"),
        (grpc.StatusCode.PERMISSION_DENIED, AuthFailedError, "step-up refused"),
        (grpc.StatusCode.INVALID_ARGUMENT, AuthFailedError, "step-up refused"),
    ],
)
async def test_create_step_up_maps_every_refusal(
    code: grpc.StatusCode, exc_type: type[BaseException], match: str
) -> None:
    stub = AsyncMock(side_effect=grpc.aio.AioRpcError(code, details="internal detail"))
    err = await _assert_rpc_raises(
        stub,
        create_step_up(_rpc("127.0.0.1:50051"), _create_step_up_params(), pat="pat"),
        exc_type,
        match,
    )
    assert "internal detail" not in str(err)


@pytest.mark.asyncio
async def test_create_step_up_rejects_a_response_with_no_token() -> None:
    stub = AsyncMock(return_value=b"")
    await _assert_rpc_raises(
        stub,
        create_step_up(_rpc("127.0.0.1:50051"), _create_step_up_params(), pat="pat"),
        AuthUnavailableError,
        "no token",
    )


@pytest.mark.asyncio
async def test_create_step_up_maps_a_malformed_response_to_unavailable() -> None:
    stub = AsyncMock(return_value=b"\x0f")
    await _assert_rpc_raises(
        stub,
        create_step_up(_rpc("127.0.0.1:50051"), _create_step_up_params(), pat="pat"),
        AuthUnavailableError,
        "codec error",
    )


def test_decode_timestamp_field_round_trips_and_skips_other_fields() -> None:
    buf = _proto_string(9, "skip") + _proto_timestamp(2, _EPOCH_SECONDS, 500_000_000)
    decoded = decode_timestamp_field(buf, 2)
    assert decoded is not None
    assert decoded.isoformat() == "2026-01-01T12:00:00.500000+00:00"
    assert decode_timestamp_field(buf, 3) is None


def test_decode_timestamp_field_skips_a_varint_field_before_the_timestamp() -> None:
    buf = _proto_varint(7, 3) + _proto_timestamp(2, _EPOCH_SECONDS)
    decoded = decode_timestamp_field(buf, 2)
    assert decoded is not None
    assert decoded.timestamp() == _EPOCH_SECONDS


def test_timestamp_message_skips_fields_it_does_not_read() -> None:
    """``Timestamp`` carries only seconds and nanos; a third field is skipped."""
    inner = _proto_varint(5, 7) + _proto_string(6, "ignored") + _proto_varint(1, _EPOCH_SECONDS)
    buf = encode_varint((2 << 3) | 2) + encode_varint(len(inner)) + inner
    decoded = decode_timestamp_field(buf, 2)
    assert decoded is not None
    assert decoded.timestamp() == _EPOCH_SECONDS


@pytest.mark.parametrize(
    ("seconds", "nanos", "match"),
    [
        (_EPOCH_SECONDS, 1_000_000_000, "nanoseconds out of range"),
        (2**62, 0, "timestamp out of range"),
    ],
)
def test_decode_timestamp_field_rejects_an_out_of_range_value(
    seconds: int, nanos: int, match: str
) -> None:
    buf = _proto_timestamp(2, seconds, nanos)
    with pytest.raises(AuthCodecError, match=match):
        decode_timestamp_field(buf, 2)


def test_decode_timestamp_field_rejects_an_oversized_message() -> None:
    from app.auth import session_refresh_codec as codec

    with pytest.raises(AuthCodecError, match="too large"):
        decode_timestamp_field(b"\x00" * (codec._MAX_MESSAGE + 1), 2)
