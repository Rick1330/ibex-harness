#!/usr/bin/env python3
"""AssembleContext gRPC load harness (milestone 3.5.C.6 / ADR-0034 methodology).

Stub profile (default): in-process server with fast memory stubs — CI-friendly
latency signal; asserts p99 < 50ms at the configured target RPS.

Live profile: point ``--addr`` at a running ContextAssemblyService backed by a
100K-memory corpus (seed via ``benchmarks/memory`` HNSW tooling). Live runs do
not fail the process on p99; they print percentiles for PR documentation.
``--addr`` must be a loopback IP literal (``127.0.0.1`` or ``[::1]``): the
caller token is a reusable credential, and plaintext gRPC to any other host
would send it off this machine.

``--org-id`` and ``--agent-id`` (canonical UUIDs) select the tenant both
profiles exercise; absent flags fall back to the module defaults.

ADR-0096: every call carries ``x-ibex-context-service-token`` and a fresh
``PrincipalContext`` (``issued_at`` per call, so runs longer than the 30s skew
window stay valid). The live profile needs a token: ``--token`` or
``IBEX_CONTEXT_GRPC_SERVICE_TOKEN``.

Scheduling launches RPCs on a monotonic interval (open-loop) so measured RPS
tracks ``--rps`` even when individual calls exceed the inter-arrival gap.

Examples::

  PYTHONPATH=packages/proto/gen/python:services/context \\
    python benchmarks/context/assemble_load.py --profile stub --rps 500 --duration 10

  PYTHONPATH=packages/proto/gen/python:services/context \\
    IBEX_CONTEXT_GRPC_SERVICE_TOKEN=... \\
    python benchmarks/context/assemble_load.py --profile live --addr 127.0.0.1:9092
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import secrets
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

# Allow running from repo root without installing the package.
_ROOT = Path(__file__).resolve().parents[2]
_CONTEXT = _ROOT / "services" / "context"
_PROTO_PY = _ROOT / "packages" / "proto" / "gen" / "python"
for path in (_CONTEXT, _PROTO_PY):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

import grpc
from grpc import aio as grpc_aio
from pydantic import SecretStr

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.grpc_auth import CALLER_AUTH_HEADER
from app.retrieval import ParallelRetriever
from app.server import _SERVICE_NAME, build_server

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"
AUTHORITY = "AuthService"
PRINCIPAL_ID = "benchmark-caller"
_P99_BUDGET_MS = 50.0


def _stub_service_token() -> str:
    """Throwaway caller token for the in-process stub; never a real credential."""
    return secrets.token_urlsafe(32)


# The live profile carries a reusable credential over plaintext gRPC, so the
# destination must be this host. IP literals only: a DNS name could resolve
# anywhere (including off-host) after the check.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def _addr_host(addr: str) -> str | None:
    """Host literal of a ``host:port`` / ``[v6]:port`` target; None if unparseable."""
    target = addr.strip()
    if target.startswith("["):
        host, bracket, rest = target.partition("]")
        if not bracket or not rest.startswith(":"):
            return None
        return host[1:] or None
    host, separator, _port = target.rpartition(":")
    if not separator or not host:
        return None
    return host


def _require_loopback_addr(addr: str) -> None:
    """Refuse a non-loopback ``--addr`` before any channel or credential use."""
    if _addr_host(addr) in _LOOPBACK_HOSTS:
        return
    raise SystemExit(
        f"live profile refuses --addr {addr!r}: it would send "
        "IBEX_CONTEXT_GRPC_SERVICE_TOKEN over plaintext gRPC to a non-loopback "
        "destination; use 127.0.0.1:<port> or [::1]:<port>"
    )


class _StubDirective:
    async def lookup(self, _org_id, _agent_id) -> DirectivePayload:
        await asyncio.sleep(0)
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


@dataclass(frozen=True, slots=True)
class _HitSpec:
    content: str
    category: str
    source: str
    confidence: float
    similarity: float


class _StubMemory:
    """In-process memory stub whose hits carry the run's tenant selectors."""

    def __init__(self, *, org: str, agent: str) -> None:
        self._org = org
        self._agent = agent

    def _one(self, spec: _HitSpec) -> MemoryHitPayload:
        return _hit(spec, org=self._org, agent=self._agent)

    async def get_hot_memories(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return [
            self._one(
                _HitSpec(
                    "hot preference " + ("x" * 64), "preference", "hot_cache", 0.9, 0.85
                )
            )
        ]

    async def search_memories(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return [
            self._one(
                _HitSpec("cold fact " + ("y" * 64), "factual", "vector", 0.8, 0.75)
            )
        ]


def _hit(spec: _HitSpec, *, org: str, agent: str) -> MemoryHitPayload:
    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=org,
        agent_id=agent,
        content=spec.content,
        category=spec.category,
        confidence=spec.confidence,
        similarity=spec.similarity,
        rank=1,
        source=spec.source,
    )


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * pct) - 1))
    return ordered[index]


