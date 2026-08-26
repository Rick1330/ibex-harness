"""HNSW corpus seed + search-matrix measurement helpers."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import SEARCH_SQL, PgVectorStore

from corpus import (
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
from plan_assert import PlanAssertionError, assert_hnsw_index_used
from synth import (
    bootstrap_p95_ci,
    percentile,
    perturb,
    unit_vector,
    vec_literal,
)

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


@dataclass(frozen=True, slots=True)
class ExplainParams:
    """Args for EXPLAIN ANALYZE of a single search."""

    org_id: UUID
    agent_id: UUID
    query: list[float]
    ef_search: int
    min_similarity: float
    iterative_scan: str
    limit: int = 10


@dataclass(frozen=True, slots=True)
class SizeRunParams:
    """Timed search pass over a seeded corpus (after EXPLAIN / warm-up)."""

    org_id: UUID
    agent_id: UUID
    size: int
    query_count: int
    ef_search: int
    min_similarity: float
    iterative_scan: str
    index_build_mode: str
    plan_summary: dict[str, Any]
    idx_scan_delta: int
    row_count: int


@dataclass(frozen=True, slots=True)
class MatrixConfig:
    """Outer search-matrix knobs (sizes × index/build × iterative × min_sim)."""

    sizes: list[int]
    index_modes: list[str]
    iterative_modes: list[str]
    min_sims: list[float]
    ef_search: int
    queries: int | None


async def _explain_search(engine: AsyncEngine, params: ExplainParams) -> dict[str, Any]:
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
            {"org_id": str(params.org_id)},
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('hnsw.ef_search', :ef, true)"
            ),
            {"ef": str(params.ef_search)},
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('hnsw.iterative_scan', :mode, true)"
            ),
            {"mode": params.iterative_scan},
        )
        result = await conn.execute(
            text(explain_sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {
                "query": vec_literal(params.query),
                "org_id": str(params.org_id),
                "agent_id": str(params.agent_id),
                "min_similarity": params.min_similarity,
                "limit": params.limit,
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


def _search_request(params: SizeRunParams, query: list[float]) -> SearchRequest:
    return SearchRequest(
        org_id=params.org_id,
        agent_id=params.agent_id,
        query_embedding=query,
        limit=10,
        min_similarity=params.min_similarity,
        ef_search=params.ef_search,
        iterative_scan=params.iterative_scan,
    )


async def _warmup_searches(store: PgVectorStore, params: SizeRunParams) -> None:
    for q in range(_WARMUP_QUERIES):
        idx = ((q * 97) + _WARMUP_INDEX_OFFSET) % params.size
        await store.search(
            _search_request(params, perturb(unit_vector(idx), seed=idx))
        )


async def _timed_search_pass(
    store: PgVectorStore, params: SizeRunParams
) -> tuple[list[float], int]:
    latencies: list[float] = []
    hits = 0
    for q in range(params.query_count):
        idx = (q * 97) % params.size
        query = perturb(unit_vector(idx), seed=idx)
        t0 = time.perf_counter()
        results = await store.search(_search_request(params, query))
        latencies.append((time.perf_counter() - t0) * 1000.0)
        top_ids = {hit.memory_id for hit in results}
        if memory_id_for(params.org_id, idx) in top_ids:
            hits += 1
    return latencies, hits


def _plan_fields(plan: dict[str, Any]) -> tuple[str, str, int, int]:
    """Flatten EXPLAIN summary knobs used in SizeResult (keeps _run_size simple)."""
    return (
        str(plan.get("node_type") or ""),
        str(plan.get("index_name") or ""),
        int(plan.get("shared_hit_blocks") or 0),
        int(plan.get("shared_read_blocks") or 0),
    )


async def _run_size(store: PgVectorStore, params: SizeRunParams) -> SizeResult:
    await _warmup_searches(store, params)
    latencies, hits = await _timed_search_pass(store, params)
    ordered = sorted(latencies)
    ci_lo, ci_hi = bootstrap_p95_ci(latencies)
    node_type, index_name, hit_blocks, read_blocks = _plan_fields(params.plan_summary)
    return SizeResult(
        corpus_size=params.size,
        query_count=params.query_count,
        recall_at_10=hits / params.query_count,
        latency_ms_p50=percentile(ordered, 50),
        latency_ms_p95=percentile(ordered, 95),
        latency_ms_p99=percentile(ordered, 99),
        latency_ms_p95_ci_low=ci_lo,
        latency_ms_p95_ci_high=ci_hi,
        ef_search=params.ef_search,
        min_similarity=params.min_similarity,
        iterative_scan=params.iterative_scan,
        index_build_mode=params.index_build_mode,
        plan_node_type=node_type,
        plan_index_name=index_name,
        shared_hit_blocks=hit_blocks,
        shared_read_blocks=read_blocks,
        idx_scan_delta=params.idx_scan_delta,
        row_count_verified=params.row_count,
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
        ExplainParams(
            org_id=cell.org_id,
            agent_id=cell.agent_id,
            query=unit_vector(0),
            ef_search=cell.ef_search,
            min_similarity=cell.min_similarity,
            iterative_scan=cell.iterative_scan,
        ),
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
        SizeRunParams(
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
        ),
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


def _cells_for_corpus(
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
    count: int,
    index_build_mode: str,
    config: MatrixConfig,
) -> list[CellParams]:
    cells: list[CellParams] = []
    first_cell = True
    for iterative_scan in config.iterative_modes:
        for min_similarity in config.min_sims:
            cells.append(
                CellParams(
                    org_id=org_id,
                    agent_id=agent_id,
                    size=size,
                    ef_search=config.ef_search,
                    min_similarity=min_similarity,
                    iterative_scan=iterative_scan,
                    index_build_mode=index_build_mode,
                    query_count=config.queries,
                    row_count=count,
                    prewarm=first_cell,
                )
            )
            first_cell = False
    return cells


async def _measure_corpus(
    engine: AsyncEngine,
    store: PgVectorStore,
    factory: async_sessionmaker[AsyncSession],
    *,
    size: int,
    index_build_mode: str,
    config: MatrixConfig,
) -> list[SizeResult]:
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
        raise RuntimeError(f"row count after upsert expected {size}, got {count}")
    return [
        await _measure_cell(engine, store, cell)
        for cell in _cells_for_corpus(
            org_id=org_id,
            agent_id=agent_id,
            size=size,
            count=count,
            index_build_mode=index_build_mode,
            config=config,
        )
    ]


async def run_search_matrix(
    engine: AsyncEngine,
    store: PgVectorStore,
    factory: async_sessionmaker[AsyncSession],
    config: MatrixConfig,
) -> list[SizeResult]:
    results: list[SizeResult] = []
    await reset_memories(engine)
    await ensure_hnsw_index(engine, maintenance_work_mem=_maintenance_work_mem())
    for size in config.sizes:
        for index_build_mode in config.index_modes:
            results.extend(
                await _measure_corpus(
                    engine,
                    store,
                    factory,
                    size=size,
                    index_build_mode=index_build_mode,
                    config=config,
                )
            )
    return results

