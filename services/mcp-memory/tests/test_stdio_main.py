"""Stdio runtime wires ValidateAgent and can serve search_memory."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from app.access_token import set_access_token
from app.agent_verifier import AllowAllAgentVerifier
from app.config import Settings, get_settings
from app.permissions import MEMORY_READ
from app.principal import Principal, set_principal
from app.ratelimit import NoopMcpLimiter
from app.stdio_main import aclose_stdio_runtime, build_stdio_runtime
from tests.memory_fixtures import stub_memory_client

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")
TOKEN = "tok-stdio"


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_stdio_runtime_search_memory_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful search_memory through the same wiring stdio_main uses."""
    mem = stub_memory_client(org_id=ORG, agent_id=AGENT)
    monkeypatch.setattr(
        "app.stdio_main.GRPCAgentVerifier",
        lambda *_a, **_k: AllowAllAgentVerifier(),
    )
    monkeypatch.setattr("app.stdio_main.build_memory_client", lambda **_k: mem)
    monkeypatch.setattr(
        "app.stdio_main.build_mcp_rate_limiter",
        lambda **_k: NoopMcpLimiter(),
    )

    settings = Settings(
        transport="stdio",
        allow_stdio=True,
        env="development",
        auth_grpc_addr="127.0.0.1:9",
        auth_timeout_ms=50,
        memory_http_url="http://memory.test",
        memory_timeout_ms=1000,
        redis_url="",
    )
    runtime = build_stdio_runtime(settings)
    assert runtime.verifier is not None

    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT))
    set_access_token(TOKEN)
    try:
        result = await runtime.mcp.call_tool(  # type: ignore[attr-defined]
            "search_memory",
            {"query": "stdio-ok", "limit": 3},
        )
    finally:
        set_principal(None)
        set_access_token(None)
        await aclose_stdio_runtime(runtime)

    assert result is not None
    assert getattr(result, "isError", False) is False
    if isinstance(result, tuple):
        content_blocks, _structured = result
        text = content_blocks[0].text
    else:
        text = result[0].text  # type: ignore[index]
    payload = json.loads(text)
    assert payload["query"] == "stdio-ok"
    assert payload["limit"] == 3
    assert payload["org_id"] == str(ORG)
    assert payload["agent_id"] == str(AGENT)
    assert payload["results"] == []
