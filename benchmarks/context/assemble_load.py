#!/usr/bin/env python3
"""AssembleContext gRPC load harness (milestone 3.5.C.6 / ADR-0034 methodology).

Stub profile (default): in-process server with fast memory stubs — CI-friendly
latency signal; asserts p99 < 50ms at the configured target RPS.

Live profile: point ``--addr`` at a running ContextAssemblyService backed by a
100K-memory corpus (seed via ``benchmarks/memory`` HNSW tooling). Live runs do
not fail the process on p99; they print percentiles for PR documentation.

Examples::

  PYTHONPATH=packages/proto/gen/python:services/context \\
    python benchmarks/context/assemble_load.py --profile stub --rps 500 --duration 10

  PYTHONPATH=packages/proto/gen/python:services/context \\
    python benchmarks/context/assemble_load.py --profile live --addr 127.0.0.1:9092
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

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

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.retrieval import ParallelRetriever
from app.server import _SERVICE_NAME, build_server

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"
_P99_BUDGET_MS = 50.0


class _StubDirective:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


class _StubMemory:
    async def get_hot_memories(self, *_args, **_kwargs):
        return [_hit("hot preference " + ("x" * 64), "preference", "hot_cache", 0.9, 0.85)]

    async def search_memories(self, *_args, **_kwargs):
        return [_hit("cold fact " + ("y" * 64), "factual", "vector", 0.8, 0.75)]


def _hit(
    content: str,
    category: str,
    source: str,
    confidence: float,
    similarity: float,
) -> MemoryHitPayload:
    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(ORG),
        agent_id=str(AGENT),
        content=content,
        category=category,
        confidence=confidence,
        similarity=similarity,
        rank=1,
        source=source,
    )


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * pct) - 1))
    return ordered[index]


async def _run_stub(duration_s: float, target_rps: int) -> list[float]:
    from ibex.context.v1 import context_pb2 as pb2

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
    retriever = ParallelRetriever(
        settings=settings,
        memory=_StubMemory(),  # type: ignore[arg-type]
        directive=_StubDirective(),
    )
    assembler = ContextAssembler(settings=settings, retriever=retriever)
    server, port = build_server(assembler, listen_addr="127.0.0.1:0")
    await server.start()
    samples: list[float] = []
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
            interval = 1.0 / max(1, target_rps)
            deadline = time.perf_counter() + duration_s
            while time.perf_counter() < deadline:
                loop_start = time.perf_counter()
                t0 = time.perf_counter()
                await stub(req, timeout=1.0)
                samples.append((time.perf_counter() - t0) * 1000.0)
                sleep_for = interval - (time.perf_counter() - loop_start)
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
    finally:
        await server.stop(grace=None)
    return samples


async def _run_live(addr: str, duration_s: float, target_rps: int) -> list[float]:
    from ibex.context.v1 import context_pb2 as pb2

    samples: list[float] = []
    async with grpc_aio.insecure_channel(addr) as channel:
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
        interval = 1.0 / max(1, target_rps)
        deadline = time.perf_counter() + duration_s
        while time.perf_counter() < deadline:
            loop_start = time.perf_counter()
            t0 = time.perf_counter()
            try:
                await stub(req, timeout=1.0)
                samples.append((time.perf_counter() - t0) * 1000.0)
            except grpc.aio.AioRpcError as exc:
                print(f"rpc_error code={exc.code()} details={exc.details()}", flush=True)
            sleep_for = interval - (time.perf_counter() - loop_start)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("stub", "live"), default="stub")
    parser.add_argument("--addr", default="127.0.0.1:9092")
    parser.add_argument("--rps", type=int, default=500)
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()

    if args.profile == "stub":
        samples = asyncio.run(_run_stub(args.duration, args.rps))
    else:
        samples = asyncio.run(_run_live(args.addr, args.duration, args.rps))

    if not samples:
        print("no successful samples", file=sys.stderr)
        return 2

    p50 = _percentile(samples, 0.50)
    p95 = _percentile(samples, 0.95)
    p99 = _percentile(samples, 0.99)
    mean = statistics.fmean(samples)
    print(
        f"context_assemble_load profile={args.profile} rps={args.rps} "
        f"duration_s={args.duration} n={len(samples)} "
        f"mean_ms={mean:.3f} p50_ms={p50:.3f} p95_ms={p95:.3f} p99_ms={p99:.3f}"
    )
    if args.profile == "stub" and p99 >= _P99_BUDGET_MS:
        print(
            f"FAIL: stub p99 {p99:.3f}ms exceeds {_P99_BUDGET_MS}ms",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