def _assemble_request(pb2: object, *, org: str, agent: str) -> object:
    """Fresh request with a fresh principal: ``issued_at`` must be per call."""
    request = pb2.AssembleContextRequest(  # type: ignore[attr-defined]
        org_id=org,
        agent_id=agent,
        query="theme",
        model=MODEL,
        recent_messages=[pb2.Message(role="user", content="hello")],  # type: ignore[attr-defined]
    )
    principal = request.principal_context
    principal.org_id = org
    principal.agent_id = agent
    principal.principal_id = PRINCIPAL_ID
    principal.authority = AUTHORITY
    principal.issued_at.GetCurrentTime()
    return request


def _request_factory(
    pb2: object,
    *,
    org: str,
    agent: str,
) -> Callable[[], object]:
    return lambda: _assemble_request(pb2, org=org, agent=agent)


def _token_metadata(token: str) -> tuple[tuple[str, str], ...]:
    return ((CALLER_AUTH_HEADER, token),)


async def _one_call(
    stub: Callable[..., Awaitable[object]],
    request_factory: Callable[[], object],
    token: str,
) -> float | None:
    """Return latency_ms on success, None on RPC error."""
    t0 = time.perf_counter()
    try:
        await stub(request_factory(), timeout=1.0, metadata=_token_metadata(token))
    except grpc.aio.AioRpcError:
        return None
    return (time.perf_counter() - t0) * 1000.0


@dataclass(frozen=True, slots=True)
class _LoadPlan:
    duration_s: float
    target_rps: int


@dataclass(frozen=True, slots=True)
class _StubRun:
    """Everything the stub profile needs: caller token, selectors, load."""

    token: str
    org: str
    agent: str
    plan: _LoadPlan


@dataclass(frozen=True, slots=True)
class _LiveRun:
    """Everything the live profile needs: channel, caller token, selectors, load."""

    addr: str
    token: str
    org: str
    agent: str
    plan: _LoadPlan


@dataclass(frozen=True, slots=True)
class _DriveStats:
    latencies_ms: tuple[float, ...]
    attempted: int
    succeeded: int
    failed: int


async def _drive_open_loop(
    stub: Callable[..., Awaitable[object]],
    request_factory: Callable[[], object],
    token: str,
    plan: _LoadPlan,
) -> _DriveStats:
    """Launch RPCs on a fixed interval; await outstanding work after the window."""
    interval = 1.0 / max(1, plan.target_rps)
    start = time.perf_counter()
    deadline = start + plan.duration_s
    next_launch = start
    tasks: list[asyncio.Task[float | None]] = []
    while time.perf_counter() < deadline:
        now = time.perf_counter()
        if now < next_launch:
            await asyncio.sleep(next_launch - now)
            # Do not schedule past the measurement window after waking.
            if time.perf_counter() >= deadline:
                break
        tasks.append(asyncio.create_task(_one_call(stub, request_factory, token)))
        next_launch += interval
    results = await asyncio.gather(*tasks)
    latencies = tuple(ms for ms in results if ms is not None)
    attempted = len(results)
    succeeded = len(latencies)
    return _DriveStats(
        latencies_ms=latencies,
        attempted=attempted,
        succeeded=succeeded,
        failed=attempted - succeeded,
    )


