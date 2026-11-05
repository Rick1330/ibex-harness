"""asyncio gRPC ContextAssemblyService (milestone 3.5.C.6 / ADR-0071 / ADR-0096).

Registers generic handlers against ``ibex.context.v1`` message types from
``packages/proto/gen/python`` (local ``buf generate``; not committed).
``SearchMemories`` / ``RecordMemoryFeedback`` return UNIMPLEMENTED (ADR-0038).

ADR-0096 adds the missing caller boundary: a shared service token in
``x-ibex-context-service-token`` metadata, a mandatory verified
``principal_context``, selector binding, and a loopback-only bind. The token
authenticates the *caller*; it does not authorize the asserted tenant.
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
import signal
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import grpc
from grpc import aio as grpc_aio
from pydantic import SecretStr

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
from app.grpc_auth import (
    guard_handler,
    require_service_token,
    secret_value,
    validate_service_token,
)
from app.principal import (
    PrincipalError,
    PrincipalInvalid,
    PrincipalMismatch,
    PrincipalMissing,
    VerifiedPrincipal,
    bind_selectors,
    verify_principal,
)
from app.retrieval import ParallelRetriever

logger = logging.getLogger(__name__)

_SERVICE_NAME = "ibex.context.v1.ContextAssemblyService"
_ASSEMBLE = "AssembleContext"
_SEARCH = "SearchMemories"
_FEEDBACK = "RecordMemoryFeedback"
_SHUTDOWN_GRACE_S = 5.0
# H3: without so_reuseport a same-UID process can share the port and capture
# the caller token (ADR-0096).
_SERVER_OPTIONS: tuple[tuple[str, int], ...] = (("grpc.so_reuseport", 0),)

PRINCIPAL_REQUIRED_DETAILS = "verified principal context required"
PRINCIPAL_INVALID_DETAILS = "principal context is invalid or expired"
SELECTOR_MISMATCH_DETAILS = "request tenant does not match verified principal"

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
    """RPC handlers backed by ``ContextAssembler``.

    The caller token is enforced here as well as in the registered handler
    wrapper (ADR-0096 H12): constructing the servicer directly must not create
    an unauthenticated path.
    """

    def __init__(
        self,
        assembler: ContextAssembler,
        *,
        service_token: SecretStr | str,
    ) -> None:
        self._assembler = assembler
        self._service_token = validate_service_token(service_token)
        self._pb2 = _load_pb2()

    async def assemble_context(
        self,
        request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        await _abort_if_cancelled(context)
        await require_service_token(
            context,
            self._service_token,
            method=_ASSEMBLE,
        )
        verified = await _require_principal(request, context)
        domain = await _parse_assemble_request(request, context, verified)
        result = await self._assemble_or_deadline(domain, context)
        await _abort_if_cancelled(context)
        return _response_to_proto(self._pb2, result)

    async def _assemble_or_deadline(
        self,
        domain: AssembleRequest,
        context: grpc_aio.ServicerContext,
    ) -> AssemblyResult:
        try:
            return await self._assembler.assemble(domain)
        except asyncio.CancelledError:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")
            raise

    async def search_memories(
        self,
        _request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        await require_service_token(context, self._service_token, method=_SEARCH)
        return await _abort_unimplemented(context, _SEARCH)

    async def record_memory_feedback(
        self,
        _request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        await require_service_token(context, self._service_token, method=_FEEDBACK)
        return await _abort_unimplemented(context, _FEEDBACK)


async def _abort_if_cancelled(
    context: grpc_aio.ServicerContext,
    *,
    details: str = "cancelled",
) -> None:
    if not context.cancelled():
        return
    await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, details)
    raise AssertionError("unreachable")  # pragma: no cover


async def _require_principal(
    request: object,
    context: grpc_aio.ServicerContext,
) -> VerifiedPrincipal:
    """Verify the principal and bind the selectors before any downstream call."""
    try:
        verified = verify_principal(request)
        bind_selectors(request, verified)
    except PrincipalError as exc:
        await _abort_principal(context, exc)
        raise AssertionError("unreachable")  # pragma: no cover
    return verified


async def _abort_principal(
    context: grpc_aio.ServicerContext,
    exc: PrincipalError,
) -> None:
    code, details = _principal_abort(exc)
    logger.warning(
        "context_assembly_principal_rejected reason=%s detail=%s",
        exc.reason,
        str(exc),
    )
    await context.abort(code, details)


def _principal_abort(exc: PrincipalError) -> tuple[grpc.StatusCode, str]:
    if isinstance(exc, PrincipalMismatch):
        return grpc.StatusCode.PERMISSION_DENIED, SELECTOR_MISMATCH_DETAILS
    if isinstance(exc, PrincipalMissing):
        return grpc.StatusCode.UNAUTHENTICATED, PRINCIPAL_REQUIRED_DETAILS
    if isinstance(exc, PrincipalInvalid):
        return grpc.StatusCode.UNAUTHENTICATED, PRINCIPAL_INVALID_DETAILS
    return grpc.StatusCode.UNAUTHENTICATED, PRINCIPAL_INVALID_DETAILS  # pragma: no cover


async def _parse_assemble_request(
    request: object,
    context: grpc_aio.ServicerContext,
    verified: VerifiedPrincipal,
) -> AssembleRequest:
    try:
        return _request_from_proto(request, verified)
    except ValueError as exc:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        raise AssertionError("unreachable")  # pragma: no cover


async def _abort_unimplemented(
    context: grpc_aio.ServicerContext,
    method: str,
) -> object:
    await context.abort(
        grpc.StatusCode.UNIMPLEMENTED,
        f"{method} deferred — ADR-0038",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _host_from_addr(addr: str) -> str:
    host = (addr or "").rsplit(":", 1)[0].strip().lower()
    if host.startswith("["):
        host = host.strip("[]")
    return host


def _is_loopback_addr(addr: str) -> bool:
    """True only for loopback IP literals.

    ``localhost`` is deliberately excluded: it is a name, and a resolver or hosts
    file can point it at a non-loopback address. ``_require_loopback_bind``
    resolves every name so the bind cannot slip off loopback.
    """
    return _host_from_addr(addr) in {"127.0.0.1", "::1"}


def _require_loopback_bind(addr: str) -> None:
    """Refuse to bind anything that is not loopback (ADR-0096).

    ``getaddrinfo`` is consulted for non-literal hosts so a name that resolves
    to a public address is rejected; every resolved address must be loopback.
    Unresolvable names fail closed.
    """
    host = _host_from_addr(addr)
    if not host:
        msg = f"IBEX_CONTEXT_GRPC_ADDR must be host:port, got {addr!r}"
        raise ValueError(msg)
    if _is_loopback_addr(addr):
        return
    addresses = _resolved_addresses(host)
    if not addresses or not all(_is_loopback_ip(item) for item in addresses):
        msg = (
            "IBEX_CONTEXT_GRPC_ADDR must resolve to loopback only; refusing "
            f"bind {addr!r} (ADR-0096)"
        )
        raise ValueError(msg)


def _resolved_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    return [str(info[4][0]) for info in infos]


def _is_loopback_ip(text: str) -> bool:
    try:
        return ipaddress.ip_address(text.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _startup_service_token(settings: ContextSettings) -> str:
    """Validate the configured caller token (fail closed at startup)."""
    token = validate_service_token(settings.grpc_service_token)
    memory_token = secret_value(settings.memory_api_token)
    if memory_token and hmac.compare_digest(
        token.encode("utf-8"),
        memory_token.encode("utf-8"),
    ):
        msg = (
            "IBEX_CONTEXT_GRPC_SERVICE_TOKEN must differ from "
            "IBEX_CONTEXT_MEMORY_API_TOKEN (ADR-0096)"
        )
        raise ValueError(msg)
    return token


def build_server(
    assembler: ContextAssembler,
    *,
    listen_addr: str | None = None,
    settings: ContextSettings | None = None,
) -> tuple[grpc_aio.Server, int]:
    """Create an aio server with ContextAssemblyService registered.

    Returns ``(server, bound_port)``. Raises ``ValueError`` when the caller
    token is missing/invalid or the bind address is not loopback.
    """
    pb2 = _load_pb2()
    cfg = settings or ContextSettings()
    token = _startup_service_token(cfg)
    addr = listen_addr if listen_addr is not None else cfg.grpc_addr
    _require_loopback_bind(addr)
    servicer = ContextAssemblyServicer(assembler, service_token=token)
    server = grpc_aio.server(options=_SERVER_OPTIONS)
    server.add_generic_rpc_handlers((_generic_handler(servicer, pb2, token),))
    port = server.add_insecure_port(addr)
    return server, int(port)


def _generic_handler(
    servicer: ContextAssemblyServicer,
    pb2: object,
    token: str,
) -> grpc.GenericRpcHandler:
    handlers = {
        _ASSEMBLE: _unary_handler(
            method=_ASSEMBLE,
            behavior=servicer.assemble_context,
            token=token,
            request_deserializer=pb2.AssembleContextRequest.FromString,  # type: ignore[attr-defined]
            response_serializer=pb2.AssembleContextResponse.SerializeToString,  # type: ignore[attr-defined]
        ),
        _SEARCH: _unary_handler(
            method=_SEARCH,
            behavior=servicer.search_memories,
            token=token,
            request_deserializer=pb2.SearchMemoriesRequest.FromString,  # type: ignore[attr-defined]
            response_serializer=pb2.SearchMemoriesResponse.SerializeToString,  # type: ignore[attr-defined]
        ),
        _FEEDBACK: _unary_handler(
            method=_FEEDBACK,
            behavior=servicer.record_memory_feedback,
            token=token,
            request_deserializer=pb2.RecordMemoryFeedbackRequest.FromString,  # type: ignore[attr-defined]
            response_serializer=pb2.RecordMemoryFeedbackResponse.SerializeToString,  # type: ignore[attr-defined]
        ),
    }
    return grpc.method_handlers_generic_handler(_SERVICE_NAME, handlers)


def _unary_handler(
    *,
    method: str,
    behavior: Any,
    token: str,
    request_deserializer: Any,
    response_serializer: Any,
) -> grpc.RpcMethodHandler:
    guarded = guard_handler(behavior, token, method=method)
    handler = grpc.unary_unary_rpc_method_handler(
        guarded,
        request_deserializer=request_deserializer,
        response_serializer=response_serializer,
    )
    _require_unary(method, handler)
    return handler


def _require_unary(method: str, handler: grpc.RpcMethodHandler) -> None:
    """Every registered RPC must stay unary so the token guard covers it."""
    if handler.request_streaming or handler.response_streaming:
        msg = f"{method} must be registered as a unary RPC (ADR-0096)"
        raise ValueError(msg)


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
            token=secret_value(settings.memory_api_token),
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
    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    server: grpc_aio.Server | None = None
    try:
        server = await _start_listening(runtime, cfg)
        _install_shutdown_signals(loop, shutdown)
        await _run_until_shutdown(server, shutdown)
    finally:
        await _shutdown_runtime(loop, server, runtime)


async def _start_listening(
    runtime: AssemblyRuntime,
    cfg: ContextSettings,
) -> grpc_aio.Server:
    server, port = build_server(runtime.assembler, settings=cfg)
    await server.start()
    logger.info(
        "context_assembly_grpc_listening addr=%s port=%s retrieval_wall_ms=%s",
        cfg.grpc_addr,
        port,
        cfg.retrieval_wall_ms,
    )
    return server


async def _shutdown_runtime(
    loop: asyncio.AbstractEventLoop,
    server: grpc_aio.Server | None,
    runtime: AssemblyRuntime,
) -> None:
    _clear_shutdown_signals(loop)
    if server is not None:
        await server.stop(grace=_SHUTDOWN_GRACE_S)
    await runtime.aclose()


def _install_shutdown_signals(loop: asyncio.AbstractEventLoop, shutdown: asyncio.Event) -> None:
    def _request_shutdown() -> None:
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except RuntimeError:  # pragma: no cover - platform (covers NotImplementedError)
            pass


def _clear_shutdown_signals(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.remove_signal_handler(sig)
        except RuntimeError:  # pragma: no cover - platform
            pass


async def _run_until_shutdown(
    server: grpc_aio.Server,
    shutdown: asyncio.Event,
) -> None:
    wait_termination = asyncio.create_task(server.wait_for_termination())
    wait_signal = asyncio.create_task(shutdown.wait())
    done, pending = await asyncio.wait(
        {wait_termination, wait_signal},
        return_when=asyncio.FIRST_COMPLETED,
    )
    await _stop_server_on_signal(server, wait_termination, wait_signal, done)
    await _cancel_tasks(pending)
    if wait_termination in done:
        await wait_termination


async def _stop_server_on_signal(
    server: grpc_aio.Server,
    wait_termination: asyncio.Task[Any],
    wait_signal: asyncio.Task[Any],
    done: set[asyncio.Task[Any]],
) -> None:
    if wait_signal not in done:
        return
    if wait_termination.done():
        return
    await server.stop(grace=_SHUTDOWN_GRACE_S)


async def _cancel_tasks(tasks: set[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
    if not tasks:
        return
    # Absorb cancel outcomes without catching CancelledError (python:S7497).
    await asyncio.gather(*tasks, return_exceptions=True)


def _request_from_proto(
    request: object,
    verified: VerifiedPrincipal,
) -> AssembleRequest:
    """Build the domain request from the verified principal, never the selectors."""
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
        org_id=verified.org_id,
        agent_id=verified.agent_id,
        query=query,
        model=model,
        recent_messages=_messages_from_proto(raw_messages),
        session_id=_optional_uuid(
            getattr(request, "session_id", ""),
            label="session_id",
        ),
        directive_version_id=_optional_uuid(
            getattr(request, "directive_version_id", ""),
            label="directive_version_id",
        ),
        request_id=_optional_uuid(
            getattr(request, "request_id", ""),
            label="request_id",
        ),
        trace_id=_optional_w3c_trace_id(getattr(request, "trace_id", "")),
        span_id=_optional_w3c_span_id(getattr(request, "span_id", "")),
        available_tokens=_available_tokens_from_proto(request),
        options=_options_from_proto(getattr(request, "options", None)),
    )


def _available_tokens_from_proto(request: object) -> int:
    raw = int(getattr(request, "available_tokens", 0) or 0)
    if raw < 0:
        raise ValueError(f"available_tokens must be >= 0, got {raw}")
    # Bound to a sane upper ceiling (model windows are << this).
    if raw > 10_000_000:
        raise ValueError(f"available_tokens exceeds 10000000, got {raw}")
    return raw


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
            exclusion=m.exclusion,
            similarity=m.similarity,
            confidence=m.confidence,
            token_estimate=m.token_estimate,
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
        request_id=result.request_id,
        trace_id=result.trace_id,
        span_id=result.span_id,
        score_schema=result.score_schema,
    )


def _optional_uuid(raw: object, *, label: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return str(UUID(text))
    except ValueError as exc:
        raise ValueError(f"{label} must be a UUID") from exc


_HEX = frozenset("0123456789abcdef")


def _is_w3c_hex(text: str, length: int) -> bool:
    return len(text) == length and all(c in _HEX for c in text)


def _optional_w3c_trace_id(raw: object) -> str:
    return _optional_w3c_hex_id(raw, label="trace_id", length=32)


def _optional_w3c_span_id(raw: object) -> str:
    return _optional_w3c_hex_id(raw, label="span_id", length=16)


def _optional_w3c_hex_id(raw: object, *, label: str, length: int) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if not _is_w3c_hex(text, length):
        raise ValueError(
            f"{label} must be a {length}-character hexadecimal W3C {label}"
        )
    if text == "0" * length:
        raise ValueError(f"{label} must be nonzero")
    return text


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve_forever())


if __name__ == "__main__":  # pragma: no cover - exercised via python -m app
    main()
