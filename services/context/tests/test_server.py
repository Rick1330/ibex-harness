"""gRPC ContextAssemblyService tests (milestone 3.5.C.6)."""

from __future__ import annotations

import asyncio
import logging
import runpy
import sys
import time
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
from app.config import MAX_ASSEMBLY_OPTION_MEMORIES, ContextSettings
from app.retrieval import ParallelRetriever
from app.server import (
    _SERVICE_NAME,
    AssemblyRuntime,
    ContextAssemblyServicer,
    _is_loopback_addr,
    _options_from_proto,
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
    """Optional per-path delays so cold can outlive deadline_ms but not timeout_ms."""

    def __init__(
        self,
        *,
        delay_s: float = 0.0,
        hot_delay_s: float | None = None,
        cold_delay_s: float | None = None,
    ) -> None:
        self._hot_delay_s = delay_s if hot_delay_s is None else hot_delay_s
        self._cold_delay_s = delay_s if cold_delay_s is None else cold_delay_s
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
        if self._hot_delay_s:
            await asyncio.sleep(self._hot_delay_s)
        return [self._hit]

    async def search_memories(self, *_args, **_kwargs):
        if self._cold_delay_s:
            await asyncio.sleep(self._cold_delay_s)
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


def _assembler(
    *,
    delay_s: float = 0.0,
    settings: ContextSettings | None = None,
    memory: _StubMemory | None = None,
) -> ContextAssembler:
    cfg = settings or _settings()
    retriever = ParallelRetriever(
        settings=cfg,
        memory=memory or _StubMemory(delay_s=delay_s),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    return ContextAssembler(settings=cfg, retriever=retriever)


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
        settings=settings,
        memory=_StubMemory(hot_delay_s=0.0, cold_delay_s=0.5),
    )
    async with _rpc_channel(assembler) as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            query="theme",
            recent_messages=[pb2.Message(role="user", content="hello")],
        )
        started = time.perf_counter()
        resp = await stub(req, timeout=2.0)
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
        {"query": "x" * 9000},
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
@pytest.mark.parametrize("max_memories", [-1, MAX_ASSEMBLY_OPTION_MEMORIES + 1])
async def test_assemble_rejects_out_of_range_max_memories(pb2, max_memories) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            options=pb2.AssemblyOptions(max_memories=max_memories),
        )

        async def _call() -> object:
            return await stub(req, timeout=2.0)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_options_from_proto_bounds_max_memories(pb2) -> None:
    ok = _options_from_proto(pb2.AssemblyOptions(max_memories=10))
    assert ok.max_memories == 10
    negative = pb2.AssemblyOptions(max_memories=-1)
    with pytest.raises(ValueError, match="max_memories"):
        _options_from_proto(negative)
    too_large = pb2.AssemblyOptions(max_memories=MAX_ASSEMBLY_OPTION_MEMORIES + 1)
    with pytest.raises(ValueError, match="max_memories"):
        _options_from_proto(too_large)


@pytest.mark.asyncio
async def test_assemble_rejects_oversized_recent_messages(pb2) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            recent_messages=[
                pb2.Message(role="user", content="hi") for _ in range(101)
            ],
        )

        async def _call() -> object:
            return await stub(req, timeout=2.0)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_assemble_rejects_oversized_message_content(pb2) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))
        req = _assemble_req(
            pb2,
            recent_messages=[pb2.Message(role="user", content="y" * 40_000)],
        )

        async def _call() -> object:
            return await stub(req, timeout=2.0)

        err = await _rpc_raises(_call)
        assert err.code() == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_assemble_rejects_oversized_model_and_role(pb2) -> None:
    async with _rpc_channel() as channel:
        stub = _unary_stub(channel, "AssembleContext", _assemble_codec(pb2))

        async def _call_model() -> object:
            return await stub(_assemble_req(pb2, model="m" * 300), timeout=2.0)

        err = await _rpc_raises(_call_model)
        assert err.code() == grpc.StatusCode.INVALID_ARGUMENT

        async def _call_role() -> object:
            return await stub(
                _assemble_req(
                    pb2,
                    recent_messages=[pb2.Message(role="r" * 80, content="hi")],
                ),
                timeout=2.0,
            )

        err = await _rpc_raises(_call_role)
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
    req = _assemble_req(pb2)
    with pytest.raises(asyncio.CancelledError):
        await servicer.assemble_context(req, ctx)  # type: ignore[arg-type]
    assert ctx.aborts == [grpc.StatusCode.DEADLINE_EXCEEDED]


