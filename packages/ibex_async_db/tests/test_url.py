"""Unit tests for async database URL parsing."""

from __future__ import annotations

import os
import ssl

import pytest

from ibex_async_db import normalize_async_database_url, parse_async_database_url


def _parse_tls_context_url(query_suffix: str) -> ssl.SSLContext:
    default_ca = ssl.get_default_verify_paths().cafile
    if not default_ca or not os.path.isfile(default_ca):
        pytest.skip("no system CA file available")
    target = parse_async_database_url(
        "postgresql://ibex:ibex@db.example:5432/ibex"
        f"?sslmode=verify-full&sslrootcert={default_ca}{query_suffix}"
    )
    ctx = target.connect_args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    return ctx


def test_parse_postgres_url_to_asyncpg() -> None:
    target = parse_async_database_url("postgres://u:p@localhost:5432/ibex?sslmode=disable")
    assert target.url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in target.url
    assert target.connect_args.get("ssl") is False


def test_parse_prefer_sslmode_local_host() -> None:
    target = parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=prefer")
    assert target.connect_args.get("ssl") == "prefer"


def test_parse_allow_sslmode() -> None:
    target = parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=allow")
    assert target.connect_args.get("ssl") == "allow"


def test_parse_prefer_sslmode_rejects_remote_host() -> None:
    with pytest.raises(ValueError, match="sslmode=prefer is only allowed"):
        parse_async_database_url("postgresql://u:p@db.example/ibex?sslmode=prefer")


def test_parse_require_uses_verified_tls() -> None:
    target = parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=require")
    assert target.connect_args.get("ssl") is True


def test_parse_unsupported_sslmode_raises() -> None:
    with pytest.raises(ValueError, match="unsupported sslmode"):
        parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=weird")


def test_normalize_plaintext_sslmode_disable() -> None:
    target = parse_async_database_url(
        "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"
    )
    assert target.url == "postgresql+asyncpg://ibex:ibex@localhost:5433/ibex_test"
    assert target.connect_args == {"ssl": False}
    assert (
        normalize_async_database_url(
            "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"
        )
        == target.url
    )


def test_normalize_verify_full_enables_hostname_checks() -> None:
    target = parse_async_database_url(
        "postgresql://ibex:ibex@db.example:5432/ibex?sslmode=verify-full"
    )
    assert "sslmode" not in target.url
    assert target.connect_args == {"ssl": True}


def test_normalize_custom_ca_builds_tls12_context() -> None:
    ctx = _parse_tls_context_url("")
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_sslcrl_rejected_for_verify_full_mode() -> None:
    default_ca = ssl.get_default_verify_paths().cafile
    if not default_ca or not os.path.isfile(default_ca):
        pytest.skip("no system CA file available")
    with pytest.raises(ValueError, match="sslcrl"):
        parse_async_database_url(
            "postgresql://ibex:ibex@db.example:5432/ibex"
            f"?sslmode=verify-full&sslrootcert={default_ca}&sslcrl={default_ca}"
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost/ibex?sslcrl=/tmp/ibex-test.crl",
        "postgresql://u:p@localhost/ibex?sslmode=disable&sslcrl=/tmp/ibex-test.crl",
        "postgresql://u:p@localhost/ibex?sslmode=allow&sslcrl=/tmp/ibex-test.crl",
        "postgresql://u:p@localhost/ibex?sslmode=prefer&sslcrl=/tmp/ibex-test.crl",
    ],
)
def test_sslcrl_rejected_for_non_verified_ssl_modes(url: str) -> None:
    with pytest.raises(ValueError, match="sslcrl"):
        parse_async_database_url(url)
