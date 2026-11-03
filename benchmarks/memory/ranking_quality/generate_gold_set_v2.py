#!/usr/bin/env python3
"""Generate gold_set_v2.json deterministically.

The corpus is generated rather than hand-written: 500 memories review badly as a hand-authored
diff and drift from their own rules. A seeded generator plus the validator (part 1) gives a
reproducible artifact that is checked by machine, and the committed JSON still diffs meaningfully
when a fact changes.

Layout, fixed by the validator's thresholds:

| pool    | topics | memories | what the query asks for                                             |
|---------|--------|----------|---------------------------------------------------------------------|
| dense   | 0-29   | 300      | the memory with the strongest cosine to the query                    |
| lexical | 30-39  | 100      | an orthogonal memory carrying a `DEC-` token, reachable only by BM25 |
| graph   | 40-49  | 100      | the newer side of a pending conflict, which must outrank its twin    |

Topic pools are disjoint, so a memory from one pool can never outrank another pool's answer.
Each profile is `{topic: weight, filler_i: sqrt(1 - weight^2)}` with a filler basis unique to
that memory, which makes `cos(query, memory)` exactly `weight`.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RANK_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _RANK_DIR.parent
for _path in (_BENCH_MEMORY, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from profiles import EMBEDDING_DIM
from validate_gold_set_v2 import (
    BENCH_MIN_SIMILARITY,
    DENSE_MIN_COSINE,
    GOLD_SET_NAME,
    GRAPH_PAIR_MIN_COSINE,
    SCHEMA_VERSION,
)

OUTPUT_PATH = _RANK_DIR / "gold_set_v2.json"
SEED = 20261103

TOPICS: tuple[str, ...] = (
    # dense pool (0-29)
    "backup retention", "incident severity", "deploy freeze", "database failover",
    "cache eviction", "log retention", "rate limit policy", "tenant onboarding",
    "key rotation", "schema migration", "queue backpressure", "price rounding",
    "invoice numbering", "tax residency", "refund window", "chargeback handling",
    "trial length", "seat counting", "plan upgrade path", "dunning schedule",
    "password policy", "session lifetime", "mfa enrolment", "api token scope",
    "audit logging", "data residency", "pii redaction", "export format",
    "webhook retry", "idempotency window",
    # lexical pool (30-39)
    "service mesh rollout", "ingress certificate", "job scheduler shard",
    "wal segment archive", "replica lag alarm", "search index rebuild",
    "feature flag naming", "image digest pin", "node pool drain", "cron jitter",
    # graph pool (40-49)
    "default branch name", "release cadence", "oncall handoff", "postmortem template",
    "error budget", "dependency pinning", "test data policy", "staging credentials",
    "support escalation", "vendor contact",
)

ASPECTS: tuple[str, ...] = (
    "value", "owner", "review date", "threshold", "fallback", "runbook",
    "approval path", "tooling", "escalation", "exception",
)

CATEGORIES: tuple[str, ...] = ("factual", "procedural", "preference", "behavioral", "episodic")

DENSE_PER_TOPIC = 10
DENSE_QUERIES_PER_TOPIC = 2
LEXICAL_PER_TOPIC = 10
LEXICAL_QUERIES_PER_TOPIC = 5
GRAPH_PER_TOPIC = 10
GRAPH_QUERIES_PER_TOPIC = 4
DENSE_TOPIC_COUNT = 30
LEXICAL_TOPIC_COUNT = 10
GRAPH_TOPIC_COUNT = 10
# Answers are staggered so two queries about one topic ask for different rows, and the top
# answer is always the unique strongest match (no tie can fill the vector window).
DENSE_WEIGHTS: tuple[float, ...] = (0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50)
AGE_MIN, AGE_MAX = 9, 300


@dataclass(frozen=True, slots=True)
class TopicPlan:
    name: str
    index: int
    pool: str


def _profile(topic: str, filler: int, weight: float) -> dict[str, float]:
    """A profile at exactly ``weight`` against ``{topic: 1.0}``, with a unique filler basis.

    A weight of 1.0 leaves nothing for the filler; adding a zero-weight topic would be
    rejected by the profile rules, and rightly so.
    """
    second = math.sqrt(max(0.0, 1.0 - weight * weight))
    if second <= 0.0:
        return {topic: weight}
    return {topic: weight, f"filler-{filler}": second}


def _topic_map(
    memories: list[dict[str, Any]],
    queries: list[dict[str, Any]],
) -> dict[str, int]:
    """Declare exactly the bases that are used: the 50 named topics, then every filler.

    Declaring a fixed block of a thousand fillers made the artifact mostly declaration; this
    keeps the map minimal, deterministic, and still collision-free.
    """
    named = {name: index for index, name in enumerate(TOPICS)}
    used: set[str] = set()
    for row in memories:
        used.update(row["embedding_profile"])
    for query in queries:
        used.update(query["embedding_profile"])
    extras = sorted(name for name in used if name not in named)
    topics = {**named}
    topics.update({name: len(named) + offset for offset, name in enumerate(extras)})
    if len(topics) > EMBEDDING_DIM:
        raise SystemExit(f"{len(topics)} topics exceed the {EMBEDDING_DIM}-dimension space")
    return topics


def _memory(key: str, **fields: Any) -> dict[str, Any]:
    """One corpus row. Fields arrive as keywords so the builder call sites stay readable."""
    profile = _profile(fields["topic"], fields["filler"], fields["weight"])
    row: dict[str, Any] = {
        "content_key": key,
        "content": fields["content"],
        "category": CATEGORIES[fields["index"] % len(CATEGORIES)],
        "valid_from_days_ago": fields["age"],
        "confidence": fields["confidence"],
        "usefulness_score": fields["usefulness"],
        "embedding_profile": profile,
        "topic": fields["topic"],
        "aspect": fields["aspect"],
    }
    if fields.get("conflicts_with"):
        row["conflicts_with"] = fields["conflicts_with"]
    return row


def _dense_block(plan: TopicPlan) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memories: list[dict[str, Any]] = []
    for slot, weight in enumerate(DENSE_WEIGHTS):
        index = plan.index * DENSE_PER_TOPIC + slot
        aspect = ASPECTS[slot]
        value = f"{aspect} {slot + 1} for {plan.name}"
        memories.append(
            _memory(
                f"gold.dense.{plan.index}.{slot}",
                topic=plan.name,
                filler=plan.index * DENSE_PER_TOPIC + slot,
                weight=weight,
                aspect=aspect,
                content=f"The {aspect} for {plan.name} is recorded as {value} in the platform handbook.",
                index=index,
                confidence=round(0.95 - slot * 0.03, 2),
                usefulness=round(0.9 - slot * 0.05, 2),
                age=AGE_MIN + (index % (AGE_MAX - AGE_MIN)),
            )
        )
    queries = [_dense_query(plan, slot) for slot in range(DENSE_QUERIES_PER_TOPIC)]
    return memories, queries


def _dense_query(plan: TopicPlan, slot: int) -> dict[str, Any]:
    """Ask about the aspect the memory at ``slot`` actually records.

    The question and the expected key are derived from one aspect, so the labelled answer
    cannot be a row that answers a different question.
    """
    aspect = ASPECTS[slot]
    return {
        "query_id": f"q_dense_{plan.index}_{slot}",
        "query_text": f"what is the {aspect} for {plan.name}",
        "subset": "dense",
        "aspect": aspect,
        "embedding_profile": {plan.name: 1.0},
        "expected_content_keys": [f"gold.dense.{plan.index}.{slot}"],
    }


def _lexical_block(plan: TopicPlan) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memories: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for slot in range(LEXICAL_PER_TOPIC):
        index = 300 + plan.index * LEXICAL_PER_TOPIC + slot
        token = f"DEC-{4400 + plan.index * LEXICAL_PER_TOPIC + slot}"
        key = f"gold.lexical.{plan.index}.{slot}"
        aspect = ASPECTS[slot]
        memories.append(
            _memory(
                key,
                topic=plan.name,
                filler=100 + plan.index * LEXICAL_PER_TOPIC + slot,
                weight=0.40,
                aspect=aspect,
                content=(
                    f"Change ticket {token} moved the {aspect} for {plan.name} to the "
                    f"value agreed in review {plan.index}-{slot}."
                ),
                index=index,
                confidence=round(0.9 - slot * 0.02, 2),
                usefulness=round(0.8 - slot * 0.03, 2),
                age=AGE_MIN + (index % (AGE_MAX - AGE_MIN)),
            )
        )
        if slot < LEXICAL_QUERIES_PER_TOPIC:
            queries.append(
                {
                    "query_id": f"q_lexical_{plan.index}_{slot}",
                    "query_text": f"change {token} for {plan.name}",
                    "subset": "lexical",
                    "embedding_profile": {f"unrelated-{plan.index}": 1.0},
                    "lexical_tokens": [token],
                    "expected_content_keys": [key],
                }
            )
    return memories, queries


def _graph_block(plan: TopicPlan) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memories: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for slot in range(GRAPH_QUERIES_PER_TOPIC):
        index = 400 + plan.index * GRAPH_PER_TOPIC + slot
        current_key = f"gold.current.{plan.index}.{slot}"
        twin_key = f"gold.twin.{plan.index}.{slot}"
        aspect = ASPECTS[slot]
        memories.append(
            _memory(
                twin_key,
                topic=plan.name,
                filler=200 + plan.index * GRAPH_PER_TOPIC + slot,
                weight=GRAPH_PAIR_MIN_COSINE,
                aspect=aspect,
                content=f"The {aspect} for {plan.name} was {slot + 1} under the previous agreement.",
                index=index,
                confidence=0.55,
                usefulness=0.25,
                age=AGE_MIN + 120 + slot,
            )
        )
        memories.append(
            _memory(
                current_key,
                topic=plan.name,
                filler=300 + plan.index * GRAPH_PER_TOPIC + slot,
                weight=1.0,
                aspect=aspect,
                content=f"The {aspect} for {plan.name} is now {slot + 10} under the current agreement.",
                index=index + 1,
                confidence=0.97,
                usefulness=0.85,
                age=AGE_MIN + slot,
                conflicts_with=[twin_key],
            )
        )
        queries.append(
            {
                "query_id": f"q_graph_{plan.index}_{slot}",
                "query_text": f"current {aspect} for {plan.name}",
                "subset": "graph",
                "embedding_profile": {plan.name: 1.0},
                "expected_content_keys": [current_key],
            }
        )
    # Two extra active rows so the pool holds the planned ten memories per topic.
    for slot in range(GRAPH_QUERIES_PER_TOPIC, GRAPH_QUERIES_PER_TOPIC + 2):
        details = f"{plan.name} note {slot}"
        memories.append(
            _memory(
                f"gold.note.{plan.index}.{slot}",
                topic=plan.name,
                filler=400 + plan.index * GRAPH_PER_TOPIC + slot,
                weight=0.45,
                aspect=ASPECTS[slot % len(ASPECTS)],
                content=f"A supporting note records the {plan.name} context as {details} for the review.",
                index=400 + plan.index * GRAPH_PER_TOPIC + slot,
                confidence=0.7,
                usefulness=0.4,
                age=AGE_MIN + 30 + slot,
            )
        )
    return memories, queries


def build_corpus() -> dict[str, Any]:
    memories: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    plans = [TopicPlan(name, index, _pool_for(index)) for index, name in enumerate(TOPICS)]
    for plan in plans:
        block = {"dense": _dense_block, "lexical": _lexical_block, "graph": _graph_block}[plan.pool]
        block_memories, block_queries = block(plan)
        memories.extend(block_memories)
        queries.extend(block_queries)
    return {
        "schema_version": SCHEMA_VERSION,
        "gold_set": GOLD_SET_NAME,
        "seed": SEED,
        "topics": _topic_map(memories, queries),
        "min_similarity": BENCH_MIN_SIMILARITY,
        "dense_min_cosine": DENSE_MIN_COSINE,
        "graph_pair_min_cosine": GRAPH_PAIR_MIN_COSINE,
        "memories": memories,
        "queries": queries,
    }


def _pool_for(index: int) -> str:
    if index < DENSE_TOPIC_COUNT:
        return "dense"
    if index < DENSE_TOPIC_COUNT + LEXICAL_TOPIC_COUNT:
        return "lexical"
    return "graph"


def _output_path(argv: list[str] | None) -> Path:
    """Resolve the output path, refusing anything outside this benchmark directory.

    The path comes from the command line, so without this a caller could write the corpus
    anywhere the process can write.
    """
    if not argv or len(argv) < 2:
        return OUTPUT_PATH
    candidate = Path(argv[1]).resolve()
    root = _RANK_DIR.resolve()
    if candidate.is_dir():
        raise SystemExit(f"output path is a directory: {candidate}")
    if root not in candidate.parents and candidate != root:
        raise SystemExit(f"refusing to write outside {root}: {candidate}")
    return candidate


def main(argv: list[str] | None = None) -> int:
    payload = build_corpus()
    out = _output_path(argv)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {out.name}: {len(payload['memories'])} memories, "
        f"{len(payload['queries'])} queries, {len(TOPICS)} topics"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
