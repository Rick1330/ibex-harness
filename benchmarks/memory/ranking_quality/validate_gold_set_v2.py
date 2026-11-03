#!/usr/bin/env python3
"""Validate gold_set_v2.json: structure, and the separations that make each subset mean something.

The point of v2 is that a mode can *fail* a subset. That only holds if the corpus is built
so that it does:

* a **dense** query's answer must be close to the query *and* inside the top-k the ANN
  channel fetches, or vector search cannot return it whatever the floor says;
* a **lexical** query's answer must be *further* from the query than the configured floor
  (so the vector channel rejects it) while both the query text and the answer text carry the
  same rare token (so the sparse channel, which tokenises the query text, can find it);
* a **graph** query needs two *active* memories close enough that both would be retrieved,
  joined by a pending conflict escalation, so unresolved-conflict suppression has something
  to remove. Supersession is deliberately not used here: a superseded memory is fenced out
  by ``status = 'active'`` before ranking, so it would never reach the suppression stage and
  the subset could not fail for the reason it claims (ADR-0094, ``read/conflicts.py``).

Without those assertions, a "hybrid beats dense" result could just mean the corpus was easy.
Every rule reports a line a human can act on, and one run lists every failure.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RANK_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _RANK_DIR.parent
for _path in (_BENCH_MEMORY, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from path_guard import resolve_bench_input_path
from profiles import ProfileError, profile_cosine, validate_topics

SCHEMA_VERSION = 2
GOLD_SET_NAME = "ranking_quality_v2"
CATEGORIES = frozenset({"factual", "procedural", "preference", "behavioral", "episodic"})
SUBSETS = frozenset({"dense", "lexical", "graph"})
MIN_MEMORIES = 400
MAX_MEMORIES = 600
MIN_QUERIES = 120
MAX_QUERIES = 180
MIN_PER_SUBSET = {"dense": 40, "lexical": 30, "graph": 15}
MIN_AGE_DAYS = 7
MAX_AGE_DAYS = 365
MIN_CONTENT_CHARS = 20

# One source of truth for the floor. The harness passes this value to the read path
# (`bench_ranking_quality.py`), and the gold set has to declare exactly it: a corpus that
# ships its own floor could claim a separation the run does not actually enforce.
BENCH_MIN_SIMILARITY = 0.5
# The ANN channel fetches this many candidates before the floor is applied. An answer has to
# be inside that window, not merely above the floor.
ANN_LIMIT = 10
# A dense answer must clear the floor with margin, or it is one distractor away from falling out.
DENSE_MIN_COSINE = BENCH_MIN_SIMILARITY + 0.05
# Two sides of a pending conflict must be close enough that both are retrieved together;
# otherwise suppression is never exercised and the graph subset measures nothing.
GRAPH_PAIR_MIN_COSINE = 0.80


@dataclass(frozen=True, slots=True)
class Corpus:
    memories: dict[str, dict[str, Any]]
    queries: list[dict[str, Any]]
    topics: Mapping[str, int]
    min_similarity: float = BENCH_MIN_SIMILARITY
    ann_limit: int = ANN_LIMIT


def validate_gold_set_v2(payload: object) -> list[str]:
    """Return every problem found; an empty list means the corpus is usable."""
    if not isinstance(payload, Mapping):
        return ["gold set must be an object"]

    header_errors = _validate_header(payload)
    topics = payload.get("topics")
    topic_map: Mapping[str, int] = dict(topics) if isinstance(topics, Mapping) else {}
    profiles_usable = not validate_topics(topics)

    memories, memory_errors = _index_memories(payload.get("memories"), topic_map, profiles_usable)
    queries, query_errors = _index_queries(payload.get("queries"), topic_map, profiles_usable)

    errors = [*header_errors, *memory_errors, *query_errors]
    errors.extend(_validate_sizes(payload))
    errors.extend(_validate_categories(memories))
    if profiles_usable:
        errors.extend(_validate_subsets(Corpus(memories=memories, queries=queries, topics=topic_map)))
    errors.extend(_validate_conflict_targets(memories))
    return errors


def _validate_header(payload: Mapping[str, Any]) -> list[str]:
    return [
        *_validate_version(payload.get("schema_version")),
        *_validate_name(payload.get("gold_set")),
        *validate_topics(payload.get("topics")),
        *_validate_similarity_floor(payload.get("min_similarity")),
        *_validate_collection(payload.get("memories"), "memories"),
        *_validate_collection(payload.get("queries"), "queries"),
    ]


def _validate_version(value: object) -> list[str]:
    if value == SCHEMA_VERSION:
        return []
    return [f"schema_version must be {SCHEMA_VERSION}, got {value!r}"]


def _validate_name(value: object) -> list[str]:
    if value == GOLD_SET_NAME:
        return []
    return [f"gold_set must be {GOLD_SET_NAME!r}"]


def _validate_collection(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{field} must be an array"]
    if not value:
        return [f"{field} must not be empty"]
    return []


def _validate_similarity_floor(value: object) -> list[str]:
    if value is None:
        return ["min_similarity is required: it must equal the floor the harness passes"]
    try:
        floor = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return [f"min_similarity must be numeric, got {value!r}"]
    if not math.isfinite(floor):
        return [f"min_similarity must be finite, got {value!r}"]
    if abs(floor - BENCH_MIN_SIMILARITY) > 1e-9:
        return [
            (
                f"min_similarity {floor} does not match the harness floor "
                f"{BENCH_MIN_SIMILARITY}: the separations below are measured against it"
            )
        ]
    return []


def _index_memories(
    rows: object,
    topics: Mapping[str, int],
    profiles_usable: bool,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    memories: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not isinstance(rows, list):
        return memories, []
    for index, row in enumerate(rows):
        prefix = f"memories[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        row_errors = _validate_memory(row, prefix, topics, profiles_usable)
        key = row.get("content_key")
        if isinstance(key, str) and key in memories:
            row_errors.append(f"duplicate content_key: {key}")
        errors.extend(row_errors)
        if not row_errors and isinstance(key, str):
            memories[key] = dict(row)
    return memories, errors


def _validate_memory(
    row: Mapping[str, Any],
    prefix: str,
    topics: Mapping[str, int],
    profiles_usable: bool,
) -> list[str]:
    return [
        *_validate_memory_identity(row, prefix),
        *_unit_interval(row.get("confidence"), "confidence", prefix),
        *_unit_interval(row.get("usefulness_score"), "usefulness_score", prefix),
        *_age(row.get("valid_from_days_ago"), prefix),
        *_validate_profile_field(row.get("embedding_profile"), prefix, topics, profiles_usable),
        *_key_list(row.get("conflicts_with"), "conflicts_with", prefix),
    ]


def _validate_memory_identity(row: Mapping[str, Any], prefix: str) -> list[str]:
    return [
        *_validate_key(row.get("content_key"), prefix),
        *_validate_content(row.get("content"), prefix),
        *_validate_category(row.get("category"), prefix),
    ]


def _validate_key(value: object, prefix: str) -> list[str]:
    if isinstance(value, str) and value.strip():
        return []
    return [f"{prefix} content_key must be a non-empty string"]


def _validate_content(value: object, prefix: str) -> list[str]:
    if isinstance(value, str) and len(value.strip()) >= MIN_CONTENT_CHARS:
        return []
    return [f"{prefix} content must be a string of at least {MIN_CONTENT_CHARS} characters"]


def _validate_category(value: object, prefix: str) -> list[str]:
    if isinstance(value, str) and value in CATEGORIES:
        return []
    return [f"{prefix} invalid category {value!r}"]


def _validate_profile_field(
    profile: object,
    prefix: str,
    topics: Mapping[str, int],
    profiles_usable: bool,
) -> list[str]:
    if not profiles_usable:
        return []
    return _validate_profile(profile, f"{prefix}.embedding_profile", topics)


def _unit_interval(value: object, field: str, prefix: str) -> list[str]:
    if value is None:
        return [f"{prefix} missing {field}"]
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return [f"{prefix} {field} must be numeric"]
    if not 0.0 <= parsed <= 1.0:
        return [f"{prefix} {field} must be in [0, 1], got {parsed!r}"]
    return []


def _age(value: object, prefix: str) -> list[str]:
    if not isinstance(value, int) or isinstance(value, bool):
        return [f"{prefix} valid_from_days_ago must be an integer"]
    if not MIN_AGE_DAYS <= value <= MAX_AGE_DAYS:
        return [f"{prefix} age {value} outside [{MIN_AGE_DAYS}, {MAX_AGE_DAYS}]"]
    return []


def _validate_profile(profile: object, prefix: str, topics: Mapping[str, int]) -> list[str]:
    if not isinstance(profile, Mapping):
        return [f"{prefix} must be an object of topic → weight"]
    unknown = sorted(topic for topic in profile if topic not in topics)
    if unknown:
        return [f"{prefix} uses undeclared topics: {unknown}"]
    try:
        profile_cosine(profile, profile)  # validates shape, types, and normalisation
    except ProfileError as exc:
        return [f"{prefix}: {exc}"]
    return []


def _key_list(value: object, field: str, prefix: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"{prefix} {field} must be an array of content keys"]
    if not value:
        return [f"{prefix} {field} must not be empty when present"]
    return [
        f"{prefix} {field} items must be non-empty strings"
        for item in value
        if not isinstance(item, str) or not item.strip()
    ]


def _index_queries(
    rows: object,
    topics: Mapping[str, int],
    profiles_usable: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    queries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        return queries, []
    for index, row in enumerate(rows):
        prefix = f"queries[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        row_errors = _validate_query(row, prefix, topics, profiles_usable)
        qid = row.get("query_id")
        if isinstance(qid, str) and qid in seen:
            row_errors.append(f"duplicate query_id: {qid}")
        errors.extend(row_errors)
        if not row_errors:
            seen.add(str(qid))
            queries.append(dict(row))
    return queries, errors


def _validate_query(
    row: Mapping[str, Any],
    prefix: str,
    topics: Mapping[str, int],
    profiles_usable: bool,
) -> list[str]:
    return [
        *_validate_query_identity(row, prefix),
        *_expected_keys(row.get("expected_content_keys"), prefix),
        *_validate_profile_field(row.get("embedding_profile"), prefix, topics, profiles_usable),
        *_key_list(row.get("lexical_tokens"), "lexical_tokens", prefix),
    ]


def _validate_query_identity(row: Mapping[str, Any], prefix: str) -> list[str]:
    return [
        *_validate_text(row.get("query_id"), "query_id", prefix),
        *_validate_text(row.get("query_text"), "query_text", prefix),
        *_validate_subset(row.get("subset"), prefix),
    ]


def _validate_text(value: object, field: str, prefix: str) -> list[str]:
    if isinstance(value, str) and value.strip():
        return []
    return [f"{prefix} {field} must be a non-empty string"]


def _validate_subset(value: object, prefix: str) -> list[str]:
    if isinstance(value, str) and value in SUBSETS:
        return []
    return [f"{prefix} subset must be one of {sorted(SUBSETS)}, got {value!r}"]


def _expected_keys(value: object, prefix: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{prefix} expected_content_keys must be a non-empty array"]
    return [
        f"{prefix} expected_content_keys items must be non-empty strings"
        for item in value
        if not isinstance(item, str) or not item.strip()
    ]


def _validate_sizes(payload: Mapping[str, Any]) -> list[str]:
    memories = payload.get("memories")
    queries = payload.get("queries")
    errors: list[str] = []
    if isinstance(memories, list) and not MIN_MEMORIES <= len(memories) <= MAX_MEMORIES:
        errors.append(f"memory count {len(memories)} outside [{MIN_MEMORIES}, {MAX_MEMORIES}]")
    if isinstance(queries, list) and not MIN_QUERIES <= len(queries) <= MAX_QUERIES:
        errors.append(f"query count {len(queries)} outside [{MIN_QUERIES}, {MAX_QUERIES}]")
    return errors


def _validate_categories(memories: Mapping[str, dict[str, Any]]) -> list[str]:
    counts = Counter(row["category"] for row in memories.values())
    return [
        f"category {category!r} has {counts[category]} memories (need >= 3)"
        for category in sorted(CATEGORIES)
        if counts[category] < 3
    ]


def _validate_subsets(corpus: Corpus) -> list[str]:
    counts = Counter(query["subset"] for query in corpus.queries)
    errors = [
        f"subset {subset!r} has {counts[subset]} queries (need >= {minimum})"
        for subset, minimum in MIN_PER_SUBSET.items()
        if counts[subset] < minimum
    ]
    for query in corpus.queries:
        errors.extend(_SUBSET_RULES[query["subset"]](corpus, query))
    return errors


def _expected_rows(corpus: Corpus, query: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [corpus.memories[key] for key in query["expected_content_keys"] if key in corpus.memories]


def _validate_dense(corpus: Corpus, query: Mapping[str, Any]) -> list[str]:
    errors = _validate_expected_exist(corpus, query)
    for key in query["expected_content_keys"]:
        row = corpus.memories.get(key)
        if row is None:
            continue
        errors.extend(_validate_dense_answer(corpus, query, row))
    return errors


def _validate_dense_answer(corpus: Corpus, query: Mapping[str, Any], row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    similarity = profile_cosine(query["embedding_profile"], row["embedding_profile"])
    if similarity < DENSE_MIN_COSINE:
        errors.append(
            f"queries[{query['query_id']}] dense answer {row['content_key']!r} has cosine "
            f"{similarity:.3f} < {DENSE_MIN_COSINE}: vector search would not admit it"
        )
    errors.extend(_validate_window(corpus, query, row))
    return errors


def _validate_window(corpus: Corpus, query: Mapping[str, Any], row: Mapping[str, Any]) -> list[str]:
    """Count memories that tie or beat ``row``: the vector channel sorts by distance only.

    Strictly-greater is not enough. With ``ann_limit`` distractors tied at the answer's
    cosine, the answer can be the one left out of the window.
    """
    similarity = profile_cosine(query["embedding_profile"], row["embedding_profile"])
    ahead = sum(
        1
        for other in corpus.memories.values()
        if other["content_key"] != row["content_key"]
        and profile_cosine(query["embedding_profile"], other["embedding_profile"]) >= similarity
    )
    if ahead < corpus.ann_limit:
        return []
    return [
        (
            f"queries[{query['query_id']}] {row['content_key']!r} ties or loses to {ahead} "
            f"memories and can fall outside the top {corpus.ann_limit} the vector channel fetches"
        )
    ]


def _validate_lexical(corpus: Corpus, query: Mapping[str, Any]) -> list[str]:
    errors = _validate_expected_exist(corpus, query)
    tokens = [token.lower() for token in query.get("lexical_tokens") or []]
    if not tokens:
        errors.append(f"queries[{query['query_id']}] lexical subset needs lexical_tokens")
        return errors
    missing_from_query = [token for token in tokens if token not in str(query["query_text"]).lower()]
    if missing_from_query:
        errors.append(
            f"queries[{query['query_id']}] query_text is missing {missing_from_query}: the "
            "sparse channel ANDs the tokenised query terms, so it could not find the answer"
        )
    for row in _expected_rows(corpus, query):
        errors.extend(_validate_lexical_answer(corpus, query, row, tokens))
    return errors


def _validate_lexical_answer(
    corpus: Corpus,
    query: Mapping[str, Any],
    row: Mapping[str, Any],
    tokens: list[str],
) -> list[str]:
    errors: list[str] = []
    similarity = profile_cosine(query["embedding_profile"], row["embedding_profile"])
    if similarity >= corpus.min_similarity:
        errors.append(
            f"queries[{query['query_id']}] lexical answer {row['content_key']!r} has cosine "
            f"{similarity:.3f} >= floor {corpus.min_similarity}: dense retrieval would already "
            "admit it, so the subset proves nothing"
        )
    missing_from_answer = [token for token in tokens if token not in str(row["content"]).lower()]
    if missing_from_answer:
        errors.append(
            f"queries[{query['query_id']}] lexical answer {row['content_key']!r} is missing "
            f"{missing_from_answer}; the sparse channel ANDs the query terms, so an answer "
            "missing one of them is unreachable"
        )
    return errors


def _validate_graph(corpus: Corpus, query: Mapping[str, Any]) -> list[str]:
    errors = _validate_expected_exist(corpus, query)
    for row in _expected_rows(corpus, query):
        twins = row.get("conflicts_with") or []
        if not twins:
            errors.append(
                f"queries[{query['query_id']}] graph answer {row['content_key']!r} has no "
                "pending conflict twin, so suppression has nothing to remove"
            )
            continue
        for twin_key in twins:
            errors.extend(_validate_conflict_pair(corpus, query, row, twin_key))
    return errors


def _validate_conflict_pair(
    corpus: Corpus,
    query: Mapping[str, Any],
    row: Mapping[str, Any],
    twin_key: str,
) -> list[str]:
    errors: list[str] = []
    if twin_key in query["expected_content_keys"]:
        errors.append(
            f"queries[{query['query_id']}] expects the conflicting memory {twin_key!r} alongside "
            "its twin; suppression is supposed to remove one of them"
        )
    twin = corpus.memories.get(twin_key)
    if twin is None:
        return [*errors, f"{row['content_key']!r} conflicts_with unknown key {twin_key!r}"]
    errors.extend(_validate_window(corpus, query, row))
    errors.extend(_validate_window(corpus, query, twin))
    errors.extend(_validate_floor(corpus, query, row))
    twin_similarity = profile_cosine(row["embedding_profile"], twin["embedding_profile"])
    if twin_similarity < GRAPH_PAIR_MIN_COSINE:
        errors.append(
            f"conflict pair {row['content_key']!r} ↔ {twin_key!r} has cosine "
            f"{twin_similarity:.3f} < {GRAPH_PAIR_MIN_COSINE}: the twin would not be retrieved, "
            "so suppression is never exercised"
        )
    query_similarity = profile_cosine(query["embedding_profile"], twin["embedding_profile"])
    if query_similarity < corpus.min_similarity:
        errors.append(
            f"queries[{query['query_id']}] would never retrieve the twin {twin_key!r} "
            f"(cosine {query_similarity:.3f} < floor {corpus.min_similarity}), so the pair is "
            "not competing and suppression is never exercised"
        )
    return errors


def _validate_floor(corpus: Corpus, query: Mapping[str, Any], row: Mapping[str, Any]) -> list[str]:
    similarity = profile_cosine(query["embedding_profile"], row["embedding_profile"])
    if similarity >= corpus.min_similarity:
        return []
    return [
        (
            f"queries[{query['query_id']}] would never retrieve {row['content_key']!r} "
            f"(cosine {similarity:.3f} < floor {corpus.min_similarity}), so the pair is not "
            "competing and suppression is never exercised"
        )
    ]


def _validate_expected_exist(corpus: Corpus, query: Mapping[str, Any]) -> list[str]:
    return [
        f"queries[{query['query_id']}] references unknown content_key {key!r}"
        for key in query["expected_content_keys"]
        if key not in corpus.memories
    ]


def _validate_conflict_targets(memories: Mapping[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for key, row in memories.items():
        for target in row.get("conflicts_with") or []:
            if target == key:
                errors.append(f"{key!r} conflicts_with itself")
            elif target not in memories:
                errors.append(f"{key!r} conflicts_with unknown content_key {target!r}")
    return errors


_SUBSET_RULES = {
    "dense": _validate_dense,
    "lexical": _validate_lexical,
    "graph": _validate_graph,
}


def main(argv: list[str] | None = None) -> int:
    path = _RANK_DIR / "gold_set_v2.json"
    if argv and len(argv) > 1:
        path = resolve_bench_input_path(Path(argv[1]), bench_dir=_RANK_DIR)
    payload = json.loads(path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083
    errors = validate_gold_set_v2(payload)
    if errors:
        print(f"gold set v2 validation failed ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    counts = Counter(query["subset"] for query in payload["queries"])
    print(
        f"ok: {len(payload['memories'])} memories, {len(payload['queries'])} queries "
        f"(dense={counts['dense']} lexical={counts['lexical']} graph={counts['graph']}), "
        f"{len(payload['topics'])} topics"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
