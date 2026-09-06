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


class _AbortCtx:
    def __init__(self, *, cancelled: bool = False) -> None:
        self._cancelled = cancelled
        self.aborts: list[tuple[object, str]] = []

    def cancelled(self) -> bool:
        return self._cancelled

    async def abort(self, code, details):  # type: ignore[no-untyped-def]
        self.aborts.append((code, details))
        raise grpc.aio.AioRpcError(code, details=details)


@pytest.mark.asyncio
async def test_servicer_cancelled_before_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())
    req = pb2.AssembleContextRequest(
        org_id=str(ORG),
        agent_id=str(AGENT),
        model=MODEL,
    )
    ctx = _AbortCtx(cancelled=True)
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await servicer.AssembleContext(req, ctx)  # type: ignore[arg-type]
    assert exc_info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    assert ctx.aborts[0][0] == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_servicer_cancelled_after_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())
    req = pb2.AssembleContextRequest(
        org_id=str(ORG),
        agent_id=str(AGENT),
        query="q",
        model=MODEL,
    )

    class _FlipCtx(_AbortCtx):
        def __init__(self) -> None:
            super().__init__(cancelled=False)
            self._n = 0

        def cancelled(self) -> bool:
            self._n += 1
            # First check (pre-assemble) false; second (post-assemble) true.
            return self._n > 1

    ctx = _FlipCtx()
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await servicer.AssembleContext(req, ctx)  # type: ignore[arg-type]
    assert exc_info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_servicer_assemble_cancelled_error(pb2) -> None:
    class _CancelAssembler(ContextAssembler):
        async def assemble(self, request):  # type: ignore[no-untyped-def]
            raise asyncio.CancelledError()

    class _Ctx:
        def __init__(self) -> None:
            self.aborts: list[object] = []

        def cancelled(self) -> bool:
            return False

        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            self.aborts.append(code)
            # Match grpc abort: set status but do not raise; caller re-raises CancelledError.

    settings = _settings()
    retriever = ParallelRetriever(
        settings=settings,
        memory=_StubMemory(),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    servicer = ContextAssemblyServicer(
        _CancelAssembler(settings=settings, retriever=retriever)
    )
    req = pb2.AssembleContextRequest(
        org_id=str(ORG),
        agent_id=str(AGENT),
        model=MODEL,
    )
    ctx = _Ctx()
    with pytest.raises(asyncio.CancelledError):
        await servicer.AssembleContext(req, ctx)  # type: ignore[arg-type]
    assert ctx.aborts == [grpc.StatusCode.DEADLINE_EXCEEDED]


@pytest.mark.asyncio
async def test_record_memory_feedback_unimplemented(pb2) -> None:
    server, port = build_server(_assembler(), listen_addr="127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/RecordMemoryFeedback",
                request_serializer=pb2.RecordMemoryFeedbackRequest.SerializeToString,
                response_deserializer=pb2.RecordMemoryFeedbackResponse.FromString,
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(
                    pb2.RecordMemoryFeedbackRequest(
                        org_id=str(ORG),
                        memory_ids=[str(uuid4())],
                        feedback="positive",
                    )
                )
            assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_build_server_uses_settings_grpc_addr() -> None:
    settings = ContextSettings.model_construct(
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
    server, port = build_server(_assembler(), settings=settings)
    assert isinstance(port, int)
    assert port >= 0
    assert server is not None
    await server.stop(grace=None)


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


def test_build_assembler_from_settings_ok() -> None:
    settings = ContextSettings.model_construct(
        memory_base_url="http://memory.test",
        memory_api_token="tok",
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
    assembler = build_assembler_from_settings(settings)
    assert isinstance(assembler, ContextAssembler)


def test_build_assembler_with_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    redis_async = types.ModuleType("redis.asyncio")
    redis_async.from_url = lambda url: object()  # type: ignore[attr-defined]
    redis_mod = types.ModuleType("redis")
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)

    settings = ContextSettings.model_construct(
        memory_base_url="http://memory.test",
        memory_api_token="tok",
        redis_url="redis://localhost:6379/0",
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
    assembler = build_assembler_from_settings(settings)
    assert isinstance(assembler, ContextAssembler)


@pytest.mark.asyncio
async def test_serve_forever_starts_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    settings = ContextSettings.model_construct(
        memory_base_url="http://memory.test",
        memory_api_token="tok",
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

    class _FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def wait_for_termination(self) -> None:
            self.stopped = True

    fake = _FakeServer()

    def _fake_build(assembler, *, listen_addr=None, settings=None):  # type: ignore[no-untyped-def]
        return fake, 9092

    monkeypatch.setattr(server_mod, "build_server", _fake_build)
    monkeypatch.setattr(
        server_mod,
        "build_assembler_from_settings",
        lambda cfg: _assembler(),
    )
    await server_mod.serve_forever(settings)
    assert fake.started is True
    assert fake.stopped is True


def test_main_invokes_serve_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import server as server_mod

    called: list[bool] = []

    async def _fake_serve(settings=None):  # type: ignore[no-untyped-def]
        called.append(True)

    monkeypatch.setattr(server_mod, "serve_forever", _fake_serve)
    monkeypatch.setattr(server_mod.logging, "basicConfig", lambda **_: None)
    server_mod.main()
    assert called == [True]


def test_dunder_main_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    called: list[bool] = []

    def _fake_main() -> None:
        called.append(True)

    # Force a clean reload of __main__ so it binds the patched main.
    sys.modules.pop("app.__main__", None)
    monkeypatch.setattr("app.server.main", _fake_main)
    runpy.run_module("app.__main__", run_name="__main__")
    assert called == [True]


@pytest.mark.asyncio
async def test_missing_model_invalid(pb2) -> None:
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
                model="",
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(req, timeout=2.0)
            assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_empty_org_id_invalid(pb2) -> None:
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
                org_id="",
                agent_id=str(AGENT),
                model=MODEL,
            )
            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await stub(req, timeout=2.0)
            assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(grace=None)
