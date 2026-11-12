#!/usr/bin/env python3
"""Ranking-quality benchmark — gold set via MemoryReadRepository.find_similar."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_BENCH_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_DIR = _BENCH_ROOT / "services" / "memory"
_BENCH_MEMORY = _BENCH_ROOT / "benchmarks" / "memory"
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))

# The imports below sit after a sys.path insertion rather than at the top of the file, because the
# bench imports both the memory service and its own siblings. The per-import E402 suppressions
# that used to sit here were inert (E402 is not selected) and RUF100 rejects them, so the reason
# is recorded once, here.
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.repository import MemoryReadRepository
from app.vectorstore.pgvector_store import PgVectorStore
from path_guard import resolve_bench_input_path, write_bench_output_json
from provenance import GOLD_V1_SET_PATH as PROVENANCE_GOLD_V1_PATH
from provenance import provenance_record
from tests.integration.conftest import zero_embedding

_RANK_DIR = Path(__file__).resolve().parent
if str(_RANK_DIR) not in sys.path:
    sys.path.insert(0, str(_RANK_DIR))

# Same reason as above: these siblings are only importable after the ranking dir is on sys.path.
from metrics import (
    expected_order_match,
    macro_mean,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from relevance_gate_probe import evaluate_relevance_gate_probe
from seed import (
    GOLD_SET_PATH,
    GoldSeedResult,
    load_gold_set,
    seed_gold_set,
)
from validate_gold_set import validate_gold_set

DEFAULT_OUTPUT = _RANK_DIR / "output" / "latest.json"
# The v1 corpus names itself in its payload; the published record repeats that name.
_V1_GOLD_SET_NAME = "v1"


def require_v1_gold_set(gold_path: Path, payload: Mapping[str, object]) -> None:
    """Refuse a corpus whose provenance could not be recorded honestly.

    The recorded ``gold_set_hash`` is the digest of the v1 corpus at its canonical path, so this
    producer accepts that file and no other: a copy somewhere else would be seeded and measured
    but published under the canonical file's hash. The corpus must also name itself the v1 set,
    because the record is scored and published as v1 -- measuring another corpus and labelling it
    v1 would name a corpus it was not measured on.
    """
    if gold_path.name != PROVENANCE_GOLD_V1_PATH.name:
        raise RuntimeError(
            f"gold set {gold_path.name!r} is not {PROVENANCE_GOLD_V1_PATH.name!r}; "
            "this producer records provenance for the v1 corpus only"
        )
    if gold_path.resolve() != PROVENANCE_GOLD_V1_PATH.resolve():
        raise RuntimeError(
            f"gold set {gold_path} is not the canonical {PROVENANCE_GOLD_V1_PATH}: the recorded "
            "provenance hashes that file, so a copy would publish another file's hash"
        )
    declared = payload.get("gold_set")
    if declared != _V1_GOLD_SET_NAME:
        raise RuntimeError(
            f"gold set declares gold_set {declared!r}, expected {_V1_GOLD_SET_NAME!r}; "
            "the published record would name a corpus it was not measured on"
        )


@dataclass(frozen=True, slots=True)
class QueryEvalContext:
    seed: GoldSeedResult
    id_to_key: dict[str, str]
    mem_by_key: dict[str, dict]


def _configured_dsn() -> str:
    """The DSN from the environment, or a refusal naming the variables that would set it."""
    raw = (
        os.getenv("IBEX_MEMORY_DATABASE_URL")
        or os.getenv("POSTGRES_TEST_DSN")
        or os.getenv("POSTGRES_DSN")
    )
    if raw:
        return raw
    msg = "IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required"
    raise RuntimeError(msg)


def _async_dsn() -> str:
    raw = _configured_dsn()
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


def _ranked_keys(results: Sequence[MemorySearchResult], id_to_key: dict[str, str]) -> list[str]:
    """The corpus keys for the hits, in the order the repository ranked them."""
    return [id_to_key[str(hit.id)] for hit in results if str(hit.id) in id_to_key]


def _top_category_ok(
    ranked_keys: list[str], mem_by_key: dict[str, dict], expected_top: str
) -> bool:
    """Whether the first ranked memory carries the category the query expects on top."""
    return bool(ranked_keys) and mem_by_key[ranked_keys[0]]["category"] == expected_top


def _query_metrics(ranked_keys: list[str], expected_keys: list[str]) -> dict:
    """The four ranking metrics for one query, each from the shared metric module."""
    return {
        "precision_at_5": precision_at_k(ranked_keys, expected_keys, 5),
        "recall_at_10": recall_at_k(ranked_keys, expected_keys, 10),
        "mrr": mean_reciprocal_rank(ranked_keys, expected_keys),
        "expected_order_match": expected_order_match(ranked_keys, expected_keys),
    }


async def _ranked_keys_for_query(
    repo: MemoryReadRepository, row: dict, ctx: QueryEvalContext
) -> list[str]:
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=ctx.seed.org_id,
            agent_id=ctx.seed.agent_id,
            query_embedding=zero_embedding(hotspot=int(row["query_hotspot"])),
            query_text=str(row["query_text"]),
            limit=10,
            min_similarity=0.5,
        )
    )
    return _ranked_keys(results, ctx.id_to_key)


async def _evaluate_query(
    repo: MemoryReadRepository,
    row: dict,
    ctx: QueryEvalContext,
) -> tuple[dict, bool]:
    expected_keys = list(row["expected_content_keys"])
    expected_top = str(row.get("expected_top_category", ""))
    ranked_keys = await _ranked_keys_for_query(repo, row, ctx)
    top_ok = _top_category_ok(ranked_keys, ctx.mem_by_key, expected_top)
    return (
        {
            "query_id": str(row["query_id"]),
            **_query_metrics(ranked_keys, expected_keys),
            "top_category_ok": top_ok,
            "ranked_content_keys": ranked_keys,
        },
        top_ok,
    )


def _aggregate_metrics(per_query: list[dict], *, top_cat_hits: int) -> dict:
    p5_vals = [float(q["precision_at_5"]) for q in per_query]
    r10_vals = [float(q["recall_at_10"]) for q in per_query]
    mrr_vals = [float(q["mrr"]) for q in per_query]
    order_vals = [float(q["expected_order_match"]) for q in per_query]
    return {
        "precision_at_5": macro_mean(p5_vals),
        "recall_at_10": macro_mean(r10_vals),
        "mrr": macro_mean(mrr_vals),
        "expected_order_match": macro_mean(order_vals),
        "top_category_accuracy": top_cat_hits / len(per_query) if per_query else 0.0,
    }


def _below_perfect(query: dict) -> bool:
    """Any of the four ranking metrics short of 1.0 for one query."""
    return (
        query["precision_at_5"] < 1.0
        or query["recall_at_10"] < 1.0
        or query["mrr"] < 1.0
        or query["expected_order_match"] < 1.0
    )


def _assert_perfect_metrics(per_query: list[dict]) -> None:
    failed_queries = [q["query_id"] for q in per_query if _below_perfect(q)]
    if not failed_queries:
        return
    sample = ", ".join(failed_queries[:5])
    raise RuntimeError(
        f"ranking bench: {len(failed_queries)} queries below perfect metrics: {sample}"
    )


def _validated_payload(gold_path: Path) -> dict:
    """The corpus, after the provenance and shape checks the producer will not run without.

    Resolved before the database is touched: a run that cannot prove which corpus it is about
    must stop before it seeds rows, not after measuring them.
    """
    payload = load_gold_set(gold_path)
    require_v1_gold_set(gold_path, payload)
    errors = validate_gold_set(payload)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(f"gold set validation failed:\n{joined}")
    return payload


async def _measure_queries(
    repo: MemoryReadRepository, queries: list[dict], ctx: QueryEvalContext
) -> tuple[list[dict], int]:
    """One row per query, plus how many of them put the expected category on top."""
    per_query: list[dict] = []
    top_cat_hits = 0
    for row in queries:
        query_result, top_ok = await _evaluate_query(repo, row, ctx)
        per_query.append(query_result)
        if top_ok:
            top_cat_hits += 1
    return per_query, top_cat_hits


async def run_bench(*, gold_path: Path) -> dict:
    settings = Settings(database_url=_async_dsn()).model_copy(
        update={"search_fallback_enabled": False},
    )
    engine = create_engine(settings)
    try:
        payload = _validated_payload(gold_path)
        queries = payload["queries"]
        mem_by_key = {m["content_key"]: m for m in payload["memories"]}

        session_factory = create_session_factory(engine)
        store = PgVectorStore(session_factory, settings)
        repo = MemoryReadRepository(session_factory, store, settings)

        seed = await seed_gold_set(session_factory, store, gold_path=gold_path)
        id_to_key = {str(v): k for k, v in seed.content_key_to_memory_id.items()}

        eval_ctx = QueryEvalContext(
            seed=seed,
            id_to_key=id_to_key,
            mem_by_key=mem_by_key,
        )
        per_query, top_cat_hits = await _measure_queries(repo, queries, eval_ctx)

        aggregate = _aggregate_metrics(per_query, top_cat_hits=top_cat_hits)
        _assert_perfect_metrics(per_query)
        gate_probe = await evaluate_relevance_gate_probe(repo, eval_ctx)
        return {
            "benchmark": "ranking_quality",
            "schema_version": 1,
            "gold_set": "v1",
            # This producer measures gold_set_v1.json, so the record identifies the v1 corpus:
            # the publisher refuses the run without a provenance block, and a v1 label next to a
            # v2 hash would describe a corpus that was not measured. Building it here means an
            # unhashable gold file raises before any payload is written.
            "provenance": provenance_record("gold_v1"),
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "query_count": len(queries),
            "memory_count": len(seed.content_key_to_memory_id),
            "metrics": aggregate,
            "queries": per_query,
            "relevance_gate_probe": gate_probe,
        }
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gold", type=Path, default=GOLD_SET_PATH)
    args = parser.parse_args(argv)
    gold_path = resolve_bench_input_path(args.gold, bench_dir=_RANK_DIR)
    result = asyncio.run(run_bench(gold_path=gold_path))
    write_bench_output_json(args.output, bench_dir=_RANK_DIR, payload=result)
    metrics = result["metrics"]
    print(
        f"ranking_quality: precision@5={metrics['precision_at_5']:.4f} "
        f"recall@10={metrics['recall_at_10']:.4f} mrr={metrics['mrr']:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
