#!/usr/bin/env python3
"""Write-pipeline wall-clock benchmark (MemoryWriteOrchestrator.create)."""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_BENCH_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_DIR = _BENCH_ROOT / "services" / "memory"
_BENCH_MEMORY = _BENCH_ROOT / "benchmarks" / "memory"
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))

from app.config import Settings  # noqa: E402
from app.db import create_engine, create_session_factory  # noqa: E402
from app.vectorstore.pgvector_store import PgVectorStore  # noqa: E402
from app.write.models import CreateMemoryCommand  # noqa: E402
from path_guard import resolve_bench_output_path, write_bench_output_json  # noqa: E402
from tests.integration.conftest import seed_org_agent_memory  # noqa: E402
from tests.integration.write_orchestrator_support import (  # noqa: E402
    OrchestratorTestDeps,
    build_orchestrator,
    ensure_pii_ready,
)

_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = _DIR / "output" / "latest.json"
DEFAULT_ITERATIONS = 40


def _async_dsn() -> str:
    raw = (
        os.getenv("IBEX_MEMORY_DATABASE_URL")
        or os.getenv("POSTGRES_TEST_DSN")
        or os.getenv("POSTGRES_DSN")
    )
    if not raw:
        msg = "IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required"
        raise RuntimeError(msg)
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


async def run_bench(*, iterations: int) -> dict:
    settings = Settings(database_url=_async_dsn())
    engine = create_engine(settings)
    try:
        session_factory = create_session_factory(engine)
        store = PgVectorStore(session_factory, settings)
        org_id, agent_id, _ = await seed_org_agent_memory(
            session_factory, content="write pipeline bench seed"
        )
        orch = build_orchestrator(
            OrchestratorTestDeps(
                session_factory=session_factory,
                settings=settings,
                store=store,
            )
        )
        await ensure_pii_ready(orch)

        latencies_ms: list[float] = []
        for index in range(iterations):
            cmd = CreateMemoryCommand(
                org_id=org_id,
                agent_id=agent_id,
                content=(
                    f"Wall-clock benchmark iteration {index} "
                    f"with unique marker {uuid4().hex} "
                    f"recorded at nanosecond {time.time_ns()}."
                ),
                category="factual",
                confidence=0.85,
            )
            start = time.perf_counter()
            await orch.create(cmd)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies_ms.append(elapsed_ms)

        result = {
            "benchmark": "write_pipeline",
            "schema_version": 1,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "iterations": iterations,
            "metrics": {
                "latency_ms_p50": statistics.median(latencies_ms),
                "latency_ms_p95": _percentile(latencies_ms, 95),
                "latency_ms_p99": _percentile(latencies_ms, 99),
            },
            "latencies_ms": latencies_ms,
        }
        return result
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    args = parser.parse_args(argv)
    resolve_bench_output_path(args.output, bench_dir=_DIR)
    result = asyncio.run(run_bench(iterations=args.iterations))
    write_bench_output_json(args.output, bench_dir=_DIR, payload=result)
    metrics = result["metrics"]
    print(
        f"write_pipeline: p50={metrics['latency_ms_p50']:.2f}ms "
        f"p95={metrics['latency_ms_p95']:.2f}ms "
        f"p99={metrics['latency_ms_p99']:.2f}ms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
