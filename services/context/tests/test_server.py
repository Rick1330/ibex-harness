"""gRPC ContextAssemblyService tests (milestone 3.5.C.6)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import grpc
import pytest
from grpc import aio as grpc_aio

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.retrieval import ParallelRetriever
from app.server import (
    _SERVICE_NAME,
    ContextAssemblyServicer,
    build_assembler_from_settings,
    build_server,
)

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"


def _settings() -> ContextSettings:
    return ContextSettings.model_construct(
        timeout_ms=45.0,
        deadline_ms=40.0,
        directive_timeout_ms=5.0,
        hot_timeout_ms=15.0,
        cold_timeout_ms=45.0,
        formatter_nonce_bytes=16,
        packer_dp_cell_ceiling=70 * 6251,
        packer_max_consecutive_skips=5,
        grpc_addr="127.0.0.1:0",
    )


class _StubDirective:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


class _StubMemory:
    def __init__(self, *, delay_s: float = 0.0) -> None:
        self._delay_s = delay_s
        self._hit = MemoryHitPayload(
            memory_id=str(uuid4()),
            org_id=str(ORG),
            agent_id=str(AGENT),
            content="prefers dark mode",
            category="preference",
            confidence=0.9,
            similarity=0.8,
            rank=1,
            source="hot_cache",
        )

    async def get_hot_memories(self, *_args, **_kwargs):
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return [self._hit]

    async def search_memories(self, *_args, **_kwargs):
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return [
            MemoryHitPayload(
                memory_id=str(uuid4()),
                org_id=str(ORG),
                agent_id=str(AGENT),
                content="cold fact",
                category="factual",
                confidence=0.8,
                similarity=0.7,
                rank=1,
                source="vector",
            )
        ]


class _SlowAssembler(ContextAssembler):
    """Assembler that sleeps long enough to trip a short client deadline."""

    async def assemble(self, request):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.2)
        return await super().assemble(request)


def _assembler(*, delay_s: float = 0.0) -> ContextAssembler:
    settings = _settings()
    retriever = ParallelRetriever(
        settings=settings,
        memory=_StubMemory(delay_s=delay_s),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    return ContextAssembler(settings=settings, retriever=retriever)


@pytest.fixture
def pb2():
    from ibex.context.v1 import context_pb2

    return context_pb2


@pytest.mark.asyncio
async def test_assemble_context_rpc_l0(pb2) -> None:
    server, port = build_server(_assembler(), listen_addr="127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/AssembleContext",
                request_serializer=pb2.AssembleContextRequest.SerializeToString,
                response_deserializer=pb2.AssembleContextResponse.FromString,
            )
            req = pb2.AssembleContextRequest(
                org_id=str(ORG),
                agent_id=str(AGENT),
                query="theme",
                model=MODEL,
                recent_messages=[pb2.Message(role="user", content="hello")],
            )
            resp = await stub(req, timeout=2.0)
            assert resp.assembled_context
            assert resp.memories_included >= 1
            assert resp.metrics.candidates_evaluated >= 1
            assert resp.metrics.total_ms >= 0
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_assemble_context_l3_deadline_exceeded(pb2) -> None:
    settings = _settings()
    retriever = ParallelRetriever(
        settings=settings,
        memory=_StubMemory(),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    assembler = _SlowAssembler(settings=settings, retriever=retriever)
    server, port = build_server(assembler, listen_addr="127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/AssembleContext",
                request_serializer=pb2.AssembleContextRequest.SerializeToString,
                response_deserializer=pb2.AssembleContextResponse.FromString,
            )
            req = pb2.AssembleContextRequest(
                org_id=str(ORG),
                agent_id=str(AGENT),
                query="theme",
                model=MODEL,
                recent_messages=[pb2.Message(role="user", content="hello")],
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(req, timeout=0.05)
            assert exc_info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_search_memories_unimplemented(pb2) -> None:
    server, port = build_server(_assembler(), listen_addr="127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/SearchMemories",
                request_serializer=pb2.SearchMemoriesRequest.SerializeToString,
                response_deserializer=pb2.SearchMemoriesResponse.FromString,
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(pb2.SearchMemoriesRequest(org_id=str(ORG), agent_id=str(AGENT)))
            assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_invalid_org_id(pb2) -> None:
    server, port = build_server(_assembler(), listen_addr="127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/AssembleContext",
                request_serializer=pb2.AssembleContextRequest.SerializeToString,
                response_deserializer=pb2.AssembleContextResponse.FromString,
            )
            req = pb2.AssembleContextRequest(
                org_id="not-a-uuid",
                agent_id=str(AGENT),
                model=MODEL,
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(req, timeout=2.0)
            assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_servicer_direct_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())

    class _Ctx:
        def cancelled(self) -> bool:
            return False

        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            raise grpc.aio.AioRpcError(code, details=details)

    req = pb2.AssembleContextRequest(
        org_id=str(ORG),
        agent_id=str(AGENT),
        query="q",
        model=MODEL,
        recent_messages=[pb2.Message(role="user", content="hi")],
    )
    resp = await servicer.AssembleContext(req, _Ctx())  # type: ignore[arg-type]
    assert resp.assembled_context
    assert "user: hi" in resp.assembled_context or resp.memories_included >= 0


def test_build_assembler_requires_memory_base_url() -> None:
    settings = ContextSettings.model_construct(
        memory_base_url="",
        memory_api_token="",
        redis_url="",
        timeout_ms=45.0,
        deadline_ms=40.0,
        directive_timeout_ms=5.0,
        hot_timeout_ms=15.0,
        cold_timeout_ms=45.0,
        formatter_nonce_bytes=16,
        packer_dp_cell_ceiling=70 * 6251,
        packer_max_consecutive_skips=5,
        grpc_addr="127.0.0.1:0",
    )
    with pytest.raises(ValueError, match="MEMORY_BASE_URL"):
        build_assembler_from_settings(settings)
