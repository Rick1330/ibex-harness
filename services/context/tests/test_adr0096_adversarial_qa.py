"""Adversarial QA for the ADR-0096 caller boundary.

These tests attack the boundary instead of confirming it. Each test names the
defect it would catch; none of them weakens a production check.

Run with: ``cd services/context && .venv/bin/pytest -q tests/test_adr0096_adversarial_qa.py``
"""

from __future__ import annotations

import errno
import logging
import socket
from contextlib import asynccontextmanager
from uuid import uuid4

import grpc
import pytest
from grpc import aio as grpc_aio
from pydantic import SecretStr
from server_test_support import (
    AGENT,
    ORG,
    SERVICE_TOKEN,
    StubDirective,
    StubMemory,
    assembler,
    principal_message,
    settings,
)

from app import server as server_mod
from app.grpc_auth import SERVICE_TOKEN_METADATA_KEY, UNAUTHENTICATED_DETAILS
from app.principal import VerifiedPrincipal
from app.retrieval import MEMORY_TENANT_MISMATCH, ParallelRetriever, RetrievalRequest
from app.server import _SERVICE_NAME, ContextAssemblyServicer, _request_from_proto, build_server

_MODEL = "gpt-4o-mini"
_METHODS = ("AssembleContext", "SearchMemories", "RecordMemoryFeedback")


@pytest.fixture
def pb2():
    from ibex.context.v1 import context_pb2

    return context_pb2


class _RejectCtx:
    """Minimal servicer context that records the abort instead of raising."""

    def __init__(self, *, metadata: object = ()) -> None:
        self._metadata = metadata
        self.aborts: list[tuple[object, str]] = []

    def invocation_metadata(self):  # type: ignore[no-untyped-def]
        return self._metadata

    def cancelled(self) -> bool:
        return False

    async def abort(self, code, details):  # type: ignore[no-untyped-def]
        self.aborts.append((code, details))
        raise grpc.aio.AioRpcError(code, details=details)


@asynccontextmanager
async def _channel(*, memory: object | None = None, directive: object | None = None):
    server, port = build_server(
        assembler(memory=memory, directive=directive),  # type: ignore[arg-type]
        listen_addr="127.0.0.1:0",
        settings=settings(),
    )
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            yield channel
    finally:
        await server.stop(grace=None)


def _assemble_stub(channel, pb2):  # type: ignore[no-untyped-def]
    return channel.unary_unary(
        f"/{_SERVICE_NAME}/AssembleContext",
        request_serializer=pb2.AssembleContextRequest.SerializeToString,
        response_deserializer=pb2.AssembleContextResponse.FromString,
    )


def _assemble_request(pb2, *, selectors=None, principal=None, **fields):  # type: ignore[no-untyped-def]
    org_id, agent_id = selectors or (str(ORG), str(AGENT))
    payload: dict[str, object] = {
        "org_id": org_id,
        "agent_id": agent_id,
        "model": _MODEL,
        "principal_context": principal if principal is not None else principal_message(),
    }
    payload.update(fields)
    return pb2.AssembleContextRequest(**payload)


async def _assemble_error(pb2, request, metadata) -> grpc.aio.AioRpcError:  # type: ignore[no-untyped-def]
    async with _channel() as channel:
        stub = _assemble_stub(channel, pb2)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub(request, timeout=2.0, metadata=metadata)
    return exc_info.value


