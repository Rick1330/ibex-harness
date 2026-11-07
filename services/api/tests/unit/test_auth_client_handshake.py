"""Hermetic TLS handshake tests for the shared auth channel (ADR-0097 §4).

Every other Python TLS assertion is mock-based; these exercise a real
``grpc.aio`` TLS server and prove the property the mocks assume: the channel
trusts the configured CA, and fails closed on a wrong CA, plaintext, or a
certificate issued for another host.

``grpcio``'s ``Channel.channel_ready`` retries a failed handshake indefinitely
and never raises, so the negative cases assert the first RPC's status instead:
a transport failure is ``UNAVAILABLE``, while a reachable server with no such
method is ``UNIMPLEMENTED``. Both are deterministic and bounded.
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import grpc
import pytest
from authclient.channel import open_auth_channel
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

_HANDSHAKE_TIMEOUT_SECONDS = 2.0
_RPC_METHOD = "/ibex.test.v1.HandshakeProbe/Probe"


def _make_ca(common_name: str = "ibex-test-ca") -> tuple[object, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _make_server_certificate(
    ca_key: object,
    ca_certificate: x509.Certificate,
    *,
    dns_names: list[str],
    ip_addresses: list[str],
) -> tuple[object, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0])])
    now = datetime.now(UTC)
    subject_alt_names: list[x509.GeneralName] = [
        x509.DNSName(name) for name in dns_names
    ]
    subject_alt_names.extend(
        x509.IPAddress(ipaddress.ip_address(address)) for address in ip_addresses
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(subject_alt_names), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, certificate


def _pem_private_key(key: object) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _pem_certificate(certificate: x509.Certificate) -> bytes:
    return certificate.public_bytes(serialization.Encoding.PEM)


def _write_ca(path: Path, certificate: x509.Certificate) -> str:
    path.write_bytes(_pem_certificate(certificate))
    return str(path)


@asynccontextmanager
async def _tls_server(
    ca_key: object,
    ca_certificate: x509.Certificate,
    *,
    dns_names: list[str],
    ip_addresses: list[str],
) -> AsyncIterator[int]:
    key, certificate = _make_server_certificate(
        ca_key,
        ca_certificate,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
    )
    server = grpc.aio.server()
    credentials = grpc.ssl_server_credentials(
        ((_pem_private_key(key), _pem_certificate(certificate)),)
    )
    port = server.add_secure_port("127.0.0.1:0", credentials)
    await server.start()
    try:
        yield port
    finally:
        await server.stop(None)


async def _assert_transport_unavailable(channel: grpc.aio.Channel) -> None:
    stub = channel.unary_unary(_RPC_METHOD)
    with pytest.raises(grpc.aio.AioRpcError) as excinfo:
        await stub(b"", timeout=_HANDSHAKE_TIMEOUT_SECONDS)
    assert excinfo.value.code() == grpc.StatusCode.UNAVAILABLE


async def test_secure_channel_completes_the_handshake_with_the_configured_ca(
    tmp_path: Path,
) -> None:
    ca_key, ca_certificate = _make_ca()
    ca_file = _write_ca(tmp_path / "ca.pem", ca_certificate)

    async with _tls_server(
        ca_key, ca_certificate, dns_names=["localhost"], ip_addresses=["127.0.0.1"]
    ) as port:
        channel = open_auth_channel(f"localhost:{port}", ca_file)
        try:
            await asyncio.wait_for(
                channel.channel_ready(), timeout=_HANDSHAKE_TIMEOUT_SECONDS
            )
            # Channel READY plus a real RPC proves the server was reached.
            stub = channel.unary_unary(_RPC_METHOD)
            with pytest.raises(grpc.aio.AioRpcError) as excinfo:
                await stub(b"", timeout=_HANDSHAKE_TIMEOUT_SECONDS)
            assert excinfo.value.code() == grpc.StatusCode.UNIMPLEMENTED
        finally:
            await channel.close()


async def test_wrong_ca_fails_the_handshake(tmp_path: Path) -> None:
    ca_key, ca_certificate = _make_ca()
    _, other_ca_certificate = _make_ca("other-ca")
    other_ca_file = _write_ca(tmp_path / "other-ca.pem", other_ca_certificate)

    async with _tls_server(
        ca_key, ca_certificate, dns_names=["localhost"], ip_addresses=["127.0.0.1"]
    ) as port:
        channel = open_auth_channel(f"localhost:{port}", other_ca_file)
        try:
            await _assert_transport_unavailable(channel)
        finally:
            await channel.close()


async def test_plaintext_channel_cannot_talk_to_the_tls_server(tmp_path: Path) -> None:
    ca_key, ca_certificate = _make_ca()

    async with _tls_server(
        ca_key, ca_certificate, dns_names=["localhost"], ip_addresses=["127.0.0.1"]
    ) as port:
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        try:
            await _assert_transport_unavailable(channel)
        finally:
            await channel.close()


async def test_certificate_for_another_host_fails_the_handshake(tmp_path: Path) -> None:
    ca_key, ca_certificate = _make_ca()
    ca_file = _write_ca(tmp_path / "ca.pem", ca_certificate)

    async with _tls_server(
        ca_key, ca_certificate, dns_names=["otherhost"], ip_addresses=[]
    ) as port:
        channel = open_auth_channel(f"localhost:{port}", ca_file)
        try:
            await _assert_transport_unavailable(channel)
        finally:
            await channel.close()
