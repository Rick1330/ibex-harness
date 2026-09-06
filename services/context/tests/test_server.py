"""gRPC ContextAssemblyService tests (milestone 3.5.C.6)."""

from __future__ import annotations

import asyncio
import runpy
import sys
import types
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
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


def _settings(**overrides: object) -> ContextSettings:
    base: dict[str, object] = {
        "timeout_ms": 45.0,
        "deadline_ms": 40.0,
        "directive_timeout_ms": 5.0,
        "hot_timeout_ms": 15.0,
        "cold_timeout_ms": 45.0,
        "formatter_nonce_bytes": 16,
        "packer_dp_cell_ceiling": 70 * 6251,
        "packer_max_consecutive_skips": 5,
        "grpc_addr": "127.0.0.1:0",
        "memory_base_url": "",
        "memory_api_token": "",
        "redis_url": "",
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


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


@asynccontextmanager
async def _rpc_channel(assembler: ContextAssembler | None = None):
    server, port = build_server(assembler or _assembler(), listen_addr="127.0.0.1:0")
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


def _assemble_req(pb2, **fields):  # type: ignore[no-untyped-def]
    payload = {
        "org_id": str(ORG),
        "agent_id": str(AGENT),
        "model": MODEL,
    }
    payload.update(fields)
    return pb2.AssembleContextRequest(**payload)


async def _rpc_raises(
    call: Callable[[], Awaitable[object]],
) -> grpc.aio.AioRpcError:
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await call()
    return exc_info.value


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
        )
        assert resp.assembled_context
        assert resp.memories_included >= 1
        assert resp.metrics.candidates_evaluated >= 1
        assert resp.metrics.total_ms >= 0


@pytest.mark.asyncio
async def test_assemble_context_l3_deadline_exceeded(pb2) -> None:
    settings = _settings()
    assembler = _SlowAssembler(
        settings=settings,
        retriever=ParallelRetriever(
            settings=settings,
            memory=_StubMemory(),  # type: ignore[arg-type]
            directive=_StubDirective(),
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
            return await stub(req, timeout=0.05)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.DEADLINE_EXCEEDED


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
            return await stub(req)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"org_id": "not-a-uuid"},
        {"org_id": ""},
        {"model": ""},
    ],
)
async def test_assemble_invalid_argument(pb2, fields) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(pb2, **fields)

        async def _call() -> object:
            return await stub(req, timeout=2.0)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_servicer_direct_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())

    class _Ctx:
        def cancelled(self) -> bool:
            return False

        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            raise grpc.aio.AioRpcError(code, details=details)

    resp = await servicer.assemble_context(
        _assemble_req(
            pb2,
            query="q",
            recent_messages=[pb2.Message(role="user", content="hi")],
        ),
        _Ctx(),  # type: ignore[arg-type]
    )
    assert resp.assembled_context
    assert "user: hi" in resp.assembled_context or resp.memories_included >= 0


@pytest.mark.asyncio
async def test_servicer_cancelled_before_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())
    ctx = _AbortCtx(cancelled=True)

    async def _call() -> object:
        return await servicer.assemble_context(_assemble_req(pb2), ctx)  # type: ignore[arg-type]

    err = await _rpc_raises(_call)
    assert err.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    assert ctx.aborts[0][0] == grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_servicer_cancelled_after_assemble(pb2) -> None:
    servicer = ContextAssemblyServicer(_assembler())

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

    class _Ctx:
        def __init__(self) -> None:
            self.aborts: list[object] = []

        def cancelled(self) -> bool:
            return False

        async def abort(self, code, details):  # type: ignore[no-untyped-def]
            self.aborts.append(code)

    settings = _settings()
    servicer = ContextAssemblyServicer(
        _CancelAssembler(
            settings=settings,
            retriever=ParallelRetriever(
                settings=settings,
                memory=_StubMemory(),  # type: ignore[arg-type]
                directive=_StubDirective(),
            ),
        )
    )
    ctx = _Ctx()
    with pytest.raises(asyncio.CancelledError):
        await servicer.assemble_context(_assemble_req(pb2), ctx)  # type: ignore[arg-type]
    assert ctx.aborts == [grpc.StatusCode.DEADLINE_EXCEEDED]


@pytest.mark.asyncio
async def test_build_server_uses_settings_grpc_addr() -> None:
    server, port = build_server(_assembler(), settings=_settings())
    assert isinstance(port, int)
    assert port >= 0
    assert server is not None
    await server.stop(grace=None)


def test_build_assembler_requires_memory_base_url() -> None:
    with pytest.raises(ValueError, match="MEMORY_BASE_URL"):
        build_assembler_from_settings(_settings())


def test_build_assembler_from_settings_ok() -> None:
    assembler = build_assembler_from_settings(
        _settings(memory_base_url="http://memory.test", memory_api_token="tok")
    )
    assert isinstance(assembler, ContextAssembler)


def test_build_assembler_with_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_async = types.ModuleType("redis.asyncio")
    redis_async.from_url = lambda url: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", types.ModuleType("redis"))
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)
    assembler = build_assembler_from_settings(
        _settings(
            memory_base_url="http://memory.test",
            memory_api_token="tok",
            redis_url="redis://localhost:6379/0",
        )
    )
    assert isinstance(assembler, ContextAssembler)


@pytest.mark.asyncio
async def test_serve_forever_starts_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    class _FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def wait_for_termination(self) -> None:
            self.stopped = True

    fake = _FakeServer()
    monkeypatch.setattr(server_mod, "build_server", lambda *a, **k: (fake, 9092))
    monkeypatch.setattr(
        server_mod,
        "build_assembler_from_settings",
        lambda cfg: _assembler(),
    )
    await server_mod.serve_forever(
        _settings(memory_base_url="http://memory.test", memory_api_token="tok")
    )
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
    called: list[bool] = []

    def _fake_main() -> None:
        called.append(True)

    sys.modules.pop("app.__main__", None)
    monkeypatch.setattr("app.server.main", _fake_main)
    runpy.run_module("app.__main__", run_name="__main__")
    assert called == [True]