# ---------------------------------------------------------------- token guard


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        # Duplicate: valid first, garbage second.
        (
            (SERVICE_TOKEN_METADATA_KEY, SERVICE_TOKEN),
            (SERVICE_TOKEN_METADATA_KEY, "z" * 32),
        ),
        # Duplicate: garbage first, valid second. Order must not matter.
        (
            (SERVICE_TOKEN_METADATA_KEY, "z" * 32),
            (SERVICE_TOKEN_METADATA_KEY, SERVICE_TOKEN),
        ),
        # Same token twice is still a duplicate, not "one valid entry".
        (
            (SERVICE_TOKEN_METADATA_KEY, SERVICE_TOKEN),
            (SERVICE_TOKEN_METADATA_KEY, SERVICE_TOKEN),
        ),
    ],
)
async def test_duplicate_wire_token_entries_are_unauthenticated(
    pb2,
    caplog: pytest.LogCaptureFixture,
    metadata,
) -> None:
    """Catch: a server that merges duplicate gRPC metadata, or keeps only one entry.

    gRPC Python delivers each wire entry separately (verified: a duplicate tuple
    arrives as two ``_Metadatum`` items), so this exercises the real duplicate
    path rather than a fake context. ``reason=duplicate`` (not ``mismatch``) pins
    that the duplicate is detected before any comparison, in both orders.
    """
    directive = StubDirective()
    memory = StubMemory()
    with caplog.at_level(logging.WARNING, logger="app.grpc_auth"):
        async with _channel(memory=memory, directive=directive) as channel:
            stub = _assemble_stub(channel, pb2)
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(_assemble_request(pb2), timeout=2.0, metadata=metadata)

    err = exc_info.value
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == UNAUTHENTICATED_DETAILS
    assert "reason=duplicate" in caplog.text
    assert directive.calls == []
    assert memory.hot_calls == 0
    assert memory.cold_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [513, 4096])
async def test_oversized_wire_token_is_unauthenticated_without_echo(
    pb2,
    caplog: pytest.LogCaptureFixture,
    length: int,
) -> None:
    """Catch: an over-long token reaching ``hmac.compare_digest`` or the logs.

    The bound is checked before the compare, and neither the configured value nor
    the presented value may appear in the rejection log or the error details.
    """
    presented = "q" * length
    with caplog.at_level(logging.WARNING, logger="app.grpc_auth"):
        err = await _assemble_error(
            pb2,
            _assemble_request(pb2),
            ((SERVICE_TOKEN_METADATA_KEY, presented),),
        )
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == UNAUTHENTICATED_DETAILS
    assert SERVICE_TOKEN not in (err.details() or "")
    assert presented not in (err.details() or "")
    assert SERVICE_TOKEN not in caplog.text
    assert presented not in caplog.text


@pytest.mark.asyncio
async def test_missing_wire_token_never_reaches_the_assembler(pb2) -> None:
    """Catch: a handler that authenticates after doing retrieval work."""
    directive = StubDirective()
    memory = StubMemory()
    async with _channel(memory=memory, directive=directive) as channel:
        stub = _assemble_stub(channel, pb2)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub(_assemble_request(pb2), timeout=2.0, metadata=())
    assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert directive.calls == []
    assert memory.hot_calls == 0


@pytest.mark.asyncio
async def test_every_registered_method_runs_the_guard_before_its_body(pb2) -> None:
    """Catch: a future RPC registered in ``_generic_handler`` without the guard.

    Introspects the real registration map: adding a fourth method without
    ``guard_handler`` fails the set assertion, and every registered behaviour
    must abort UNAUTHENTICATED on empty metadata before any downstream work.
    """
    servicer = ContextAssemblyServicer(assembler(), service_token=SERVICE_TOKEN)
    generic = server_mod._generic_handler(servicer, pb2, SERVICE_TOKEN)
    handlers = generic._method_handlers
    expected = {f"/{_SERVICE_NAME}/{name}" for name in _METHODS}
    assert set(handlers) == expected

    for name, handler in handlers.items():
        ctx = _RejectCtx(metadata=())
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await handler.unary_unary(handler.request_deserializer(b""), ctx)
        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED, name
        assert ctx.aborts == [(grpc.StatusCode.UNAUTHENTICATED, UNAUTHENTICATED_DETAILS)]


# ------------------------------------------------------------------ principal


def _metadata(token: str = SERVICE_TOKEN) -> tuple[tuple[str, str], ...]:
    return ((SERVICE_TOKEN_METADATA_KEY, token),)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authority",
    [" AuthService", "\tAuthService", "AUTHSERVICE", "AuthService\n"],
)
async def test_non_exact_authority_is_unauthenticated(pb2, authority: str) -> None:
    """Catch: a normalising authority check (case fold / strip)."""
    principal = principal_message(authority=authority)
    err = await _assemble_error(pb2, _assemble_request(pb2, principal=principal), _metadata())
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == server_mod.PRINCIPAL_INVALID_DETAILS