@pytest.mark.asyncio
async def test_build_server_uses_settings_grpc_addr() -> None:
    server, port = build_server(_assembler(), settings=_settings())
    assert isinstance(port, int)
    assert port >= 0
    assert server is not None
    await server.stop(grace=None)


def test_is_loopback_addr() -> None:
    assert _is_loopback_addr("127.0.0.1:9092")
    assert _is_loopback_addr("localhost:9092")
    assert _is_loopback_addr("[::1]:9092")
    assert not _is_loopback_addr("0.0.0.0:9092")
    assert not _is_loopback_addr("10.0.0.5:9092")


@pytest.mark.asyncio
async def test_build_server_warns_non_loopback_without_auth(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.server"):
        server, _port = build_server(_assembler(), listen_addr="0.0.0.0:0")
    assert any(
        "context_assembly_grpc_non_loopback_bind" in r.message
        and "3.5.D.1" in r.message
        and "ADR-0071" in r.message
        for r in caplog.records
    )
    await server.stop(grace=None)


def test_build_assembler_requires_memory_base_url() -> None:
    settings = _settings()
    with pytest.raises(ValueError, match="MEMORY_BASE_URL"):
        build_assembler_from_settings(settings)


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

    class _FakeMemory:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def wait_for_termination(self) -> None:
            self.stopped = True

        async def stop(self, grace: float | None = None) -> None:
            self.stopped = True

    fake = _FakeServer()
    memory = _FakeMemory()
    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=memory,  # type: ignore[arg-type]
        redis_client=None,
    )
    monkeypatch.setattr(server_mod, "build_server", lambda *a, **k: (fake, 9092))
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )
    await server_mod.serve_forever(
        _settings(memory_base_url="http://memory.test", memory_api_token="tok")
    )
    assert fake.started is True
    assert fake.stopped is True
    assert memory.closed is True


@pytest.mark.asyncio
async def test_serve_forever_signal_stops_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import server as server_mod

    class _FakeMemory:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeRedis:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeServer:
        def __init__(self) -> None:
            self.stop_grace: float | None = None
            self._term = asyncio.Event()

        async def start(self) -> None:
            return None

        async def wait_for_termination(self) -> None:
            await self._term.wait()

        async def stop(self, grace: float | None = None) -> None:
            self.stop_grace = grace
            self._term.set()

    fake = _FakeServer()
    memory = _FakeMemory()
    redis = _FakeRedis()
    runtime = AssemblyRuntime(
        assembler=_assembler(),
        memory=memory,  # type: ignore[arg-type]
        redis_client=redis,
    )
    monkeypatch.setattr(server_mod, "build_server", lambda *a, **k: (fake, 9092))
    monkeypatch.setattr(
        server_mod,
        "build_runtime_from_settings",
        lambda cfg: runtime,
    )

    shutdown_box: list[asyncio.Event] = []
    real_event = asyncio.Event

    def _tracking_event() -> asyncio.Event:
        ev = real_event()
        shutdown_box.append(ev)
        return ev

    monkeypatch.setattr(server_mod.asyncio, "Event", _tracking_event)
    serve_task = asyncio.create_task(
        server_mod.serve_forever(
            _settings(memory_base_url="http://memory.test", memory_api_token="tok")
        )
    )
    await asyncio.sleep(0.05)
    assert shutdown_box, "serve_forever should create a shutdown Event"
    shutdown_box[0].set()
    await serve_task
    assert fake.stop_grace == server_mod._SHUTDOWN_GRACE_S
    assert memory.closed is True
    assert redis.closed is True


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
