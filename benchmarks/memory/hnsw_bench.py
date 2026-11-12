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
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.vectorstore.pgvector_store import PgVectorStore

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
from hnsw_run import WARMUP_QUERIES, MatrixConfig, SizeResult, run_search_matrix
from path_guard import UnsafePathError, resolve_raw_bench_path
from provenance import provenance_record
from synth import ACTIVE_DIMS, DIM

_DEFAULT_EF_SEARCH = 64
_DEFAULT_SIZES = (10_000, 100_000)


@dataclass(frozen=True, slots=True)
class PayloadParams:
    """Knobs + results for the published JSON payload."""

    ef_search: int
    results: list[SizeResult]
    iterative_modes: list[str]
    min_sims: list[float]
    index_modes: list[str]


def _methodology_block(params: PayloadParams) -> dict[str, object]:
    return {
        "index": "idx_memories_embedding_hnsw (m=16, ef_construction=64, cosine)",
        "ef_search": params.ef_search,
        "dim": DIM,
        "active_dims": ACTIVE_DIMS,
        "warmup_queries": WARMUP_QUERIES,
        "truncate_between_sizes": True,
        "reuse_corpus_across_search_knobs": True,
        "analyze_after_copy": True,
        "explain_requires_hnsw": True,
        "recall": "planted near-neighbor must appear in top-10",
        "latency": "wall-clock PgVectorStore.search including SET LOCAL",
        "iterative_scan_modes": params.iterative_modes,
        "min_similarity_values": params.min_sims,
        "index_build_modes": params.index_modes,
    }


def _build_payload(params: PayloadParams) -> dict[str, object]:
    """The raw artifact for one measured run.

    ``provenance`` is gathered here rather than by a caller, so a payload cannot be assembled
    without it. ``provenance_record`` raises for a corpus file it cannot read and for a runner
    identity it cannot determine, which is the point: a run that cannot say what it measured is
    not written to disk, and no branch below fills the block in from a default. A halted or
    unusable ``git`` does not raise -- it is reported as ``dirty``/``stale``, because "cannot
    prove this is clean" is a fact the record can carry, while "no corpus hash" is not. Because
    this record is gathered *after* the run, ``_benchmark`` compares it with the one captured
    before the run and refuses to write a payload when they differ.
    """
    mean_recall = (
        statistics.fmean(r.recall_at_10 for r in params.results) if params.results else 0.0
    )
    return {
        "benchmark": "hnsw_recall_latency",
        "generated_at": datetime.now(UTC).isoformat(),
        "methodology": _methodology_block(params),
        "provenance": provenance_record("hnsw"),
        "results": [asdict(r) for r in params.results],
        "mean_recall_at_10": mean_recall,
    }


def _changed_provenance(before: Mapping[str, object], after: Mapping[str, object]) -> list[str]:
    """The provenance fields that differ between two records of the same run."""
    return sorted(
        field for field in set(before) | set(after) if before.get(field) != after.get(field)
    )


def _require_one_corpus(before: Mapping[str, object], after: object) -> None:
    """Refuse a run the corpus moved under.

    The record is captured before the matrix and built again inside the payload afterwards, so a
    difference between the two is proof that the corpus, the runner identity or the tree changed
    while the measurement was running. Such a run mixes two corpora in one number and no reader
    can tell which, so it is refused rather than written.
    """
    if not isinstance(after, Mapping):
        raise TypeError("payload.provenance must be the mapping _build_payload writes")
    changed = _changed_provenance(before, after)
    if changed:
        raise RuntimeError(
            f"provenance changed during the run ({', '.join(changed)}); the corpus or the tree"
            " was modified between the start and the end of the measurement, so this run cannot"
            " be attributed to one corpus -- re-run the bench on an unchanged checkout"
        )


def _require_dsn() -> str:
    dsn = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not dsn:
        raise RuntimeError("IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required")
    return dsn


def _matrix_from_args(args: argparse.Namespace) -> MatrixConfig:
    return MatrixConfig(
        sizes=list(args.sizes),
        index_modes=list(args.index_build_mode),
        iterative_modes=list(args.iterative_scan),
        min_sims=list(args.min_similarity),
        ef_search=args.ef_search,
        queries=args.queries,
    )


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


async def _benchmark(args: argparse.Namespace) -> dict[str, object]:
    dsn = _require_dsn()
    # Captured before the matrix runs: the payload's record is gathered after it, and a
    # difference between the two is the corpus changing mid-run.
    before = provenance_record("hnsw")
    settings = Settings(database_url=dsn, hnsw_ef_search=args.ef_search)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PgVectorStore(factory, settings)
    config = _matrix_from_args(args)
    try:
        results = await run_search_matrix(engine, store, factory, config)
    finally:
        await engine.dispose()
    payload = _build_payload(
        PayloadParams(
            ef_search=args.ef_search,
            results=results,
            iterative_modes=config.iterative_modes,
            min_sims=config.min_sims,
            index_modes=config.index_modes,
        )
    )
    _require_one_corpus(before, payload.get("provenance"))
    _write_payload(resolve_raw_bench_path(args.output, must_exist=False), payload)
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
        help="hnsw.ef_search (default: 64 — production / publish SLA)",
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