# ------------------------------------------------------------ selector binding


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selectors",
    [
        (" " + str(ORG), str(AGENT)),
        (str(ORG) + " ", str(AGENT)),
        (str(ORG).upper(), str(AGENT)),
        (str(ORG), " " + str(AGENT)),
        (str(ORG), str(AGENT).upper()),
        ("urn:uuid:" + str(ORG), str(AGENT)),
    ],
)
async def test_padded_or_non_canonical_selectors_are_permission_denied(
    pb2,
    selectors: tuple[str, str],
) -> None:
    """Catch: an equality check that trims/casefolds or parses the selector UUID."""
    directive = StubDirective()
    memory = StubMemory()
    async with _channel(memory=memory, directive=directive) as channel:
        stub = _assemble_stub(channel, pb2)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub(
                _assemble_request(pb2, selectors=selectors),
                timeout=2.0,
                metadata=_metadata(),
            )
    err = exc_info.value
    assert err.code() == grpc.StatusCode.PERMISSION_DENIED
    assert err.details() == server_mod.SELECTOR_MISMATCH_DETAILS
    assert directive.calls == []
    assert memory.hot_calls == 0
    assert memory.cold_calls == 0


def test_domain_request_is_built_from_the_principal_not_the_selectors(pb2) -> None:
    """Catch: a directive key derived from ``request.org_id`` rather than the principal.

    ``bind_selectors`` makes the two indistinguishable over the wire, so this
    calls the mapper directly with deliberately foreign selectors. If
    ``_request_from_proto`` ever reads the selectors, the domain request carries
    the attacker's tenant and this test fails.
    """
    foreign_org, foreign_agent = uuid4(), uuid4()
    request = pb2.AssembleContextRequest(
        org_id=str(foreign_org),
        agent_id=str(foreign_agent),
        model=_MODEL,
    )
    domain = _request_from_proto(request, VerifiedPrincipal(org_id=ORG, agent_id=AGENT))
    assert domain.org_id == ORG
    assert domain.agent_id == AGENT
    assert domain.org_id != foreign_org
    assert domain.agent_id != foreign_agent


# ------------------------------------------------------- memory-hit validation


def _retrieval_request() -> RetrievalRequest:
    return RetrievalRequest(org_id=ORG, agent_id=AGENT, query="q", model=_MODEL, recent_messages=[])


