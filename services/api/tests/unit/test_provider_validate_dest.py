"""Unit tests for provider_validate_dest / provider_validate_net helpers."""

from __future__ import annotations

import ipaddress
import socket
from unittest.mock import AsyncMock, patch

import pytest
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError
from app.services.provider_validate_dest import _assert_self_hosted_destination
from app.services.provider_validate_net import (
    ProbeDial,
    assert_public_resolved_host,
    resolved_addrs,
    url_for_dial,
)


@pytest.mark.asyncio
async def test_dest_self_hosted_rejects_non_http_scheme() -> None:
    with pytest.raises(ApiError) as exc:
        await _assert_self_hosted_destination("ftp", "127.0.0.1")
    assert exc.value.code == INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_dest_public_literal_ip_allowed() -> None:
    dial = await assert_public_resolved_host("8.8.8.8")
    assert dial == ProbeDial(server_name="8.8.8.8", connect_ip="8.8.8.8")


@pytest.mark.asyncio
async def test_url_for_dial_rewrites_host_and_ipv6() -> None:
    pinned = url_for_dial(
        "https://llm.example.com:8443/v1/models",
        ProbeDial(server_name="llm.example.com", connect_ip="8.8.4.4"),
    )
    assert pinned == "https://8.8.4.4:8443/v1/models"
    v6 = url_for_dial(
        "https://llm.example.com/v1/models",
        ProbeDial(server_name="llm.example.com", connect_ip="2001:db8::1"),
    )
    assert v6 == "https://[2001:db8::1]/v1/models"
    unchanged = url_for_dial(
        "https://api.openai.com/v1/models",
        ProbeDial(server_name="api.openai.com", connect_ip=None),
    )
    assert unchanged == "https://api.openai.com/v1/models"


@pytest.mark.asyncio
async def test_dest_resolved_addrs_gaierror() -> None:
    with patch(
        "app.services.provider_validate_net.socket.getaddrinfo",
        side_effect=socket.gaierror(1, "fail"),
    ):
        assert await resolved_addrs("missing.example") == []


@pytest.mark.asyncio
async def test_dest_resolved_addrs_skips_bad_entries() -> None:
    with patch(
        "app.services.provider_validate_net.socket.getaddrinfo",
        return_value=[
            (0, 0, 0, "", ("8.8.4.4", 0)),
            (0, 0, 0, "", ()),
            (0, 0, 0, "", ("not-an-ip", 0)),
        ],
    ):
        addrs = await resolved_addrs("ok.example")
    assert addrs == [ipaddress.ip_address("8.8.4.4")]


@pytest.mark.asyncio
async def test_dest_public_host_with_resolved_addrs() -> None:
    with patch(
        "app.services.provider_validate_net.resolved_addrs",
        new=AsyncMock(return_value=[ipaddress.ip_address("8.8.4.4")]),
    ):
        dial = await assert_public_resolved_host("ok.example")
    assert dial == ProbeDial(server_name="ok.example", connect_ip="8.8.4.4")