def _stub_settings(token: str) -> ContextSettings:
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
        memory_base_url="",
        memory_api_token=SecretStr(""),
        grpc_service_token=SecretStr(token),
        redis_url="",
    )


async def _run_stub(run: _StubRun) -> _DriveStats:
    from ibex.context.v1 import context_pb2 as pb2

    settings = _stub_settings(run.token)
    retriever = ParallelRetriever(
        settings=settings,
        memory=_StubMemory(org=run.org, agent=run.agent),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    assembler = ContextAssembler(settings=settings, retriever=retriever)
    server, port = build_server(assembler, listen_addr="127.0.0.1:0", settings=settings)
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = channel.unary_unary(
                f"/{_SERVICE_NAME}/AssembleContext",
                request_serializer=pb2.AssembleContextRequest.SerializeToString,
                response_deserializer=pb2.AssembleContextResponse.FromString,
            )
            return await _drive_open_loop(
                stub,
                _request_factory(pb2, org=run.org, agent=run.agent),
                run.token,
                run.plan,
            )
    finally:
        await server.stop(grace=None)


async def _run_live(run: _LiveRun) -> _DriveStats:
    _require_loopback_addr(run.addr)
    if not run.token.strip():
        raise SystemExit(
            "live profile requires --token or IBEX_CONTEXT_GRPC_SERVICE_TOKEN (ADR-0096)"
        )
    from ibex.context.v1 import context_pb2 as pb2

    async with grpc_aio.insecure_channel(run.addr) as channel:
        stub = channel.unary_unary(
            f"/{_SERVICE_NAME}/AssembleContext",
            request_serializer=pb2.AssembleContextRequest.SerializeToString,
            response_deserializer=pb2.AssembleContextResponse.FromString,
        )
        return await _drive_open_loop(
            stub,
            _request_factory(pb2, org=run.org, agent=run.agent),
            run.token,
            run.plan,
        )


def _parse_error_rate(raw: str) -> float:
    """Argparse type for ``--max-error-rate``: finite float in inclusive [0, 1]."""
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"max-error-rate must be a number, got {raw!r}"
        ) from exc
    if not math.isfinite(value):
        _raise_error_rate_range(raw)
    if value < 0.0:
        _raise_error_rate_range(raw)
    if value > 1.0:
        _raise_error_rate_range(raw)
    return value


def _raise_error_rate_range(raw: str) -> None:
    raise argparse.ArgumentTypeError(
        f"max-error-rate must be a finite number in [0, 1], got {raw!r}"
    )


def _parse_uuid(raw: str) -> str:
    """Argparse type for ``--org-id``/``--agent-id``: a canonical lowercase UUID.

    Matches the ContextAssemblyService principal check, so a malformed selector
    fails here with a named flag instead of turning every RPC into an error.
    """
    try:
        parsed = UUID(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"must be a canonical UUID, got {raw!r}"
        ) from exc
    if str(parsed) != raw:
        raise argparse.ArgumentTypeError(f"must be a canonical UUID, got {raw!r}")
    return str(parsed)