def _json_hit(*, org_id: str, agent_id: str, content: str) -> dict[str, object]:
    """One hit in the real POST /v1/memories/search response shape."""
    return {
        "memory": {
            "id": str(uuid4()),
            "agent_id": agent_id,
            "org_id": org_id,
            "content": content,
            "category": "factual",
            "confidence": 0.9,
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        "similarity": 0.9,
        "rank": 1,
        "source": "hot_cache",
    }


def _memory_from_json(hot: list[dict[str, object]], cold: list[dict[str, object]]):
    import httpx

    from app.clients.memory import MemoryHttpClient, MemoryHttpConfig

    def _handler(request: httpx.Request) -> httpx.Response:
        results = hot if request.url.path == "/v1/memories/hot" else cold
        return httpx.Response(200, json={"data": {"results": results}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    memory = MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.test", token="memory-token"),
        http_client,
    )
    return memory, http_client


async def _retrieve_over_http(hot: list[dict[str, object]], cold: list[dict[str, object]]):
    memory, http_client = _memory_from_json(hot, cold)
    retriever = ParallelRetriever(settings=settings(), memory=memory, directive=StubDirective())
    async with http_client:
        return await retriever.retrieve(_retrieval_request())


@pytest.mark.asyncio
async def test_foreign_hit_inside_a_real_memory_response_is_never_packed() -> None:
    """Catch: validation that only covers the stub payload shape, not the wire JSON.

    A foreign hit arrives first, so a parser/validator that keeps the first hit or
    that trusts the response wholesale would pack it into the model prompt.
    """
    hot = [
        _json_hit(org_id=str(uuid4()), agent_id=str(AGENT), content="foreign tenant secret"),
        _json_hit(org_id=str(ORG), agent_id=str(AGENT), content="legit"),
    ]
    cold = [_json_hit(org_id=str(ORG), agent_id=str(AGENT), content="legit cold")]
    result = await _retrieve_over_http(hot, cold)

    assert result.hot_outcome.status == "error"
    assert result.hot_outcome.detail == MEMORY_TENANT_MISMATCH
    assert result.hot_memories == []
    contents = [hit.content for hit in (*result.hot_memories, *result.cold_memories)]
    assert "foreign tenant secret" not in contents
    assert result.cold_outcome.status == "success"


@pytest.mark.asyncio
async def test_empty_org_in_a_real_memory_response_fails_the_branch() -> None:
    """Catch: an empty tenant field treated as "unknown" and packed anyway."""
    hot = [_json_hit(org_id="", agent_id=str(AGENT), content="ambiguous tenant")]
    cold = [_json_hit(org_id=str(ORG), agent_id=str(AGENT), content="legit cold")]
    result = await _retrieve_over_http(hot, cold)

    assert result.hot_outcome.status == "error"
    assert result.hot_memories == []
    assert "ambiguous tenant" not in str(
        [hit.content for hit in (*result.hot_memories, *result.cold_memories)]
    )


@pytest.mark.asyncio
async def test_non_canonical_hit_tenant_for_the_same_principal_is_accepted() -> None:
    """Catch: a validator that compares raw UUID text and drops same-tenant hits.

    The HTTP client canonicalises ``memory.org_id``/``agent_id``, so an uppercase
    spelling of the principal's own UUID must not be rejected; a *foreign* value
    (previous test) must still be. This pins the normalisation boundary.
    """
    hot = [
        _json_hit(
            org_id=str(ORG).upper(),
            agent_id=str(AGENT).upper(),
            content="same tenant",
        )
    ]
    result = await _retrieve_over_http(hot, [])

    assert result.hot_outcome.status == "success"
    assert [hit.content for hit in result.hot_memories] == ["same tenant"]


def _hit(*, org_id: object = ORG, agent_id: object = AGENT, content: str = "legit") -> object:
    from app.clients.memory import MemoryHitPayload

    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(org_id),
        agent_id=str(agent_id),
        content=content,
        category="factual",
        confidence=0.9,
        similarity=0.9,
        rank=1,
        source="hot_cache",
    )


class _Memory:
    def __init__(self, *, hot: list[object], cold: list[object]) -> None:
        self._hot = hot
        self._cold = cold

    async def get_hot_memories(self, *_args, **_kwargs):
        return self._hot

    async def search_memories(self, *_args, **_kwargs):
        return self._cold


async def _retrieve(hot: list[object], cold: list[object]):
    retriever = ParallelRetriever(
        settings=settings(),
        memory=_Memory(hot=hot, cold=cold),  # type: ignore[arg-type]
        directive=StubDirective(),
    )
    return await retriever.retrieve(_retrieval_request())


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", ["hot", "cold"])
async def test_foreign_hit_first_still_rejects_the_whole_branch(branch: str) -> None:
    """Catch: a validator that inspects only the last (or first) hit.

    The legitimate hit comes second in hot and first in cold, so a
    "check hits[-1]" or "check hits[0]" implementation leaves one case green and
    the other leaking.
    """
    foreign = _hit(org_id=uuid4(), content="foreign tenant secret")
    legit = _hit(content="legit")
    hot = [foreign, legit] if branch == "hot" else [legit]
    cold = [foreign, legit] if branch == "cold" else [legit]
    result = await _retrieve(hot, cold)

    outcome = result.hot_outcome if branch == "hot" else result.cold_outcome
    packed = result.hot_memories if branch == "hot" else result.cold_memories
    assert outcome.status == "error"
    assert outcome.detail == MEMORY_TENANT_MISMATCH
    assert packed == []
    assert branch not in result.sources_available
    contents = [
        hit.content for hit in (*result.hot_memories, *result.cold_memories)
    ]
    assert "foreign tenant secret" not in contents


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("org_id", "agent_id"),
    [("", AGENT), (ORG, ""), ("", "")],
)
async def test_hit_with_empty_tenant_is_rejected(org_id: object, agent_id: object) -> None:
    """Catch: a validator that treats an empty tenant as "unknown, allow"."""
    result = await _retrieve([_hit(org_id=org_id, agent_id=agent_id)], [_hit()])
    assert result.hot_outcome.status == "error"
    assert result.hot_outcome.detail == MEMORY_TENANT_MISMATCH
    assert result.hot_memories == []
    # The cold branch stays healthy; the failure is scoped, not global.
    assert result.cold_outcome.status == "success"


