#!/usr/bin/env python3
"""Live driver: run every retrieval mode over the seeded corpus and record what came back.

``bench_ranking_modes`` scores a *recording*; this module produces one. The split is what keeps
the scoring path testable without a database and the database path out of the numbers: the
recording is the seam, and it is written in the same strict format the scoring CLI reads back,
so a driver bug cannot make the scorer accept rows it would otherwise reject.

Ids in the recording are gold-set ``content_key`` values, not database UUIDs. Keys survive a
re-seed (the purge rewrites every row) and a reader can check them against ``gold_set_v2.json``,
which a UUID from one machine's database cannot offer.

Needs Postgres with pgvector and the seeded corpus, so it runs in the ``collect-ranking-quality``
CI job rather than in the unit tests; the loop itself is exercised through an injected page
lookup instead.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_RANK_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _RANK_DIR.parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _BENCH_MEMORY, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.read.models import FindSimilarQuery
from app.read.repository import MemoryReadRepository
from app.vectorstore.pgvector_store import PgVectorStore
from bench_ranking_modes import INPUT_ROOT, TOP_K
from bench_ranking_modes import main as score_main
from dsn import async_dsn
from modes import MODE_BY_NAME, MODES, BenchmarkMode, require_supported
from path_guard import (
    resolve_bench_input_path,
    resolve_bench_output_path,
    write_json_atomic,
)
from profiles import profile_vector
from provenance import GOLD_SET_PATH as PROVENANCE_GOLD_SET_PATH
from provenance import provenance_record
from recorded_run import QueryOutcome
from rerank_stub import LABEL as STUB_RERANKER_LABEL
from rerank_stub import LexicalOverlapReranker
from seed import GoldSeedResult, load_gold_set, seed_gold_set
from validate_gold_set_v2 import GOLD_SET_NAME

DEFAULT_GOLD_SET = _RANK_DIR / "gold_set_v2.json"
DEFAULT_RECORDING = _RANK_DIR / "output" / "modes-recorded.json"
# The corpus declares the floor its own geometry was designed against; this is the fallback for
# a corpus that predates the field.
FALLBACK_MIN_SIMILARITY = 0.5

# One mode's page lookup: a query in, the ranked content keys it returned out.
SearchPage = Callable[["QuerySpec"], Awaitable[Sequence[str]]]


class RunModeError(ValueError):
    """The corpus handed to the runner cannot be turned into a query.

    A ``ValueError`` so callers that already treat a bad corpus as malformed input keep working;
    named apart from a schema failure so the message a reader sees points at the runner's own
    requirement rather than at the gold set's structure.
    """


@dataclass(frozen=True, slots=True)
class RunContext:
    """Everything a mode's run shares with the others, resolved once per corpus.

    Bundled because each field is identical for every mode: passing them individually made the
    call signature longer than the call was informative.
    """

    session_factory: Any
    store: PgVectorStore
    seed: GoldSeedResult
    specs: Sequence[QuerySpec]
    floor: float


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """One query, resolved to the vector and the gold ids the database call needs."""

    query_id: str
    subset: str
    text: str
    vector: Sequence[float]
    expected_ids: tuple[str, ...]


def _require_profile(query: Mapping[str, Any]) -> Mapping[str, float]:
    profile = query.get("embedding_profile")
    if not isinstance(profile, Mapping):
        raise RunModeError(
            f"query {query.get('query_id')!r} has no embedding_profile; "
            "the mode runner needs the v2 corpus"
        )
    return profile


def _require_topics(payload: Mapping[str, Any]) -> Mapping[str, int]:
    topics = payload.get("topics")
    if not isinstance(topics, Mapping) or not topics:
        raise RunModeError("gold set must declare its topics to build query vectors")
    return topics


def _spec(query: Mapping[str, Any], topics: Mapping[str, int]) -> QuerySpec:
    return QuerySpec(
        query_id=str(query["query_id"]),
        subset=str(query["subset"]),
        text=str(query["query_text"]),
        vector=profile_vector(_require_profile(query), topics),
        expected_ids=tuple(str(key) for key in query["expected_content_keys"]),
    )


def query_specs(payload: Mapping[str, Any]) -> list[QuerySpec]:
    """Resolve every gold query against the corpus topics, once, for all modes.

    Building the vectors here rather than per mode is what makes the modes comparable: they are
    guaranteed to be asked the same question.
    """
    topics = _require_topics(payload)
    return [_spec(query, topics) for query in payload["queries"]]


async def run_mode(search: SearchPage, specs: Sequence[QuerySpec]) -> list[QueryOutcome]:
    """Ask the page lookup for one page per query and record it verbatim.

    No filtering or topping up happens here: a mode that returns nine ids must be published as
    nine, because the shortfall is a result about that mode.
    """
    outcomes: list[QueryOutcome] = []
    for spec in specs:
        ranked = await search(spec)
        outcomes.append(
            QueryOutcome(
                query_id=spec.query_id,
                subset=spec.subset,
                ranked_ids=tuple(ranked),
                expected_ids=spec.expected_ids,
            )
        )
    return outcomes


def _content_keys(hits: Sequence[Any], id_to_key: Mapping[str, str]) -> list[str]:
    """Keep the corpus rows, in the order the mode ranked them.

    A hit that is not part of the corpus cannot be judged, so it is dropped rather than counted
    as a miss; the seed purges the org first, so anything else is a leftover from another test.
    """
    return [key for key in (id_to_key.get(str(hit.id)) for hit in hits) if key is not None]


def page_search(
    repo: MemoryReadRepository,
    seed: GoldSeedResult,
    id_to_key: Mapping[str, str],
    *,
    min_similarity: float,
) -> SearchPage:
    """Bind one mode's repository into the page lookup the runner calls."""

    async def search(spec: QuerySpec) -> Sequence[str]:
        hits = await repo.find_similar(
            FindSimilarQuery(
                org_id=seed.org_id,
                agent_id=seed.agent_id,
                query_embedding=list(spec.vector),
                query_text=spec.text,
                limit=TOP_K,
                min_similarity=min_similarity,
            )
        )
        return _content_keys(hits, id_to_key)

    return search


