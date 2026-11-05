"""gRPC ContextAssemblyService tests (milestone 3.5.C.6 / ADR-0096)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import grpc
import pytest
from grpc import aio as grpc_aio
from server_test_support import (
    AGENT,
    MODEL,
    ORG,
    SERVICE_TOKEN,
    StubDirective,
    StubHits,
    StubMemory,
    foreign_hit,
    principal_class,
    principal_message,
)
from server_test_support import (
    assembler as _assembler,
)
from server_test_support import (
    settings as _settings,
)

from app.assemble import AssemblyOptions, ContextAssembler
from app.config import MAX_ASSEMBLY_OPTION_MEMORIES
from app.grpc_auth import SERVICE_TOKEN_METADATA_KEY, UNAUTHENTICATED_DETAILS
from app.retrieval import ParallelRetriever
from app.server import (
    _SERVICE_NAME,
    PRINCIPAL_INVALID_DETAILS,
    PRINCIPAL_REQUIRED_DETAILS,
    SELECTOR_MISMATCH_DETAILS,
    ContextAssemblyServicer,
    _options_from_proto,
    build_server,
)

ORG_B = uuid4()
AGENT_B = uuid4()


class _SlowAssembler(ContextAssembler):
    """Assembler that sleeps long enough to trip a short client deadline."""

    async def assemble(self, request):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.2)
        return await super().assemble(request)


@pytest.fixture
def pb2():
    from ibex.context.v1 import context_pb2

    return context_pb2


def _metadata(token: str | None = SERVICE_TOKEN) -> tuple[tuple[str, str], ...]:
    if token is None:
        return ()
    return ((SERVICE_TOKEN_METADATA_KEY, token),)


@asynccontextmanager
async def _rpc_channel(assembler: ContextAssembler | None = None, *, token: str = SERVICE_TOKEN):
    server, port = build_server(
        assembler or _assembler(),
        listen_addr="127.0.0.1:0",
        settings=_settings(grpc_service_token=token),
    )
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            yield channel
    finally:
        await server.stop(grace=None)


@dataclass(frozen=True, slots=True)
class _Codec:
    request: object
    response: object


def _unary_stub(channel, method: str, codec: _Codec):  # type: ignore[no-untyped-def]
    return channel.unary_unary(
        f"/{_SERVICE_NAME}/{method}",
        request_serializer=codec.request.SerializeToString,
        response_deserializer=codec.response.FromString,
    )


def _assemble_codec(pb2) -> _Codec:  # type: ignore[no-untyped-def]
    return _Codec(pb2.AssembleContextRequest, pb2.AssembleContextResponse)


def _assemble_req(
    pb2,  # type: ignore[no-untyped-def]
    *,
    selectors: tuple[str, str] | None = None,
    principal: object | None = None,
    **fields: object,
):
    org_id, agent_id = selectors or (str(ORG), str(AGENT))
    payload: dict[str, object] = {
        "org_id": org_id,
        "agent_id": agent_id,
        "model": MODEL,
        "principal_context": principal or principal_message(),
    }
    payload.update(fields)
    return pb2.AssembleContextRequest(**payload)


async def _rpc_raises(
    call: Callable[[], Awaitable[object]],
) -> grpc.aio.AioRpcError:
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await call()
    return exc_info.value


async def _assemble_error(pb2, req: object, metadata) -> grpc.aio.AioRpcError:  # type: ignore[no-untyped-def]
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))

        async def _call() -> object:
            return await stub(req, timeout=2.0, metadata=metadata)

        return await _rpc_raises(_call)


async def _assert_assemble_invalid(pb2, **fields: object) -> None:
    err = await _assemble_error(pb2, _assemble_req(pb2, **fields), _metadata())
    assert err.code() == grpc.StatusCode.INVALID_ARGUMENT


class _AbortCtx:
    def __init__(self, *, cancelled: bool = False, metadata: object = None) -> None:
        self._cancelled = cancelled
        self._metadata = _metadata() if metadata is None else metadata
        self.aborts: list[tuple[object, str]] = []

    def cancelled(self) -> bool:
        return self._cancelled

    def invocation_metadata(self):  # type: ignore[no-untyped-def]
        return self._metadata

    async def abort(self, code, details):  # type: ignore[no-untyped-def]
        self.aborts.append((code, details))
        raise grpc.aio.AioRpcError(code, details=details)


@pytest.mark.asyncio
async def test_assemble_context_rpc_l0(pb2) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        resp = await stub(
            _assemble_req(
                pb2,
                query="theme",
                recent_messages=[pb2.Message(role="user", content="hello")],
            ),
            timeout=2.0,
            metadata=_metadata(),
        )
        assert resp.assembled_context
        assert resp.memories_included >= 1
        assert resp.metrics.candidates_evaluated >= 1
        assert resp.metrics.total_ms >= 0


@pytest.mark.asyncio
async def test_assemble_rpc_deadline_ms_decouples_from_timeout_ms(pb2) -> None:
    """S2: retrieval wall is deadline_ms (40), not timeout_ms (100), on the RPC path.

    Cold sleeps far longer than either budget. ParallelRetriever must cancel at
    retrieval_wall_ms=40 so AssembleContext returns with cold outer_deadline
    latency of 40ms in metrics — not waiting the historical timeout_ms budget.
    timeout_ms is set well above 45 so a mistaken timeout-only wall would show
    ~100ms in cold_memory_retrieval_ms and wall-clock.
    """
    settings = _settings(
        timeout_ms=100.0,
        deadline_ms=40.0,
        directive_timeout_ms=20.0,
        hot_timeout_ms=20.0,
        cold_timeout_ms=500.0,
    )
    assembler = _assembler(
        settings_obj=settings,
        memory=StubMemory(hot_delay_s=0.0, cold_delay_s=0.5),
    )
    async with _rpc_channel(assembler) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            query="theme",
            recent_messages=[pb2.Message(role="user", content="hello")],
        )
        started = time.perf_counter()
        resp = await stub(req, timeout=2.0, metadata=_metadata())
        elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert resp.assembled_context
    assert "cold fact" not in resp.assembled_context
    # Outer-deadline BranchOutcome records retrieval_wall_ms (== deadline_ms).
    assert resp.metrics.cold_memory_retrieval_ms == 40
    # Must return near the 40ms wall, not the 100ms timeout_ms budget.
    assert 30.0 <= elapsed_ms < 70.0
    assert resp.metrics.total_ms < 80


@pytest.mark.asyncio
async def test_assemble_context_l3_deadline_exceeded(pb2) -> None:
    settings = _settings()
    assembler = _SlowAssembler(
        settings=settings,
        retriever=ParallelRetriever(
            settings=settings,
            memory=StubMemory(),  # type: ignore[arg-type]
            directive=StubDirective(),
        ),
    )
    async with _rpc_channel(assembler) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            query="theme",
            recent_messages=[pb2.Message(role="user", content="hello")],
        )

        async def _call() -> object:
            return await stub(req, timeout=0.05, metadata=_metadata())

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_assemble_rpc_without_service_token_is_unauthenticated(pb2) -> None:
    err = await _assemble_error(pb2, _assemble_req(pb2), _metadata(None))
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == UNAUTHENTICATED_DETAILS


@pytest.mark.asyncio
async def test_assemble_rpc_with_wrong_service_token_is_unauthenticated(pb2) -> None:
    wrong = "context-test-service-token-fedcba9876543210"
    err = await _assemble_error(pb2, _assemble_req(pb2), _metadata(wrong))
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert SERVICE_TOKEN not in (err.details() or "")
    assert wrong not in (err.details() or "")


@pytest.mark.asyncio
async def test_assemble_rpc_without_principal_is_unauthenticated(pb2) -> None:
    req = _assemble_req(pb2)
    req.ClearField("principal_context")
    err = await _assemble_error(pb2, req, _metadata())
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == PRINCIPAL_REQUIRED_DETAILS


@pytest.mark.asyncio
async def test_assemble_rpc_with_empty_principal_is_unauthenticated(pb2) -> None:
    req = _assemble_req(pb2)
    req.principal_context.CopyFrom(principal_class()())
    err = await _assemble_error(pb2, req, _metadata())
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == PRINCIPAL_INVALID_DETAILS


@pytest.mark.asyncio
async def test_assemble_rpc_with_wrong_authority_is_unauthenticated(pb2) -> None:
    principal = principal_message(authority="Client")
    err = await _assemble_error(pb2, _assemble_req(pb2, principal=principal), _metadata())
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == PRINCIPAL_INVALID_DETAILS


@pytest.mark.asyncio
async def test_assemble_rpc_with_stale_principal_is_unauthenticated(pb2) -> None:
    principal = principal_message(issued_at=time.time() - 120.0)
    err = await _assemble_error(pb2, _assemble_req(pb2, principal=principal), _metadata())
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert err.details() == PRINCIPAL_INVALID_DETAILS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selectors",
    [
        (str(ORG_B), str(AGENT)),
        (str(ORG), str(AGENT_B)),
        (str(ORG_B), str(AGENT_B)),
        ("", str(AGENT)),
        ("not-a-uuid", str(AGENT)),
    ],
)
async def test_assemble_denies_selector_mismatch(pb2, selectors) -> None:
    err = await _assemble_error(pb2, _assemble_req(pb2, selectors=selectors), _metadata())
    assert err.code() == grpc.StatusCode.PERMISSION_DENIED
    assert err.details() == SELECTOR_MISMATCH_DETAILS


@pytest.mark.asyncio
async def test_assemble_denies_cross_tenant_selector_without_retrieval(pb2) -> None:
    """Proof (ADR-0096): org-B selectors under an org-A principal never reach I/O.

    The directive lookup is the first thing that would build a tenant-scoped
    Redis key from the selectors, so zero calls is the security assertion.
    """
    directive = StubDirective()
    memory = StubMemory()
    async with _rpc_channel(_assembler(memory=memory, directive=directive)) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))

        async def _call() -> object:
            return await stub(
                _assemble_req(pb2, selectors=(str(ORG_B), str(AGENT_B))),
                timeout=2.0,
                metadata=_metadata(),
            )

        err = await _rpc_raises(_call)

    assert err.code() == grpc.StatusCode.PERMISSION_DENIED
    assert err.details() == SELECTOR_MISMATCH_DETAILS
    assert directive.calls == []
    assert memory.hot_calls == 0
    assert memory.cold_calls == 0


@pytest.mark.asyncio
async def test_foreign_memory_hits_are_never_packed(pb2) -> None:
    """Proof (ADR-0096 H2): a hit from another tenant fails its branch."""
    memory = StubMemory(hits=StubHits(hot=[foreign_hit()], cold=[foreign_hit()]))
    async with _rpc_channel(_assembler(memory=memory)) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        resp = await stub(_assemble_req(pb2, query="theme"), timeout=2.0, metadata=_metadata())

    assert resp.memories_included == 0
    assert resp.memory_tokens == 0
    assert resp.metrics.candidates_evaluated == 0
    assert "foreign tenant secret" not in resp.assembled_context
    assert list(resp.memories_used) == []


@pytest.mark.asyncio
async def test_foreign_hot_hit_does_not_block_healthy_cold_branch(pb2) -> None:
    memory = StubMemory(hits=StubHits(hot=[foreign_hit()]))
    async with _rpc_channel(_assembler(memory=memory)) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        resp = await stub(_assemble_req(pb2, query="theme"), timeout=2.0, metadata=_metadata())

    assert "cold fact" in resp.assembled_context
    assert "foreign tenant secret" not in resp.assembled_context
    assert resp.memories_included == 1


@pytest.mark.asyncio
async def test_assemble_uses_principal_identity_for_retrieval(pb2) -> None:
    directive = StubDirective()
    async with _rpc_channel(_assembler(directive=directive)) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        await stub(_assemble_req(pb2, query="theme"), timeout=2.0, metadata=_metadata())

    assert directive.calls == [(ORG, AGENT)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "codec_factory", "request_factory"),
    [
        (
            "SearchMemories",
            lambda pb2: _Codec(pb2.SearchMemoriesRequest, pb2.SearchMemoriesResponse),
            lambda pb2: pb2.SearchMemoriesRequest(org_id=str(ORG), agent_id=str(AGENT)),
        ),
        (
            "RecordMemoryFeedback",
            lambda pb2: _Codec(
                pb2.RecordMemoryFeedbackRequest,
                pb2.RecordMemoryFeedbackResponse,
            ),
            lambda pb2: pb2.RecordMemoryFeedbackRequest(
                org_id=str(ORG),
                memory_ids=[str(uuid4())],
                feedback="positive",
            ),
        ),
    ],
)
async def test_unimplemented_rpcs(pb2, method, codec_factory, request_factory) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, method, codec_factory(pb2))
        req = request_factory(pb2)

        async def _call() -> object:
            return await stub(req, metadata=_metadata())

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "codec_factory", "request_factory"),
    [
        (
            "SearchMemories",
            lambda pb2: _Codec(pb2.SearchMemoriesRequest, pb2.SearchMemoriesResponse),
            lambda pb2: pb2.SearchMemoriesRequest(),
        ),
        (
            "RecordMemoryFeedback",
            lambda pb2: _Codec(
                pb2.RecordMemoryFeedbackRequest,
                pb2.RecordMemoryFeedbackResponse,
            ),
            lambda pb2: pb2.RecordMemoryFeedbackRequest(),
        ),
    ],
)
async def test_stub_rpcs_require_the_service_token(
    pb2,
    method,
    codec_factory,
    request_factory,
) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, method, codec_factory(pb2))

        async def _call() -> object:
            return await stub(request_factory(pb2), metadata=())

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields_factory",
    [
        lambda pb2: {"model": ""},
        lambda pb2: {"query": "x" * 9000},
        lambda pb2: {"options": pb2.AssemblyOptions(max_memories=-1)},
        lambda pb2: {
            "options": pb2.AssemblyOptions(
                max_memories=MAX_ASSEMBLY_OPTION_MEMORIES + 1
            )
        },
        lambda pb2: {
            "recent_messages": [
                pb2.Message(role="user", content="hi") for _ in range(101)
            ]
        },
        lambda pb2: {
            "recent_messages": [pb2.Message(role="user", content="y" * 40_000)]
        },
        lambda pb2: {"model": "m" * 300},
        lambda pb2: {
            "recent_messages": [pb2.Message(role="r" * 80, content="hi")]
        },
        lambda pb2: {"request_id": "not-a-uuid"},
        lambda pb2: {"trace_id": "zzzz"},
        lambda pb2: {"available_tokens": -1},
        lambda pb2: {"available_tokens": 10_000_001},
        lambda pb2: {"trace_id": "0" * 32},
        lambda pb2: {"span_id": "abcd"},
        lambda pb2: {"span_id": "0" * 16},
        lambda pb2: {"session_id": "not-a-uuid"},
        lambda pb2: {"directive_version_id": "bad"},
    ],
)
async def test_assemble_rejects_invalid_argument(pb2, fields_factory) -> None:
    await _assert_assemble_invalid(pb2, **fields_factory(pb2))


def test_options_from_proto_bounds_max_memories(pb2) -> None:
    ok = _options_from_proto(pb2.AssemblyOptions(max_memories=10))
    assert ok.max_memories == 10
    negative = pb2.AssemblyOptions(max_memories=-1)
    with pytest.raises(ValueError, match="max_memories"):
        _options_from_proto(negative)
    too_large = pb2.AssemblyOptions(max_memories=MAX_ASSEMBLY_OPTION_MEMORIES + 1)
    with pytest.raises(ValueError, match="max_memories"):
        _options_from_proto(too_large)


def test_options_from_proto_defaults_when_absent() -> None:
    assert _options_from_proto(None) == AssemblyOptions()


def test_servicer_requires_a_service_token() -> None:
    with pytest.raises(ValueError, match="IBEX_CONTEXT_GRPC_SERVICE_TOKEN"):
        ContextAssemblyServicer(_assembler(), service_token="")


@pytest.mark.asyncio
async def test_servicer_direct_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler(), service_token=SERVICE_TOKEN)
    ctx = _AbortCtx()

    resp = await servicer.assemble_context(
        _assemble_req(
            pb2,
            query="q",
            recent_messages=[pb2.Message(role="user", content="hi")],
        ),
        ctx,  # type: ignore[arg-type]
    )
    assert resp.assembled_context
    assert ctx.aborts == []


@pytest.mark.asyncio
async def test_servicer_direct_call_without_token_cannot_bypass(pb2) -> None:
    """H12: constructing the servicer directly must not skip caller auth."""
    servicer = ContextAssemblyServicer(_assembler(), service_token=SERVICE_TOKEN)
    ctx = _AbortCtx(metadata=())

    async def _call() -> object:
        return await servicer.assemble_context(
            _assemble_req(pb2, query="q"),
            ctx,  # type: ignore[arg-type]
        )

    err = await _rpc_raises(_call)
    assert err.code() == grpc.StatusCode.UNAUTHENTICATED
    assert ctx.aborts[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_servicer_direct_call_rejects_tenant_mismatch(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler(), service_token=SERVICE_TOKEN)
    ctx = _AbortCtx()

    async def _call() -> object:
        return await servicer.assemble_context(
            _assemble_req(pb2, selectors=(str(ORG_B), str(AGENT_B))),
            ctx,  # type: ignore[arg-type]
        )

    err = await _rpc_raises(_call)
    assert err.code() == grpc.StatusCode.PERMISSION_DENIED
    assert ctx.aborts[0][0] == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_servicer_cancelled_before_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler(), service_token=SERVICE_TOKEN)
    ctx = _AbortCtx(cancelled=True)

    async def _call() -> object:
        return await servicer.assemble_context(_assemble_req(pb2), ctx)  # type: ignore[arg-type]

    err = await _rpc_raises(_call)
    assert err.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    assert ctx.aborts[0][0] == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_servicer_cancelled_after_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler(), service_token=SERVICE_TOKEN)

    class _FlipCtx(_AbortCtx):
        def __init__(self) -> None:
            super().__init__(cancelled=False)
            self._n = 0

        def cancelled(self) -> bool:
            self._n += 1
            return self._n > 1

    ctx = _FlipCtx()

    async def _call() -> object:
        return await servicer.assemble_context(
            _assemble_req(pb2, query="q"),
            ctx,  # type: ignore[arg-type]
        )

    err = await _rpc_raises(_call)
    assert err.code() == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_servicer_assemble_cancelled_error(pb2) -> None:
    class _CancelAssembler(ContextAssembler):
        async def assemble(self, request):  # type: ignore[no-untyped-def]
            raise asyncio.CancelledError()

    class _SilentCtx(_AbortCtx):
        """Records aborts without raising, so CancelledError propagates."""

        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            self.aborts.append((code, details))

    settings = _settings()
    servicer = ContextAssemblyServicer(
        _CancelAssembler(
            settings=settings,
            retriever=ParallelRetriever(
                settings=settings,
                memory=StubMemory(),  # type: ignore[arg-type]
                directive=StubDirective(),
            ),
        ),
        service_token=SERVICE_TOKEN,
    )
    ctx = _SilentCtx()
    req = _assemble_req(pb2)
    with pytest.raises(asyncio.CancelledError):
        await servicer.assemble_context(req, ctx)  # type: ignore[arg-type]
    assert ctx.aborts == [(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")]