# ------------------------------------------------------------ port sharing


@pytest.mark.skipif(
    not hasattr(socket, "SO_REUSEPORT"),
    reason="SO_REUSEPORT is not available on this platform",
)
@pytest.mark.asyncio
async def test_real_listener_refuses_a_so_reuseport_peer() -> None:
    """Catch: a dropped/renamed ``grpc.so_reuseport`` option.

    A plain assertion on ``_SERVER_OPTIONS`` still passes if gRPC renames the
    channel arg. This binds a fresh SO_REUSEPORT socket to the live gRPC port:
    the kernel lets two SO_REUSEPORT sockets share a port (positive control),
    so a successful bind here would prove the listener enabled it and that a
    same-UID process could capture the caller token.
    """

    def bind(port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("127.0.0.1", port))
        return sock

    # Positive control: this kernel shares a port between two SO_REUSEPORT binds.
    control = bind(0)
    control.listen(1)
    shared_port = control.getsockname()[1]
    peer = bind(shared_port)
    peer.close()
    control.close()

    server, port = build_server(
        assembler(),
        listen_addr="127.0.0.1:0",
        settings=settings(),
    )
    await server.start()
    try:
        with pytest.raises(OSError) as exc_info:
            bind(port)
        assert exc_info.value.errno == errno.EADDRINUSE
    finally:
        await server.stop(grace=None)


# ------------------------------------------------------- startup fail-closed


@pytest.mark.asyncio
@pytest.mark.parametrize(("length", "accepted"), [(31, False), (32, True), (512, True), (513, False)])
async def test_startup_token_length_boundary(
    monkeypatch: pytest.MonkeyPatch,
    length: int,
    accepted: bool,
) -> None:
    """Catch: an off-by-one in the 32..512 startup bound (either direction)."""
    created: list[int] = []
    real_server = server_mod.grpc_aio.server

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        created.append(1)
        return real_server(*args, **kwargs)

    monkeypatch.setattr(server_mod.grpc_aio, "server", _spy)
    token = "a" * length
    if not accepted:
        with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
            build_server(
                assembler(),
                listen_addr="127.0.0.1:0",
                settings=settings(grpc_service_token=SecretStr(token)),
            )
        assert created == [], "a rejected token must not construct a gRPC server"
        return

    server, port = build_server(
        assembler(),
        listen_addr="127.0.0.1:0",
        settings=settings(grpc_service_token=SecretStr(token)),
    )
    try:
        assert port > 0
        assert created == [1]
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_serve_forever_never_constructs_a_listener_on_token_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch: a refusal that leaves a bound listener behind.

    Spies on ``grpc.aio.server`` itself: a token refusal must fail before any
    server object exists, so no port can be bound and nothing can be shared.
    """
    created: list[int] = []
    monkeypatch.setattr(
        server_mod.grpc_aio,
        "server",
        lambda *args, **kwargs: created.append(1),  # type: ignore[no-untyped-def]
    )
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        await server_mod.serve_forever(
            settings(
                memory_base_url="http://127.0.0.1:1",
                memory_api_token=SecretStr("memory-token"),
                grpc_service_token=SecretStr("too-short"),
                grpc_addr="127.0.0.1:0",
            )
        )
    assert created == []


def test_loopback_guard_resolves_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catch: trusting the literal string ``localhost`` instead of resolution."""

    def _public_localhost(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("203.0.113.7", 0))]

    monkeypatch.setattr(server_mod.socket, "getaddrinfo", _public_localhost)
    with pytest.raises(ValueError, match="loopback"):
        server_mod._require_loopback_bind("localhost:9092")