def _row(outcome: QueryOutcome) -> dict[str, Any]:
    return {
        "query_id": outcome.query_id,
        "subset": outcome.subset,
        "ranked_ids": list(outcome.ranked_ids),
        "expected_ids": list(outcome.expected_ids),
    }


PROVENANCE_GOLD_FIELDS = ("gold_set_hash", "gold_set_name", "corpus_status")


def require_v2_gold_set(gold_path: Path, payload: Mapping[str, Any]) -> None:
    """Refuse a corpus whose provenance could not be recorded honestly.

    The recorded ``gold_set_hash`` is the digest of the v2 corpus at its canonical path, so this
    driver accepts that file and no other: a copy somewhere else would be seeded and published
    under the canonical file's hash. The corpus must also name itself the v2 set, because the
    recording is scored by the v2 validator -- publishing it under ``v1`` would compare a run to
    a corpus it was not measured on.
    """
    if gold_path.name != PROVENANCE_GOLD_SET_PATH.name:
        raise RunModeError(
            f"gold set {gold_path.name!r} is not {PROVENANCE_GOLD_SET_PATH.name!r}; "
            "this driver records provenance for the v2 corpus only"
        )
    if gold_path.resolve() != PROVENANCE_GOLD_SET_PATH.resolve():
        raise RunModeError(
            f"gold set {gold_path} is not the canonical {PROVENANCE_GOLD_SET_PATH}: the recorded "
            "provenance hashes that file, so a copy would publish another file's hash"
        )
    declared = payload.get("gold_set")
    if declared != GOLD_SET_NAME:
        raise RunModeError(
            f"gold set declares gold_set {declared!r}, expected {GOLD_SET_NAME!r}; "
            "the recording would name a corpus it was not measured on"
        )


def gold_set_provenance() -> dict[str, Any]:
    """The provenance block for the v2 corpus, from the one hash implementation."""
    return dict(provenance_record("gold"))


def _require_gold_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """A recording must name the corpus it was measured on, or it cannot be scored honestly."""
    if not isinstance(provenance, Mapping):
        raise RunModeError(
            "recording provenance must be the provenance block from benchmarks/memory/provenance.py"
        )
    missing = [field for field in PROVENANCE_GOLD_FIELDS if not provenance.get(field)]
    if missing:
        raise RunModeError(
            f"recording provenance is missing {', '.join(missing)}; "
            "every mode run must name the gold set it was measured on"
        )
    return dict(provenance)


@dataclass(frozen=True, slots=True)
class RecordingContext:
    """The run metadata a recording publishes, bundled so one call carries them all.

    Every field is required rather than defaulted: the recording is the only artifact that knows
    which corpus produced these rankings, and a default would let a run reach the scorer without
    saying what it measured.
    """

    reranker: str
    gold_set: str
    recorded_at: str
    provenance: Mapping[str, Any]


def build_recording(
    runs: Mapping[str, Sequence[QueryOutcome]], context: RecordingContext
) -> dict[str, Any]:
    """The recorded run, in the format ``recorded_run.load_recorded`` validates."""
    return {
        "schema_version": 1,
        "benchmark": "ranking_quality",
        "gold_set": context.gold_set,
        "reranker": context.reranker,
        "recorded_at": context.recorded_at,
        "provenance": _require_gold_provenance(context.provenance),
        "modes": {name: [_row(outcome) for outcome in outcomes] for name, outcomes in runs.items()},
    }


def base_settings() -> Settings:
    """The configuration every mode is a delta over.

    ``search_fallback_enabled`` is pinned off here because only ``dense_only`` sets it: leaving
    it to the ambient default would let a refill add lexical hits to the vector-only baseline and
    to the modes that inherit the value, so two runs on different defaults would not compare.
    """
    return Settings(database_url=async_dsn()).model_copy(update={"search_fallback_enabled": False})


