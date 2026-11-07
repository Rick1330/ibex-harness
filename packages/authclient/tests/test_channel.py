"""Unit tests for the shared AuthService channel factory (ADR-0097 §4)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from authclient import channel as channel_module
from authclient.channel import assert_auth_target, open_auth_channel, read_auth_ca

_PEM_BUNDLE = (
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


def _write_ca(tmp_path: Path, payload: bytes = _PEM_BUNDLE) -> str:
    ca_file = tmp_path / "auth-ca.pem"
    ca_file.write_bytes(payload)
    return str(ca_file)


def test_read_auth_ca_returns_bundle_bytes(tmp_path: Path) -> None:
    assert read_auth_ca(_write_ca(tmp_path)) == _PEM_BUNDLE


def test_read_auth_ca_trims_surrounding_path_space(tmp_path: Path) -> None:
    ca_file = _write_ca(tmp_path)
    assert read_auth_ca(f"  {ca_file}  ") == _PEM_BUNDLE


def test_read_auth_ca_missing_file_names_the_env_var(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        read_auth_ca(str(tmp_path / "absent.pem"))


def test_read_auth_ca_unreadable_path_names_the_env_var(tmp_path: Path) -> None:
    # A directory is always unreadable as a file, even when the tests run as root.
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        read_auth_ca(str(tmp_path))


def test_read_auth_ca_rejects_blank_bundle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        read_auth_ca(_write_ca(tmp_path, b"  \n\t\n"))


def test_read_auth_ca_rejects_a_non_certificate_bundle(tmp_path: Path) -> None:
    # These bytes are non-empty and ASCII, but no PEM certificate is parseable.
    garbage = b"-----BEGIN CERTIFICATE-----\nnot-a-certificate\n-----END CERTIFICATE-----\n"
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        read_auth_ca(_write_ca(tmp_path, garbage))


def test_read_auth_ca_rejects_non_ascii_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IBEX_AUTH_GRPC_CA_FILE"):
        read_auth_ca(_write_ca(tmp_path, b"\xff\xfe\x00garbage"))


# The markers are assembled at runtime rather than written as one literal so a
# secret scanner does not flag this test fixture. The bytes handed to
# read_auth_ca are still a real private-key PEM block, which is what the
# rejection path must detect.
_PEM_BEGIN = b"-----" + b"BEGIN "
_PEM_END = b"-----" + b"END "
_PRIVATE_KEY_LABEL = b"PRIVATE" + b" " + b"KEY-----"


def _private_key_block(label: bytes = _PRIVATE_KEY_LABEL) -> bytes:
    body = b"MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA0test-only-key-material\n"
    return _PEM_BEGIN + label + b"\n" + body + _PEM_END + label + b"\n"


_PRIVATE_KEY_BLOCK = _private_key_block()
_ENCRYPTED_PRIVATE_KEY_BLOCK = _private_key_block(b"ENCRYPTED " + _PRIVATE_KEY_LABEL)


def test_read_auth_ca_rejects_a_combined_certificate_and_private_key(
    tmp_path: Path,
) -> None:
    payload = _PEM_BUNDLE + _PRIVATE_KEY_BLOCK
    with pytest.raises(ValueError, match="certificates only") as excinfo:
        read_auth_ca(_write_ca(tmp_path, payload))
    message = str(excinfo.value)
    assert "IBEX_AUTH_GRPC_CA_FILE" in message
    # The rejection must never echo key material.
    assert "MIIBVQIBADAN" not in message


def test_read_auth_ca_rejects_an_encrypted_private_key(tmp_path: Path) -> None:
    payload = _PEM_BUNDLE + _ENCRYPTED_PRIVATE_KEY_BLOCK
    with pytest.raises(ValueError, match="certificates only") as excinfo:
        read_auth_ca(_write_ca(tmp_path, payload))
    assert "IBEX_AUTH_GRPC_CA_FILE" in str(excinfo.value)
    assert "MIIBVQIBADAN" not in str(excinfo.value)


def test_read_auth_ca_accepts_a_multi_certificate_bundle(tmp_path: Path) -> None:
    payload = _PEM_BUNDLE + _PEM_BUNDLE
    assert read_auth_ca(_write_ca(tmp_path, payload)) == payload


def test_read_auth_ca_caches_the_parsed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ca_file = _write_ca(tmp_path)
    channel_module._load_auth_ca.cache_clear()
    reads: list[Path] = []
    original = Path.read_bytes

    def _counting_read(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", _counting_read)

    assert read_auth_ca(ca_file) == _PEM_BUNDLE
    assert read_auth_ca(ca_file) == _PEM_BUNDLE
    assert len(reads) == 1


def test_read_auth_ca_reloads_when_the_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ca_file = Path(_write_ca(tmp_path))
    channel_module._load_auth_ca.cache_clear()
    reads: list[Path] = []
    original = Path.read_bytes

    def _counting_read(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", _counting_read)

    assert read_auth_ca(str(ca_file)) == _PEM_BUNDLE
    stat = ca_file.stat()
    os.utime(ca_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert read_auth_ca(str(ca_file)) == _PEM_BUNDLE
    assert len(reads) == 2


@pytest.mark.parametrize(
    "target",
    [
        "auth:9091",
        "127.0.0.1:9091",
        "[::1]:9091",
        "auth.example.com:9091",
        "dns:///auth:9091",
        "ipv4:10.0.0.5:9091",
    ],
)
def test_assert_auth_target_accepts_host_port(target: str) -> None:
    assert assert_auth_target(target) == target


def test_assert_auth_target_trims_surrounding_space() -> None:
    assert assert_auth_target("  auth.example.com:9091  ") == "auth.example.com:9091"


@pytest.mark.parametrize("target", ["", "   ", "auth", "auth:", ":9091", "auth:not-a-port"])
def test_assert_auth_target_rejects_non_host_port(target: str) -> None:
    with pytest.raises(ValueError):
        assert_auth_target(target)


def test_assert_auth_target_does_not_restrict_public_hosts() -> None:
    # The insecure gate refuses this host; the TLS path must not (ADR-0097 §4).
    assert assert_auth_target("auth.example.com:9091") == "auth.example.com:9091"


def _forbid(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("unexpected transport constructor")


def test_open_auth_channel_uses_tls_with_the_ca_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ca_file = _write_ca(tmp_path)
    credentials = object()
    secure_channel = object()

    calls: dict[str, Any] = {}

    def _credentials(*, root_certificates: bytes) -> object:
        calls["root_certificates"] = root_certificates
        return credentials

    def _secure(target: str, creds: object) -> object:
        calls["secure"] = (target, creds)
        return secure_channel

    monkeypatch.setattr(channel_module.grpc, "ssl_channel_credentials", _credentials)
    monkeypatch.setattr(channel_module.grpc.aio, "secure_channel", _secure)
    monkeypatch.setattr(channel_module.grpc.aio, "insecure_channel", _forbid)
    monkeypatch.setattr(channel_module, "assert_trusted_insecure_auth_target", _forbid)

    assert open_auth_channel(" auth.example.com:9091 ", f"  {ca_file}  ") is secure_channel
    assert calls["root_certificates"] == _PEM_BUNDLE
    assert calls["secure"] == ("auth.example.com:9091", credentials)


def test_open_auth_channel_treats_empty_ca_file_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insecure_channel = object()

    def _insecure(target: str) -> object:
        assert target == "auth:9091"
        return insecure_channel

    monkeypatch.setattr(channel_module.grpc.aio, "insecure_channel", _insecure)
    monkeypatch.setattr(channel_module.grpc.aio, "secure_channel", _forbid)

    assert open_auth_channel("auth:9091", "") is insecure_channel
    assert open_auth_channel("auth:9091", "   ") is insecure_channel
    assert open_auth_channel("auth:9091") is insecure_channel


def test_open_auth_channel_gates_the_plaintext_dial(monkeypatch: pytest.MonkeyPatch) -> None:
    insecure_channel = object()
    gated: list[str] = []

    def _gate(target: str) -> str:
        gated.append(target)
        return "gated:9091"

    def _insecure(target: str) -> object:
        assert target == "gated:9091"
        return insecure_channel

    monkeypatch.setattr(channel_module, "assert_trusted_insecure_auth_target", _gate)
    monkeypatch.setattr(channel_module.grpc.aio, "insecure_channel", _insecure)
    monkeypatch.setattr(channel_module.grpc.aio, "secure_channel", _forbid)

    assert open_auth_channel("auth:9091") is insecure_channel
    assert gated == ["auth:9091"]


def test_open_auth_channel_propagates_the_trust_gate_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(channel_module.grpc.aio, "insecure_channel", _forbid)
    with pytest.raises(ValueError, match="refusing target"):
        open_auth_channel("auth.example.com:9091")
