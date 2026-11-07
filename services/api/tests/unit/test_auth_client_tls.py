"""TLS-selection tests for the shared AuthService gRPC clients (ADR-0097 §4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authclient.provider_credentials import GRPCProviderCredentialManager
from authclient.revoke import GRPCTokenRevoker
from authclient.tokens import GRPCTokenManager
from authclient.validate import GRPCTokenValidator

_CA_BUNDLE = (
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


def _ca_file(tmp_path: Path) -> str:
    path = tmp_path / "auth-ca.pem"
    path.write_bytes(_CA_BUNDLE)
    return str(path)


def _channel() -> MagicMock:
    channel = MagicMock()
    channel.unary_unary.return_value = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.mark.parametrize(
    "build",
    [
        lambda target, ca_file: GRPCTokenValidator(target, 0.1, ca_file),
        lambda target, ca_file: GRPCTokenRevoker(target, 0.1, ca_file),
        lambda target, ca_file: GRPCTokenManager(target, 0.1, ca_file),
        lambda target, ca_file: GRPCProviderCredentialManager(target, 0.1, ca_file),
    ],
    ids=["validator", "revoker", "token-manager", "provider-credentials"],
)
def test_auth_client_uses_tls_when_ca_file_is_set(tmp_path: Path, build) -> None:
    ca_file = _ca_file(tmp_path)
    credentials = object()
    channel = _channel()
    with (
        patch(
            "authclient.channel.grpc.ssl_channel_credentials", return_value=credentials
        ) as credentials_mock,
        patch("authclient.channel.grpc.aio.secure_channel", return_value=channel) as secure_mock,
        patch("authclient.channel.grpc.aio.insecure_channel") as insecure_mock,
    ):
        build("auth.example.com:9091", ca_file)
    credentials_mock.assert_called_once_with(root_certificates=_CA_BUNDLE)
    # A non-loopback host is allowed once TLS authenticates the server.
    secure_mock.assert_called_once_with("auth.example.com:9091", credentials)
    insecure_mock.assert_not_called()


def test_auth_client_keeps_the_trust_gated_plaintext_dial_without_a_ca_file() -> None:
    channel = _channel()
    with (
        patch("authclient.channel.grpc.aio.insecure_channel", return_value=channel) as insecure_mock,
        patch("authclient.channel.grpc.aio.secure_channel") as secure_mock,
    ):
        GRPCTokenValidator("127.0.0.1:9091", 0.1)
    insecure_mock.assert_called_once_with("127.0.0.1:9091")
    secure_mock.assert_not_called()


def test_auth_client_rejects_a_missing_ca_bundle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        GRPCTokenValidator("auth.example.com:9091", 0.1, str(tmp_path / "absent.pem"))