def _settings_for(mode: BenchmarkMode, base: Settings) -> Settings:
    require_supported(mode, base)
    return mode.settings_for(base)


def _require_stub_reranker(reranker: str) -> None:
    """This driver can only run the stub, so a real model's name here would be a false claim."""
    if reranker != STUB_RERANKER_LABEL:
        raise RunModeError(
            f"this driver only runs {STUB_RERANKER_LABEL!r}, not {reranker!r}; "
            "a real cross-encoder is measured by the opt-in job, not here"
        )


def _rerank_client(mode: BenchmarkMode) -> LexicalOverlapReranker | None:
    """A stub for the modes that declare reranking, ``None`` for the modes that do not.

    ``None`` is not a shortcut: the read path only reranks when it holds a client, so a mode
    labelled ``hybrid_rerank`` that was handed no client would publish fusion's numbers under
    the cross-encoder's name.
    """
    return LexicalOverlapReranker() if mode.rerank else None


def _require_rerank_ran(mode: BenchmarkMode, client: LexicalOverlapReranker | None) -> None:
    """A mode that declares reranking must have reached the reranker.

    The stage skips itself when the hydrated window is too small and degrades on any failure,
    so a run can finish carrying the mode's label with none of its behaviour.
    """
    if client is None or client.calls:
        return
    raise RunModeError(
        f"mode {mode.name!r} declares reranking but the reranker was never called; "
        "publishing this run would attribute fusion's numbers to a cross-encoder"
    )


async def _run_one_mode(
    mode: BenchmarkMode, settings: Settings, context: RunContext
) -> list[QueryOutcome]:
    client = _rerank_client(mode)
    repo = MemoryReadRepository(
        context.session_factory, context.store, settings, rerank_client=client
    )
    id_to_key = {
        str(memory_id): key for key, memory_id in context.seed.content_key_to_memory_id.items()
    }
    outcomes = await run_mode(
        page_search(repo, context.seed, id_to_key, min_similarity=context.floor),
        context.specs,
    )
    _require_rerank_ran(mode, client)
    return outcomes


async def run_all(
    *,
    gold_path: Path,
    modes: Sequence[BenchmarkMode],
    reranker: str,
) -> dict[str, Any]:
    """Seed the corpus, run each mode over the same queries, and return the recording."""
    _require_stub_reranker(reranker)
    payload = load_gold_set(gold_path)  # validates the corpus before anything is seeded
    require_v2_gold_set(gold_path, payload)
    # Gathered before the database is touched: a run that cannot prove which corpus it is
    # about must stop before it seeds rows, not after measuring them.
    provenance = gold_set_provenance()
    specs = query_specs(payload)
    base = base_settings()
    settings_by_mode = {mode.name: _settings_for(mode, base) for mode in modes}
    floor = float(payload.get("min_similarity") or FALLBACK_MIN_SIMILARITY)
    engine = create_engine(base)
    try:
        session_factory = create_session_factory(engine)
        store = PgVectorStore(session_factory, base)
        seed = await seed_gold_set(session_factory, store, gold_path=gold_path)
        context = RunContext(
            session_factory=session_factory,
            store=store,
            seed=seed,
            specs=specs,
            floor=floor,
        )
        runs = {
            mode.name: await _run_one_mode(mode, settings_by_mode[mode.name], context)
            for mode in modes
        }
    finally:
        await engine.dispose()
    return build_recording(
        runs,
        RecordingContext(
            reranker=reranker,
            gold_set=str(payload.get("gold_set") or GOLD_SET_NAME),
            recorded_at=datetime.now(tz=UTC).isoformat(),
            provenance=provenance,
        ),
    )


def _selected_modes(names: Sequence[str]) -> list[BenchmarkMode]:
    unknown = sorted(set(names) - set(MODE_BY_NAME))
    if unknown:
        raise RunModeError(f"unknown modes: {', '.join(unknown)}")
    return [MODE_BY_NAME[name] for name in names]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold-set",
        type=Path,
        default=DEFAULT_GOLD_SET,
        help="gold set to seed and score, inside the benchmark directory",
    )
    parser.add_argument(
        "--record-out",
        type=Path,
        default=DEFAULT_RECORDING,
        help="where to write the recording, inside the benchmark directory",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=[mode.name for mode in MODES],
        default=[mode.name for mode in MODES],
        help="modes to run, in this order",
    )
    parser.add_argument(
        "--reranker",
        default=STUB_RERANKER_LABEL,
        help="the reranker that produced these rankings; published with every number",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv[1:] if argv else None)
    gold_path = resolve_bench_input_path(args.gold_set, bench_dir=INPUT_ROOT)
    target = resolve_bench_output_path(args.record_out, bench_dir=INPUT_ROOT)
    recording = asyncio.run(
        run_all(
            gold_path=gold_path,
            modes=_selected_modes(args.modes),
            reranker=args.reranker,
        )
    )
    written = write_json_atomic(target, recording)
    print(f"recorded {len(recording['modes'])} modes to {written}")
    return score_main(["run_modes", "--outcomes", str(written)])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