def _parse_rps(raw: str) -> int:
    """Argparse type for ``--rps``: an integer >= 1."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"rps must be an integer, got {raw!r}"
        ) from exc
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"rps must be an integer >= 1, got {raw!r}"
        )
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("stub", "live"), default="stub")
    parser.add_argument(
        "--addr",
        default="127.0.0.1:9092",
        help=(
            "gRPC target for --profile live; loopback only "
            "(127.0.0.1:<port> or [::1]:<port>)."
        ),
    )
    parser.add_argument(
        "--rps",
        type=_parse_rps,
        default=500,
        help="Requests per second (default 500; minimum 1).",
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument(
        "--token",
        default=os.environ.get("IBEX_CONTEXT_GRPC_SERVICE_TOKEN", ""),
        help=(
            "Caller service token (ADR-0096), used by both profiles. Defaults "
            "to IBEX_CONTEXT_GRPC_SERVICE_TOKEN; the stub profile uses a "
            "throwaway token when this is empty."
        ),
    )
    parser.add_argument(
        "--org-id",
        type=_parse_uuid,
        default=str(ORG),
        help="Tenant asserted by the benchmark principal, in both profiles (canonical UUID).",
    )
    parser.add_argument(
        "--agent-id",
        type=_parse_uuid,
        default=str(AGENT),
        help="Agent asserted by the benchmark principal, in both profiles (canonical UUID).",
    )
    parser.add_argument("--json", type=Path, help="Write the profile-tagged result to this path.")
    parser.add_argument(
        "--max-error-rate",
        type=_parse_error_rate,
        default=0.0,
        help="Fail when failed/attempted exceeds this fraction (default 0; range 0..1).",
    )
    return parser.parse_args()


def _profile_stats(args: argparse.Namespace) -> _DriveStats:
    """Drive the profile selected by ``--profile`` and return its measurements."""
    if args.profile == "stub":
        return asyncio.run(
            _run_stub(
                _StubRun(
                    token=args.token or _stub_service_token(),
                    org=args.org_id,
                    agent=args.agent_id,
                    plan=_LoadPlan(args.duration, args.rps),
                )
            )
        )
    return asyncio.run(
        _run_live(
            _LiveRun(
                addr=args.addr,
                token=args.token,
                org=args.org_id,
                agent=args.agent_id,
                plan=_LoadPlan(args.duration, args.rps),
            )
        )
    )


def main() -> int:
    args = _parse_args()
    stats = _profile_stats(args)

    samples = list(stats.latencies_ms)
    error_rate = (
        (stats.failed / stats.attempted) if stats.attempted else 1.0
    )
    print(
        f"context_assemble_load profile={args.profile} rps={args.rps} "
        f"duration_s={args.duration} attempted={stats.attempted} "
        f"succeeded={stats.succeeded} failed={stats.failed} "
        f"error_rate={error_rate:.4f}"
    )
    if not samples:
        print("no successful samples", file=sys.stderr)
        return 2

    p50 = _percentile(samples, 0.50)
    p95 = _percentile(samples, 0.95)
    p99 = _percentile(samples, 0.99)
    mean = statistics.fmean(samples)
    print(
        f"latencies mean_ms={mean:.3f} p50_ms={p50:.3f} "
        f"p95_ms={p95:.3f} p99_ms={p99:.3f}"
    )
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "profile": args.profile,
                    "rps": args.rps,
                    "duration_s": args.duration,
                    "attempted": stats.attempted,
                    "succeeded": stats.succeeded,
                    "failed": stats.failed,
                    "error_rate": error_rate,
                    "mean_ms": mean,
                    "p50_ms": p50,
                    "p95_ms": p95,
                    "p99_ms": p99,
                },
                indent=2,
                allow_nan=False,
            ) + "\n",
            encoding="utf-8",
        )
    if error_rate > args.max_error_rate:
        print(
            f"FAIL: error_rate {error_rate:.4f} exceeds max {args.max_error_rate:.4f}",
            file=sys.stderr,
        )
        return 1
    if args.profile == "stub" and p99 >= _P99_BUDGET_MS:
        print(
            f"FAIL: stub p99 {p99:.3f}ms exceeds {_P99_BUDGET_MS}ms",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
