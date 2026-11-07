"""Unit coverage for ValidateAgent verifier paths (3.5.F.2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import grpc
import pytest
from authclient import encode_validate_agent_request

from app.agent_verifier import (
    AllowAllAgentVerifier,
    GRPCAgentVerifier,
    StaticAgentVerifier,
    _require_active_payload,
    _serialize_request,
)
from app.errors import AuthUnavailableError, PermissionDeniedError

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")
TOKEN = "test-pat-token"


def _active_payload(*, status: str = "active") -> bytes:
    agent_b = str(AGENT).encode()
    org_b = str(ORG).encode()
    status_b = status.encode()
    payload = b"\x0a" + bytes([len(agent_b)]) + agent_b
    payload += b"\x12" + bytes([len(org_b)]) + org_b
    payload += b"\x1a" + bytes([len(status_b)]) + status_b
    return payload


@pytest.mark.asyncio
async def test_allow_all_and_static_helpers() -> None:
    await AllowAllAgentVerifier().verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
    await AllowAllAgentVerifier().aclose()

    allow = StaticAgentVerifier(allowed={(ORG, AGENT)})
    await allow.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
    await allow.aclose()

    deny = StaticAgentVerifier(allowed=set())
    with pytest.raises(PermissionDeniedError, match="agent is not active"):
        await deny.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)


def test_serialize_request() -> None:
    wire = _serialize_request((str(AGENT), str(ORG)))
    assert wire == encode_validate_agent_request(agent_id=str(AGENT), org_id=str(ORG))


def test_require_active_payload_accepts_active() -> None:
    _require_active_payload(_active_payload())


def test_require_active_payload_rejects_suspended() -> None:
    payload = _active_payload(status="suspended")
    with pytest.raises(PermissionDeniedError, match="agent is not active"):
        _require_active_payload(payload)


def test_require_active_payload_rejects_non_bytes() -> None:
    payload: object = "not-bytes"
    with pytest.raises(AuthUnavailableError, match="not bytes"):
        _require_active_payload(payload)


def test_require_active_payload_rejects_malformed() -> None:
    payload = b"\xff\xfe\xfd"
    with pytest.raises(AuthUnavailableError):
        _require_active_payload(payload)


@pytest.mark.asyncio
async def test_grpc_verifier_active_and_aclose() -> None:
    verifier = GRPCAgentVerifier("127.0.0.1:9", timeout_seconds=0)
    assert verifier._timeout == 0.05
    with patch.object(verifier, "_ensure_stub", return_value=AsyncMock()) as ensure:
        ensure.return_value = AsyncMock(return_value=_active_payload())
        await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
        ensure.return_value.assert_awaited_once()
        call_kwargs = ensure.return_value.await_args.kwargs
        assert call_kwargs["metadata"] == (("authorization", f"Bearer {TOKEN}"),)
    await verifier.aclose()
    assert verifier._channel is None
    assert verifier._stub is None


@pytest.mark.asyncio
async def test_grpc_verifier_uses_tls_when_ca_file_is_set(tmp_path: Path) -> None:
    bundle = (
        b"-----BEGIN CERTIFICATE-----\n"
        b"MIIDDzCCAfegAwIBAgIUYkpMtWlr9joO1DuN8xbJDn+LxUcwDQYJKoZIhvcNAQEL\n"
        b"BQAwFzEVMBMGA1UEAwwMaWJleC10ZXN0LWNhMB4XDTI2MTEwNzExMjgyM1oXDTM2\n"
        b"MTEwNDExMjgyM1owFzEVMBMGA1UEAwwMaWJleC10ZXN0LWNhMIIBIjANBgkqhkiG\n"
        b"9w0BAQEFAAOCAQ8AMIIBCgKCAQEAlH6um7tAtkEPowNbvEAHYaQKSMqhNHVtZ87p\n"
        b"9z6iHMr8uADSwcPA/aCZP2xPkMN8ExyE/q/bGltJKuvZSJALFZOT8sVbPmHTnqLw\n"
        b"RuyHwKYOpsdQqBf/SpouDj74cjCTneM1ogoxTnUmlh3iJCn9Q/IC4H2Zacqr9hen\n"
        b"+IOWsvOZxMNLhqx7BuF1um/S8TZLEeDec79fxMT5JrQPX2zyPuZAx7UzCKbay84C\n"
        b"cWJRgv2426YC/m3pdYAL+pguUXj9j16EVu2Y39EDktqNdB3cj71CxKXfJDKvNLTH\n"
        b"341IcMQyyTL+BPDpjmzMwyHfQAFSg7oSJEn4U7TTWKx0VZ252wIDAQABo1MwUTAd\n"
        b"BgNVHQ4EFgQUUgqAqOchTd6YsmOHGakJUG63T3YwHwYDVR0jBBgwFoAUUgqAqOch\n"
        b"Td6YsmOHGakJUG63T3YwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOC\n"
        b"AQEAVKAVyIudfAKDrfy+d0EmUQ7HTrQ4wHCpLZmAaehmznTUiM6ZtxOGRhsRfq8k\n"
        b"AVZjxV3VSb5j0L8eL7Ykr5Zu1mCCpNM7/IR4PrSBcvTkAsUyN3MCOdXgwibXf9bG\n"
        b"wMo8A33hi9JDuTwnaCKRLVjqTQ7NTPXl/AYVkPGBxKjaoP8sVJgeysXc0SJfzkkD\n"
        b"lsG2dbrVWrGcdIiGmQSgf15PToChLV4l32/HlM9YyJH/fCSpA2BC/lUw5SKKvmE0\n"
        b"lgHBICqtwcF/89B1MFBv86VE0I1rOvRT5OXMWu6zIRZW7rkpcQGQ/e7uBr9GNZS6\n"
        b"V8+kT7XgiVlD1Y7cOGpFSWvFIg==\n"
        b"-----END CERTIFICATE-----\n"
    )
    ca_file = tmp_path / "auth-ca.pem"
    ca_file.write_bytes(bundle)
    # A public host is allowed once TLS authenticates AuthService (ADR-0097 §4).
    verifier = GRPCAgentVerifier("auth.example.com:9091", 0.01, str(ca_file))
    channel = MagicMock()
    channel.close = AsyncMock()
    channel.unary_unary.return_value = AsyncMock(return_value=_active_payload())
    credentials = object()
    with (
        patch("authclient.channel.grpc.ssl_channel_credentials", return_value=credentials),
        patch(
            "authclient.channel.grpc.aio.secure_channel", return_value=channel
        ) as secure_mock,
        patch("authclient.channel.grpc.aio.insecure_channel") as insecure_mock,
    ):
        await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
    secure_mock.assert_called_once_with("auth.example.com:9091", credentials)
    insecure_mock.assert_not_called()
    await verifier.aclose()


def test_grpc_verifier_rejects_untrusted_target_without_a_ca_file() -> None:
    with pytest.raises(ValueError, match="refusing target"):
        GRPCAgentVerifier("auth.example.com:9091", 0.01)


def test_grpc_verifier_treats_a_whitespace_ca_file_as_unset() -> None:
    # Matching the Go client: a padded-but-empty value must not switch to TLS.
    with pytest.raises(ValueError, match="refusing target"):
        GRPCAgentVerifier("auth.example.com:9091", 0.01, "   ")


@pytest.mark.asyncio
async def test_grpc_verifier_maps_permission_denied_inactive() -> None:
    verifier = GRPCAgentVerifier("127.0.0.1:9", timeout_seconds=0.01)
    inactive = grpc.aio.AioRpcError(
        code=grpc.StatusCode.PERMISSION_DENIED,
        initial_metadata=(),
        trailing_metadata=(),
        details="agent is not active",
    )
    other = grpc.aio.AioRpcError(
        code=grpc.StatusCode.PERMISSION_DENIED,
        initial_metadata=(),
        trailing_metadata=(),
        details="cross-org",
    )
    unavailable = grpc.aio.AioRpcError(
        code=grpc.StatusCode.UNAVAILABLE,
        initial_metadata=(),
        trailing_metadata=(),
        details="down",
    )
    stub = AsyncMock()
    with patch.object(verifier, "_ensure_stub", return_value=stub):
        stub.side_effect = inactive
        with pytest.raises(PermissionDeniedError, match="agent is not active"):
            await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)

        stub.side_effect = other
        with pytest.raises(PermissionDeniedError, match="agent not authorized"):
            await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)

        stub.side_effect = unavailable
        with pytest.raises(AuthUnavailableError):
            await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)

        stub.side_effect = OSError("boom")
        with pytest.raises(AuthUnavailableError):
            await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)

        stub.side_effect = None
        stub.return_value = _active_payload(status="suspended")
        with pytest.raises(PermissionDeniedError, match="agent is not active"):
            await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
    await verifier.aclose()


@pytest.mark.asyncio
async def test_grpc_verifier_rebuilds_stub_across_loops() -> None:
    verifier = GRPCAgentVerifier("127.0.0.1:9", timeout_seconds=0.01)
    channel = MagicMock()
    channel.close = AsyncMock()
    stub = AsyncMock(return_value=_active_payload())
    channel.unary_unary.return_value = stub
    with patch("app.agent_verifier.grpc.aio.insecure_channel", return_value=channel):
        await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
        assert verifier._stub is stub
        # Same loop reuses stub.
        await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
        assert channel.unary_unary.call_count == 1
        # Force stale-loop path: clear loop marker and rebuild.
        verifier._loop = object()  # type: ignore[assignment]
        await verifier.verify(bearer=TOKEN, org_id=ORG, agent_id=AGENT)
        assert channel.unary_unary.call_count == 2
    await verifier.aclose()
    channel.close.assert_awaited()


def test_agent_verifier_rejects_a_missing_ca_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        GRPCAgentVerifier(
            "auth:9091", timeout_seconds=1.0, ca_file=str(tmp_path / "missing.pem")
        )
