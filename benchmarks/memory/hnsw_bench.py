"""HNSW recall@10 + latency benches against live pgvector (m3.2.1).

Seeds synthetic unit vectors with planted near-neighbors, then measures
PgVectorStore search latency and recall@10 at configurable corpus sizes.

Methodology gates (hard fail):
- TRUNCATE between sizes + script start; assert exact row count
- ANALYZE after COPY
- EXPLAIN must use idx_memories_embedding_hnsw; pg_stat idx_scan must move
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import SEARCH_SQL, PgVectorStore

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
from corpus import (  # noqa: E402
    analyze_memories,
    bulk_insert_memories,
    count_memories,
    drop_hnsw_index,
    ensure_hnsw_index,
    idx_scan_count,
    memory_id_for,
    reset_memories,
    seed_org,
    try_prewarm,
)
from path_guard import UnsafePathError, resolve_raw_bench_path  # noqa: E402
from plan_assert import PlanAssertionError, assert_hnsw_index_used  # noqa: E402
from synth import (  # noqa: E402
    ACTIVE_DIMS,
    DIM,
    bootstrap_p95_ci,
    percentile,
    perturb,
    unit_vector,
    vec_literal,
)

_DEFAULT_EF_SEARCH = 40
_DEFAULT_SIZES = (10_000, 100_000)
_QUERY_COUNTS = {10_000: 500, 100_000: 200, 1_000_000: 200}
_WARMUP_QUERIES = 100
# Offset so warm-up indices never share the timed `(q * 97) % size` sequence.
_WARMUP_INDEX_OFFSET = 10_007


def _maintenance_work_mem() -> str:
    return os.environ.get("MEMORY_BENCH_MAINTENANCE_WORK_MEM", "2GB")


@dataclass(frozen=True, slots=True)
class SizeResult:
    corpus_size: int
    query_count: int
    recall_at_10: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_p99: float
    latency_ms_p95_ci_low: float
    latency_ms_p95_ci_high: float
    ef_search: int
    min_similarity: float
    iterative_scan: str
    index_build_mode: str
    plan_node_type: str
    plan_index_name: str
    shared_hit_blocks: int
    shared_read_blocks: int
    idx_scan_delta: int
    row_count_verified: int


@dataclass(frozen=True, slots=True)
class CellParams:
    """Search-knob cell on an already-seeded corpus (reduces arg sprawl)."""

    org_id: UUID
    agent_id: UUID
    size: int
    ef_search: int
    min_similarity: float
    iterative_scan: str
    index_build_mode: str
    query_count: int | None
    row_count: int
    prewarm: bool


async def _explain_search(
    engine: AsyncEngine,
    *,
    org_id: UUID,
    agent_id: UUID,
    query: list[float],
    ef_search: int,
    min_similarity: float,
    iterative_scan: str,
    limit: int = 10,
) -> dict[str, Any]:
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {SEARCH_SQL}"
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.current_org_id', :org_id, true)"
            ),
            {"org_id": str(org_id)},
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('hnsw.ef_search', :ef, true)"
            ),
            {"ef": str(ef_search)},
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('hnsw.iterative_scan', :mode, true)"
            ),
            {"mode": iterative_scan},
        )
        result = await conn.execute(
            text(explain_sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {
                "query": vec_literal(query),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "min_similarity": min_similarity,
                "limit": limit,
            },
        )
        payload = result.scalar()
    if isinstance(payload, str):
        payload = json.loads(payload)
    summary = assert_hnsw_index_used(payload)
    print(
        f"  EXPLAIN ok node={summary['node_type']} index={summary['index_name']} "
        f"hits={summary['shared_hit_blocks']} reads={summary['shared_read_blocks']} "
        f"exec_ms={summary.get('execution_time_ms')}",
        flush=True,
    )
    return summary


async def _run_size(
    store: PgVectorStore,
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
    query_count: int,
    ef_search: int,
    min_similarity: float,
    iterative_scan: str,
    index_build_mode: str,
    plan_summary: dict[str, Any],
    idx_scan_delta: int,
    row_count: int,
) -> SizeResult:
    for q in range(_WARMUP_QUERIES):
        idx = ((q * 97) + _WARMUP_INDEX_OFFSET) % size
        await store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=perturb(unit_vector(idx), seed=idx),
                limit=10,
                min_similarity=min_similarity,
                ef_search=ef_search,
                iterative_scan=iterative_scan,
            )
        )

    latencies: list[float] = []
    hits = 0
    for q in range(query_count):
        idx = (q * 97) % size
        query = perturb(unit_vector(idx), seed=idx)
        t0 = time.perf_counter()
        results = await store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=query,
                limit=10,
                min_similarity=min_similarity,
                ef_search=ef_search,
                iterative_scan=iterative_scan,
            )
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
        top_ids = {hit.memory_id for hit in results}
        if memory_id_for(org_id, idx) in top_ids:
            hits += 1

    ordered = sorted(latencies)
    ci_lo, ci_hi = bootstrap_p95_ci(latencies)
    return SizeResult(
        corpus_size=size,
        query_count=query_count,
        recall_at_10=hits / query_count,
        latency_ms_p50=percentile(ordered, 50),
        latency_ms_p95=percentile(ordered, 95),
        latency_ms_p99=percentile(ordered, 99),
        latency_ms_p95_ci_low=ci_lo,
        latency_ms_p95_ci_high=ci_hi,
        ef_search=ef_search,
        min_similarity=min_similarity,
        iterative_scan=iterative_scan,
        index_build_mode=index_build_mode,
        plan_node_type=str(plan_summary.get("node_type") or ""),
        plan_index_name=str(plan_summary.get("index_name") or ""),
        shared_hit_blocks=int(plan_summary.get("shared_hit_blocks") or 0),
        shared_read_blocks=int(plan_summary.get("shared_read_blocks") or 0),
        idx_scan_delta=idx_scan_delta,
        row_count_verified=row_count,
    )


async def _prepare_corpus(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    *,
    size: int,
    index_build_mode: str,
) -> tuple[UUID, UUID, float]:
    await reset_memories(engine)
    if index_build_mode == "bulk":
        await drop_hnsw_index(engine)
    else:
        await ensure_hnsw_index(engine, maintenance_work_mem=_maintenance_work_mem())

    org_id, agent_id = await seed_org(factory)
    print(f"seeding corpus_size={size} mode={index_build_mode} …", flush=True)
    t0 = time.perf_counter()
    await bulk_insert_memories(engine, org_id=org_id, agent_id=agent_id, size=size)
    if index_build_mode == "bulk":
        print("  CREATE INDEX (bulk) …", flush=True)
        await ensure_hnsw_index(engine, maintenance_work_mem=_maintenance_work_mem())
    build_s = time.perf_counter() - t0
    await analyze_memories(engine)
    count = await count_memories(engine)
    if count != size:
        msg = f"row count after seed expected {size}, got {count}"
        raise RuntimeError(msg)
    print(f"  row_count={count} build_s={build_s:.2f} ANALYZE ok", flush=True)
    return org_id, agent_id, build_s


async def _measure_cell(engine: AsyncEngine, store: PgVectorStore, cell: CellParams) -> SizeResult:
    """Time one (min_similarity × iterative_scan) cell on an already-seeded corpus."""
    plan_summary = await _explain_search(
        engine,
        org_id=cell.org_id,
        agent_id=cell.agent_id,
        query=unit_vector(0),
        ef_search=cell.ef_search,
        min_similarity=cell.min_similarity,
        iterative_scan=cell.iterative_scan,
    )
    if cell.prewarm:
        await try_prewarm(engine)

    qn = cell.query_count if cell.query_count is not None else _QUERY_COUNTS.get(cell.size, 200)
    before = await idx_scan_count(engine)
    print(
        f"searching size={cell.size} ef={cell.ef_search} min_sim={cell.min_similarity} "
        f"iter={cell.iterative_scan} queries={qn} warmup={_WARMUP_QUERIES} …",
        flush=True,
    )
    result = await _run_size(
        store,
        org_id=cell.org_id,
        agent_id=cell.agent_id,
        size=cell.size,
        query_count=qn,
        ef_search=cell.ef_search,
        min_similarity=cell.min_similarity,
        iterative_scan=cell.iterative_scan,
        index_build_mode=cell.index_build_mode,
        plan_summary=plan_summary,
        idx_scan_delta=0,
        row_count=cell.row_count,
    )
    after = await idx_scan_count(engine)
    delta = after - before
    if delta < 1:
        msg = (
            f"pg_stat_user_indexes idx_scan did not increase "
            f"(before={before}, after={after}) — HNSW index not used"
        )
        raise PlanAssertionError(msg)
    result = SizeResult(**{**asdict(result), "idx_scan_delta": delta})
    print(
        f"size={cell.size} recall@10={result.recall_at_10:.4f} "
        f"p95_ms={result.latency_ms_p95:.2f} "
        f"p95_ci=[{result.latency_ms_p95_ci_low:.2f},{result.latency_ms_p95_ci_high:.2f}] "
        f"idx_scan_delta={delta}",
        flush=True,
    )
    return result


async def _run_search_matrix(
    engine: AsyncEngine,
    store: PgVectorStore,
    factory: async_sessionmaker[AsyncSession],
    *,
    sizes: list[int],
    index_modes: list[str],
    iterative_modes: list[str],
    min_sims: list[float],
    ef_search: int,
    queries: int | None,
) -> list[SizeResult]:
    results: list[SizeResult] = []
    await reset_memories(engine)
    await ensure_hnsw_index(engine, maintenance_work_mem=_maintenance_work_mem())
    for size in sizes:
        for index_build_mode in index_modes:
            org_id, agent_id, _build_s = await _prepare_corpus(
                engine, factory, size=size, index_build_mode=index_build_mode
            )
            await store.upsert(
                UpsertRequest(
                    memory_id=memory_id_for(org_id, 0),
                    org_id=org_id,
                    embedding=unit_vector(0),
                    embedding_model="bench-synthetic",
                )
            )
            count = await count_memories(engine)
            if count != size:
                msg = f"row count after upsert expected {size}, got {count}"
                raise RuntimeError(msg)

            first_cell = True
            for iterative_scan in iterative_modes:
                for min_similarity in min_sims:
                    cell = CellParams(
                        org_id=org_id,
                        agent_id=agent_id,
                        size=size,
                        ef_search=ef_search,
                        min_similarity=min_similarity,
                        iterative_scan=iterative_scan,
                        index_build_mode=index_build_mode,
                        query_count=queries,
                        row_count=count,
                        prewarm=first_cell,
                    )
                    results.append(await _measure_cell(engine, store, cell))
                    first_cell = False
    return results


def _build_payload(
    *,
    args: argparse.Namespace,
    results: list[SizeResult],
    iterative_modes: list[str],
    min_sims: list[float],
    index_modes: list[str],
) -> dict[str, object]:
    return {
        "benchmark": "hnsw_recall_latency",
        "generated_at": datetime.now(UTC).isoformat(),
        "methodology": {
            "index": "idx_memories_embedding_hnsw (m=16, ef_construction=64, cosine)",
            "ef_search": args.ef_search,
            "dim": DIM,
            "active_dims": ACTIVE_DIMS,
            "warmup_queries": _WARMUP_QUERIES,
            "truncate_between_sizes": True,
            "reuse_corpus_across_search_knobs": True,
            "analyze_after_copy": True,
            "explain_requires_hnsw": True,
            "recall": "planted near-neighbor must appear in top-10",
            "latency": "wall-clock PgVectorStore.search including SET LOCAL",
            "iterative_scan_modes": iterative_modes,
            "min_similarity_values": min_sims,
            "index_build_modes": index_modes,
        },
        "results": [asdict(r) for r in results],
        "mean_recall_at_10": statistics.fmean(r.recall_at_10 for r in results)
        if results
        else 0.0,
    }


async def _benchmark(args: argparse.Namespace) -> dict[str, object]:
    dsn = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not dsn:
        msg = "IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required"
        raise RuntimeError(msg)

    settings = Settings(database_url=dsn, hnsw_ef_search=args.ef_search)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PgVectorStore(factory, settings)

    iterative_modes = list(args.iterative_scan)
    min_sims = list(args.min_similarity)
    index_modes = list(args.index_build_mode)
    try:
        results = await _run_search_matrix(
            engine,
            store,
            factory,
            sizes=list(args.sizes),
            index_modes=index_modes,
            iterative_modes=iterative_modes,
            min_sims=min_sims,
            ef_search=args.ef_search,
            queries=args.queries,
        )
    finally:
        await engine.dispose()

    payload = _build_payload(
        args=args,
        results=results,
        iterative_modes=iterative_modes,
        min_sims=min_sims,
        index_modes=index_modes,
    )
    out = resolve_raw_bench_path(args.output, must_exist=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=list(_DEFAULT_SIZES),
        help="Corpus sizes (default: 10K 100K; avoid 1M on laptop)",
    )
    parser.add_argument(
        "--ef-search",
        type=int,
        default=_DEFAULT_EF_SEARCH,
        help="hnsw.ef_search (default: 40 — roadmap SLA)",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        nargs="+",
        default=[0.0, 0.70],
        help="SearchRequest min_similarity values to matrix (default: 0.0 0.70)",
    )
    parser.add_argument(
        "--iterative-scan",
        type=str,
        nargs="+",
        default=["off", "relaxed_order"],
        choices=["off", "relaxed_order", "strict_order"],
        help="hnsw.iterative_scan modes to matrix",
    )
    parser.add_argument(
        "--index-build-mode",
        type=str,
        nargs="+",
        default=["incremental"],
        choices=["incremental", "bulk"],
        help="incremental = COPY into existing HNSW; bulk = COPY then CREATE INDEX",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=None,
        help="Override timed query count for all sizes",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/memory/output/hnsw_recall_latency.json"),
        help="Workspace-relative JSON output path",
    )
    args = parser.parse_args()
    if args.ef_search < 1:
        parser.error("--ef-search must be >= 1")
    try:
        asyncio.run(_benchmark(args))
    except UnsafePathError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
