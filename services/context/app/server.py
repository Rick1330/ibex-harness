"""asyncio gRPC ContextAssemblyService (milestone 3.5.C.6 / ADR-0071).

Registers generic handlers against ``ibex.context.v1`` message types from
``packages/proto/gen/python`` (local ``buf generate``; not committed).
``SearchMemories`` / ``RecordMemoryFeedback`` return UNIMPLEMENTED (ADR-0038).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import grpc
from grpc import aio as grpc_aio

from app.assemble import (
    AssembleRequest,
    AssemblyOptions,
    AssemblyResult,
    ContextAssembler,
)
from app.budget import Message
from app.clients.directive import EmptyDirectiveLookup, RedisDirectiveLookup
from app.clients.memory import MemoryHttpClient, MemoryHttpConfig
from app.config import MAX_ASSEMBLY_OPTION_MEMORIES, ContextSettings
from app.retrieval import ParallelRetriever

logger = logging.getLogger(__name__)

_SERVICE_NAME = "ibex.context.v1.ContextAssemblyService"
_ASSEMBLE = "AssembleContext"
_SEARCH = "SearchMemories"
_FEEDBACK = "RecordMemoryFeedback"
_SHUTDOWN_GRACE_S = 5.0

# Request-field bounds (AGENTS.md §5.2); transport limits remain defense in depth.
_MAX_QUERY_CHARS = 8_192
_MAX_MODEL_CHARS = 256
_MAX_RECENT_MESSAGES = 100
_MAX_ROLE_CHARS = 64
_MAX_CONTENT_CHARS = 32_768


def _load_pb2():
    """Import generated protobuf module (requires ``make proto-gen`` / CI script)."""
    try:
        from ibex.context.v1 import context_pb2 as pb2
    except ImportError as exc:  # pragma: no cover - env misconfig
        msg = (
            "ibex.context.v1.context_pb2 not found — run "
            "`bash infra/scripts/context-proto-gen.sh` (or `make proto-gen`) "
            "and ensure packages/proto/gen/python is on PYTHONPATH"
        )
        raise ImportError(msg) from exc
    return pb2


class ContextAssemblyServicer:
    """RPC handlers backed by ``ContextAssembler``."""

    def __init__(self, assembler: ContextAssembler) -> None:
        self._assembler = assembler
        self._pb2 = _load_pb2()

    async def assemble_context(
        self,
        request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        pb2 = self._pb2
        if context.cancelled():
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "cancelled")
            raise AssertionError("unreachable")  # pragma: no cover

        try:
            domain = _request_from_proto(request)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("unreachable")  # pragma: no cover

        try:
            result = await self._assembler.assemble(domain)
        except asyncio.CancelledError:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")
            raise
        if context.cancelled():
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "cancelled")
            raise AssertionError("unreachable")  # pragma: no cover

        return _response_to_proto(pb2, result)

    async def search_memories(
        self,
        _request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        return await _abort_unimplemented(context, _SEARCH)

    async def record_memory_feedback(
        self,
        _request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        return await _abort_unimplemented(context, _FEEDBACK)


async def _abort_unimplemented(
    context: grpc_aio.ServicerContext,
    method: str,
) -> object:
    await context.abort(
        grpc.StatusCode.UNIMPLEMENTED,
        f"{method} deferred — ADR-0038",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _is_loopback_addr(addr: str) -> bool:
    host = (addr or "").rsplit(":", 1)[0].strip().lower()
    if host.startswith("["):
        host = host.strip("[]")
    return host in {"127.0.0.1", "localhost", "::1"}


def _warn_non_loopback_bind(addr: str) -> None:
    if _is_loopback_addr(addr):
        return
    logger.warning(
        "context_assembly_grpc_non_loopback_bind addr=%s "
        "auth_interceptor=absent "
        "risk=request_org_agent_ids_trusted_without_caller_auth "
        "deferred_to=milestone_3.5.D.1 adr=ADR-0071",
        addr,
    )


def build_server(
    assembler: ContextAssembler,
    *,
    listen_addr: str | None = None,
    settings: ContextSettings | None = None,
) -> tuple[grpc_aio.Server, int]:
    """Create an aio server with ContextAssemblyService registered.

    Returns ``(server, bound_port)``.
    """
    pb2 = _load_pb2()
    servicer = ContextAssemblyServicer(assembler)
    server = grpc_aio.server()
    handlers = {
        _ASSEMBLE: grpc.unary_unary_rpc_method_handler(
            servicer.assemble_context,
            request_deserializer=pb2.AssembleContextRequest.FromString,
            response_serializer=pb2.AssembleContextResponse.SerializeToString,
        ),
        _SEARCH: grpc.unary_unary_rpc_method_handler(
            servicer.search_memories,
            request_deserializer=pb2.SearchMemoriesRequest.FromString,
            response_serializer=pb2.SearchMemoriesResponse.SerializeToString,
        ),
        _FEEDBACK: grpc.unary_unary_rpc_method_handler(
            servicer.record_memory_feedback,
            request_deserializer=pb2.RecordMemoryFeedbackRequest.FromString,
            response_serializer=pb2.RecordMemoryFeedbackResponse.SerializeToString,
        ),
    }
    generic = grpc.method_handlers_generic_handler(_SERVICE_NAME, handlers)
    server.add_generic_rpc_handlers((generic,))
    addr = listen_addr
    if addr is None:
        cfg = settings or ContextSettings()
        addr = cfg.grpc_addr
    _warn_non_loopback_bind(addr)
    port = server.add_insecure_port(addr)
    return server, int(port)


@dataclass(slots=True)
class AssemblyRuntime:
    """Assembler plus closable I/O clients owned by ``serve_forever``."""

    assembler: ContextAssembler
    memory: MemoryHttpClient
    redis_client: Any | None = None

    async def aclose(self) -> None:
        await self.memory.aclose()
        if self.redis_client is not None:
            close = getattr(self.redis_client, "aclose", None)
            if close is not None:
                await close()


def build_runtime_from_settings(settings: ContextSettings) -> AssemblyRuntime:
    """Wire HTTP memory + optional Redis directive; caller must ``aclose``."""
    if not settings.memory_base_url.strip():
        msg = "IBEX_CONTEXT_MEMORY_BASE_URL / MEMORY_BASE_URL is required"
        raise ValueError(msg)
    memory = MemoryHttpClient(
        MemoryHttpConfig(
            base_url=settings.memory_base_url,
            token=settings.memory_api_token,
        )
    )
    redis_client: Any | None = None
    directive: EmptyDirectiveLookup | RedisDirectiveLookup = EmptyDirectiveLookup()
    if settings.redis_url.strip():
        import redis.asyncio as redis_async

        redis_client = redis_async.from_url(settings.redis_url)
        directive = RedisDirectiveLookup(redis_client)
    retriever = ParallelRetriever(
        settings=settings,
        memory=memory,
        directive=directive,
    )
    return AssemblyRuntime(
        assembler=ContextAssembler(settings=settings, retriever=retriever),
        memory=memory,
        redis_client=redis_client,
    )


def build_assembler_from_settings(settings: ContextSettings) -> ContextAssembler:
    """Wire HTTP memory + optional Redis directive from settings."""
    return build_runtime_from_settings(settings).assembler


async def serve_forever(settings: ContextSettings | None = None) -> None:
    """Entrypoint: build dependencies, start server, wait for termination."""
    cfg = settings or ContextSettings()
    runtime = build_runtime_from_settings(cfg)
    server, port = build_server(runtime.assembler, settings=cfg)
    await server.start()
    logger.info(
        "context_assembly_grpc_listening addr=%s port=%s retrieval_wall_ms=%s",
        cfg.grpc_addr,
        port,
        cfg.retrieval_wall_ms,
    )

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except RuntimeError:  # pragma: no cover - platform (covers NotImplementedError)
            pass

    wait_termination = asyncio.create_task(server.wait_for_termination())
    wait_signal = asyncio.create_task(shutdown.wait())
    try:
        done, pending = await asyncio.wait(
            {wait_termination, wait_signal},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if wait_signal in done and not wait_termination.done():
            await server.stop(grace=_SHUTDOWN_GRACE_S)
        for task in pending:
            task.cancel()
        if pending:
            # Absorb cancel outcomes without catching CancelledError (python:S7497).
            await asyncio.gather(*pending, return_exceptions=True)
        if wait_termination in done:
            await wait_termination
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.remove_signal_handler(sig)
            except RuntimeError:  # pragma: no cover - platform
                pass
        await runtime.aclose()


def _request_from_proto(request: object) -> AssembleRequest:
    org_id = _parse_uuid(getattr(request, "org_id", ""), "org_id")
    agent_id = _parse_uuid(getattr(request, "agent_id", ""), "agent_id")
    model = _bounded_text(
        getattr(request, "model", ""),
        label="model",
        max_chars=_MAX_MODEL_CHARS,
        required=True,
    )
    query = _bounded_text(
        getattr(request, "query", ""),
        label="query",
        max_chars=_MAX_QUERY_CHARS,
        required=False,
    )
    raw_messages = getattr(request, "recent_messages", ()) or ()
    if len(raw_messages) > _MAX_RECENT_MESSAGES:
        raise ValueError(f"recent_messages exceeds {_MAX_RECENT_MESSAGES} items")
    return AssembleRequest(
        org_id=org_id,
        agent_id=agent_id,
        query=query,
        model=model,
        recent_messages=_messages_from_proto(raw_messages),
        options=_options_from_proto(getattr(request, "options", None)),
    )


def _bounded_text(
    raw: object,
    *,
    label: str,
    max_chars: int,
    required: bool,
) -> str:
    text = str(raw or "").strip() if required else str(raw or "")
    if required and not text:
        raise ValueError(f"{label} is required")
    if len(text) > max_chars:
        raise ValueError(f"{label} exceeds {max_chars} characters")
    return text


def _options_from_proto(options_msg: object | None) -> AssemblyOptions:
    if options_msg is None:
        return AssemblyOptions()
    max_memories = int(getattr(options_msg, "max_memories", 0) or 0)
    if max_memories < 0 or max_memories > MAX_ASSEMBLY_OPTION_MEMORIES:
        raise ValueError(
            f"max_memories must be in 0..{MAX_ASSEMBLY_OPTION_MEMORIES}, "
            f"got {max_memories}"
        )
    return AssemblyOptions(
        skip_cold_memories=bool(getattr(options_msg, "skip_cold_memories", False)),
        skip_hot_memories=bool(getattr(options_msg, "skip_hot_memories", False)),
        max_memories=max_memories,
    )


def _messages_from_proto(raw: Sequence[object]) -> list[Message]:
    out: list[Message] = []
    for item in raw:
        role = _bounded_text(
            getattr(item, "role", ""),
            label="message.role",
            max_chars=_MAX_ROLE_CHARS,
            required=False,
        )
        content = _bounded_text(
            getattr(item, "content", ""),
            label="message.content",
            max_chars=_MAX_CONTENT_CHARS,
            required=False,
        )
        out.append(Message(role=role, content=content))
    return out


def _response_to_proto(pb2: object, result: AssemblyResult) -> object:
    metrics = result.metrics
    memories = [
        pb2.MemoryUsed(  # type: ignore[attr-defined]
            memory_id=m.memory_id,
            composite_score=m.composite_score,
            relevance_score=m.relevance_score,
            recency_score=m.recency_score,
            usefulness_score=m.usefulness_score,
            rank=m.rank,
            category=m.category,
        )
        for m in result.memories_used
    ]
    return pb2.AssembleContextResponse(  # type: ignore[attr-defined]
        assembled_context=result.formatted.assembled_context,
        tokens_used=int(result.tokens_used),
        memories_included=int(result.formatted.memories_included),
        memories_used=memories,
        directive_tokens=int(result.budget.directive_tokens),
        history_tokens=int(result.budget.messages_tokens),
        memory_tokens=int(result.packed.total_tokens),
        metrics=pb2.AssemblyMetrics(  # type: ignore[attr-defined]
            budget_calculation_ms=metrics.budget_calculation_ms,
            directive_load_ms=metrics.directive_load_ms,
            hot_memory_retrieval_ms=metrics.hot_memory_retrieval_ms,
            cold_memory_retrieval_ms=metrics.cold_memory_retrieval_ms,
            ranking_ms=metrics.ranking_ms,
            packing_ms=metrics.packing_ms,
            formatting_ms=metrics.formatting_ms,
            total_ms=metrics.total_ms,
            candidates_evaluated=metrics.candidates_evaluated,
        ),
    )


def _parse_uuid(raw: str, label: str) -> UUID:
    text = (raw or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    try:
        return UUID(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a UUID") from exc


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve_forever())


if __name__ == "__main__":  # pragma: no cover - exercised via python -m app
    main()
