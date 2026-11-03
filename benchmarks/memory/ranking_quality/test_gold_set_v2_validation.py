"""Tests for the v2 embedding geometry and the corpus validator.

The corpus is built programmatically so the suite can afford a full-size corpus (the
validator enforces 400..600 memories and 120..180 queries) and then mutate exactly one
property per case. Profiles are deliberately *graded* — a one-hot fixture would only ever
produce cosines of 0.0 and 1.0, which is precisely the geometry v2 exists to replace, and it
would leave the thresholds untested.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest
from profiles import (
    EMBEDDING_DIM,
    ProfileError,
    normalise_weights,
    profile_cosine,
    profile_vector,
    validate_topics,
)
from validate_gold_set_v2 import (
    ANN_LIMIT,
    BENCH_MIN_SIMILARITY,
    DENSE_MIN_COSINE,
    GRAPH_PAIR_MIN_COSINE,
    validate_gold_set_v2,
)

TOPICS = {f"topic-{index}": index * 5 for index in range(40)}
# A topic no corpus memory uses, so a margin test can isolate one cosine from the crowd.
TOPICS["topic-margin"] = 400
CATEGORIES = ["factual", "procedural", "preference", "behavioral", "episodic"]


def _profile_at(topic: str, other: str, cosine: float) -> dict[str, float]:
    """A two-topic profile whose cosine against ``{topic: 1.0}`` is exactly ``cosine``."""
    return {topic: cosine, other: math.sqrt(max(0.0, 1.0 - cosine * cosine))}


def _memory(key: str, profile: dict[str, float], age: int, **extra: object) -> dict[str, Any]:
    """One corpus row; ``extra`` carries the optional fields a case needs."""
    row: dict[str, Any] = {
        "content_key": key,
        "content": extra.pop("content", "Durable statement recorded for the ranking gold corpus."),
        "category": extra.pop("category", "factual"),
        "valid_from_days_ago": age,
        "confidence": 0.9,
        "usefulness_score": 0.6,
        "embedding_profile": profile,
    }
    row.update(extra)
    return row


def _valid_corpus() -> dict[str, Any]:
    memories: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    _add_dense(memories, queries)
    _add_lexical(memories, queries)
    _add_graph(memories, queries)
    _add_filler(memories)
    return {
        "schema_version": 2,
        "gold_set": "ranking_quality_v2",
        "topics": dict(TOPICS),
        "min_similarity": BENCH_MIN_SIMILARITY,
        "memories": memories,
        "queries": queries,
    }


def _add_dense(memories: list[dict[str, Any]], queries: list[dict[str, Any]]) -> None:

    # 40 dense answers: unique best match at cosine 0.9 against the query profile.
    for index in range(40):
        topic = f"topic-{index % 10}"
        memories.append(
            _memory(
                f"gold.dense.{index}",
                profile=_profile_at(topic, f"topic-{(index % 10) + 10}", 0.9),
                age=30 + index,
                category=CATEGORIES[index % 5],
            )
        )
        queries.append(
            {
                "query_id": f"q_dense_{index}",
                "query_text": f"what did we settle about {topic}",
                "subset": "dense",
                "embedding_profile": {topic: 1.0},
                "expected_content_keys": [f"gold.dense.{index}"],
            }
        )

def _add_lexical(memories: list[dict[str, Any]], queries: list[dict[str, Any]]) -> None:
    """Orthogonal to the query profile, carrying the rare token the sparse channel needs."""
    for index in range(40):
        topic = f"topic-{index % 5}"
        token = f"DEC-{4400 + index}"
        memories.append(
            _memory(
                f"gold.lexical.{index}",
                profile={f"topic-{10 + index % 10}": 1.0},
                age=40 + index,
                category=CATEGORIES[index % 5],
                content=f"The change ticket {token} pins the retention window for {topic}.",
            )
        )
        queries.append(
            {
                "query_id": f"q_lexical_{index}",
                "query_text": f"retention window for {token}",
                "subset": "lexical",
                "embedding_profile": {topic: 1.0},
                "lexical_tokens": [token],
                "expected_content_keys": [f"gold.lexical.{index}"],
            }
        )

def _add_graph(memories: list[dict[str, Any]], queries: list[dict[str, Any]]) -> None:
    """An active twin in a pending conflict, close enough that both would be retrieved."""
    for index in range(40):
        topic = f"topic-{20 + index % 15}"
        twin_key = f"gold.twin.{index}"
        new_key = f"gold.current.{index}"
        memories.append(_memory(twin_key, profile=_profile_at(topic, "topic-0", GRAPH_PAIR_MIN_COSINE), age=90 + index))
        memories.append(
            _memory(
                new_key,
                profile={topic: 1.0},
                age=10 + index,
                conflicts_with=[twin_key],
            )
        )
        queries.append(
            {
                "query_id": f"q_graph_{index}",
                "query_text": f"current guidance for {topic}",
                "subset": "graph",
                "embedding_profile": {topic: 1.0},
                "expected_content_keys": [new_key],
            }
        )

def _add_filler(memories: list[dict[str, Any]]) -> None:
    """Reach the corpus size floor without outranking any graded answer."""
    while len(memories) < 420:
        index = len(memories)
        memories.append(
            _memory(
                f"gold.filler.{index}",
                profile={"topic-35": 0.5, "topic-36": math.sqrt(0.75)},
                age=20 + index % 100,
                category=CATEGORIES[index % 5],
            )
        )

@pytest.fixture
def corpus() -> dict[str, Any]:
    return _valid_corpus()


def _has(errors: list[str], fragment: str) -> bool:
    return any(fragment in error for error in errors)


def _query(corpus: dict[str, Any], subset: str) -> dict[str, Any]:
    return next(query for query in corpus["queries"] if query["subset"] == subset)


def _memory_row(corpus: dict[str, Any], key: str) -> dict[str, Any]:
    return next(row for row in corpus["memories"] if row["content_key"] == key)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


class TestProfiles:
    def test_weights_are_normalised(self) -> None:
        unit = normalise_weights({"a": 0.3, "b": 0.4})

        assert unit["a"] == pytest.approx(0.6)
        assert unit["b"] == pytest.approx(0.8)

    def test_identical_profiles_have_cosine_one(self) -> None:
        assert profile_cosine({"a": 0.8, "b": 0.6}, {"a": 0.8, "b": 0.6}) == pytest.approx(1.0)

    def test_disjoint_profiles_have_cosine_zero(self) -> None:
        assert profile_cosine({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_shared_topic_gives_a_graded_cosine(self) -> None:
        assert profile_cosine({"a": 0.8, "b": 0.6}, {"a": 0.8, "c": 0.6}) == pytest.approx(0.64)

    def test_two_shared_topics_contribute_independently(self) -> None:
        left = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5}
        right = {"a": 0.5, "b": 0.5, "e": 0.5, "f": 0.5}

        assert profile_cosine(left, right) == pytest.approx(0.5)

    def test_vector_cosine_matches_the_weight_cosine(self) -> None:
        # The corpus design rests on this equality: what the validator computes from the
        # weights is what pgvector computes from the stored vectors.
        left = {"topic-1": 0.8, "topic-2": 0.6}
        right = {"topic-1": 0.6, "topic-3": 0.8}

        vector_a = profile_vector(left, TOPICS)
        vector_b = profile_vector(right, TOPICS)
        norm_a = sum(value * value for value in vector_a) ** 0.5
        norm_b = sum(value * value for value in vector_b) ** 0.5
        dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))

        assert dot / (norm_a * norm_b) == pytest.approx(profile_cosine(left, right))

    def test_stored_vector_is_unit_length(self) -> None:
        vector = profile_vector({"topic-2": 0.6, "topic-4": 0.8}, TOPICS)

        assert sum(value * value for value in vector) ** 0.5 == pytest.approx(1.0)
        assert vector[TOPICS["topic-2"]] == pytest.approx(0.6)

    def test_vector_length_matches_the_embedding_dimension(self) -> None:
        assert len(profile_vector({"topic-0": 1.0}, TOPICS)) == EMBEDDING_DIM

    def test_zero_weight_is_rejected(self) -> None:
        with pytest.raises(ProfileError, match=r"must be in \(0, 1\]"):
            normalise_weights({"a": 0.0})

    def test_above_one_weight_is_rejected(self) -> None:
        with pytest.raises(ProfileError, match=r"must be in \(0, 1\]"):
            normalise_weights({"a": 1.5})

    def test_negative_weight_is_rejected(self) -> None:
        with pytest.raises(ProfileError, match=r"must be in \(0, 1\]"):
            normalise_weights({"a": -0.5})

    def test_non_numeric_weight_is_a_profile_error(self) -> None:
        # A malformed gold set must produce a line to fix, not a TypeError.
        with pytest.raises(ProfileError, match="must be a number"):
            normalise_weights({"a": "heavy"})  # type: ignore[dict-item]

    def test_none_weight_is_a_profile_error(self) -> None:
        with pytest.raises(ProfileError, match="must be a number"):
            normalise_weights({"a": None})  # type: ignore[dict-item]

    def test_empty_profile_is_rejected(self) -> None:
        with pytest.raises(ProfileError, match="at least one topic"):
            normalise_weights({})

    def test_too_many_topics_are_rejected(self) -> None:
        with pytest.raises(ProfileError, match="more than"):
            normalise_weights({f"t{index}": 1.0 for index in range(5)})

    def test_undeclared_topic_is_rejected(self) -> None:
        with pytest.raises(ProfileError, match="not declared"):
            profile_vector({"nope": 1.0}, TOPICS)

    def test_vector_builder_rejects_reused_bases(self) -> None:
        # Two topics on one basis would add their weights and break the cosine identity.
        with pytest.raises(ProfileError, match="reuses basis indices"):
            profile_vector({"a": 0.6, "b": 0.8}, {"a": 0, "b": 0})

    def test_duplicate_bases_are_reported_by_validate_topics(self) -> None:
        errors = validate_topics({"a": 1, "b": 1, "c": EMBEDDING_DIM, "": 3, "d": "4"})

        assert _has(errors, "reused by several topics")
        assert _has(errors, "outside")
        assert _has(errors, "non-empty string")
        assert _has(errors, "must be an integer")


# ---------------------------------------------------------------------------
# Corpus validation
# ---------------------------------------------------------------------------


class TestValidCorpus:
    def test_the_generated_corpus_is_valid(self, corpus: dict[str, Any]) -> None:
        assert validate_gold_set_v2(corpus) == []


class TestHeaderRules:
    def test_wrong_schema_version(self, corpus: dict[str, Any]) -> None:
        corpus["schema_version"] = 1

        assert _has(validate_gold_set_v2(corpus), "schema_version")

    def test_missing_similarity_floor(self, corpus: dict[str, Any]) -> None:
        del corpus["min_similarity"]

        assert _has(validate_gold_set_v2(corpus), "min_similarity is required")

    def test_similarity_floor_must_match_the_harness(self, corpus: dict[str, Any]) -> None:
        # A corpus cannot declare a friendlier floor than the run actually applies.
        corpus["min_similarity"] = 0.9

        assert _has(validate_gold_set_v2(corpus), "does not match the harness floor")

    def test_topic_map_must_be_an_object(self, corpus: dict[str, Any]) -> None:
        corpus["topics"] = []

        assert _has(validate_gold_set_v2(corpus), "topics")

    def test_header_and_body_errors_are_reported_together(self, corpus: dict[str, Any]) -> None:
        corpus["schema_version"] = 1
        corpus["memories"][0]["category"] = "misc"

        errors = validate_gold_set_v2(corpus)

        assert _has(errors, "schema_version")
        assert _has(errors, "invalid category")


class TestMemoryRules:
    def test_duplicate_content_key(self, corpus: dict[str, Any]) -> None:
        corpus["memories"].append(copy.deepcopy(corpus["memories"][0]))

        assert _has(validate_gold_set_v2(corpus), "duplicate content_key")

    def test_unknown_topic_in_profile(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["embedding_profile"] = {"not-a-topic": 1.0}

        assert _has(validate_gold_set_v2(corpus), "undeclared topics")

    def test_profile_with_zero_weight(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["embedding_profile"] = {"topic-0": 0.0}

        assert _has(validate_gold_set_v2(corpus), "must be in (0, 1]")

    def test_non_numeric_weight_is_reported(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["embedding_profile"] = {"topic-0": None}

        assert _has(validate_gold_set_v2(corpus), "must be a number")

    def test_short_content(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["content"] = "too short"

        assert _has(validate_gold_set_v2(corpus), "at least 20 characters")

    def test_invalid_category(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["category"] = "misc"

        assert _has(validate_gold_set_v2(corpus), "invalid category")

    def test_age_outside_range(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["valid_from_days_ago"] = 400

        assert _has(validate_gold_set_v2(corpus), "outside")

    def test_conflicts_with_unknown_key(self, corpus: dict[str, Any]) -> None:
        _memory_row(corpus, "gold.current.0")["conflicts_with"] = ["gold.missing"]

        assert _has(validate_gold_set_v2(corpus), "conflicts_with unknown content_key")

    def test_conflicts_with_self(self, corpus: dict[str, Any]) -> None:
        _memory_row(corpus, "gold.current.0")["conflicts_with"] = ["gold.current.0"]

        assert _has(validate_gold_set_v2(corpus), "conflicts_with itself")


class TestSizeAndCoverage:
    def test_too_few_memories(self, corpus: dict[str, Any]) -> None:
        corpus["memories"] = corpus["memories"][:100]

        assert _has(validate_gold_set_v2(corpus), "memory count")

    def test_too_few_queries(self, corpus: dict[str, Any]) -> None:
        corpus["queries"] = corpus["queries"][:10]

        assert _has(validate_gold_set_v2(corpus), "query count")

    def test_subset_under_its_minimum(self, corpus: dict[str, Any]) -> None:
        corpus["queries"] = [q for q in corpus["queries"] if q["subset"] != "graph"]

        assert _has(validate_gold_set_v2(corpus), "subset 'graph'")


class TestDenseSeparations:
    def test_answer_at_the_margin_passes(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "dense")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at("topic-margin", "topic-10", DENSE_MIN_COSINE)
        query["embedding_profile"] = {"topic-margin": 1.0}

        assert validate_gold_set_v2(corpus) == []

    def test_answer_just_below_the_margin_fails(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "dense")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at("topic-0", "topic-10", DENSE_MIN_COSINE - 0.01)
        query["embedding_profile"] = {"topic-0": 1.0}

        assert _has(validate_gold_set_v2(corpus), "vector search would not admit it")

    def test_answer_outside_the_ann_window_fails(self, corpus: dict[str, Any]) -> None:
        # Ten memories closer to the query than the answer means the answer is never fetched,
        # however far above the floor it sits.
        query = _query(corpus, "dense")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at("topic-0", "topic-10", 0.9)
        query["embedding_profile"] = {"topic-0": 1.0}
        for index in range(ANN_LIMIT):
            corpus["memories"].append(
                _memory(
                    f"gold.blocker.{index}",
                    profile=_profile_at("topic-0", "topic-11", 0.95),
                    age=50,
                )
            )

        errors = validate_gold_set_v2(corpus)

        assert _has(errors, "can fall outside the top")

    def test_dense_query_aspect_must_match_its_answer(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "dense")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        query["aspect"] = "value"
        answer["aspect"] = "an-aspect-nobody-asked-about"

        assert _has(validate_gold_set_v2(corpus), "rewards the wrong row")

    def test_unknown_expected_key(self, corpus: dict[str, Any]) -> None:
        corpus["queries"][0]["expected_content_keys"] = ["gold.nope"]

        assert _has(validate_gold_set_v2(corpus), "references unknown content_key")

    def test_non_string_expected_key_is_reported(self, corpus: dict[str, Any]) -> None:
        corpus["queries"][0]["expected_content_keys"] = [["gold.dense.0"]]

        assert _has(validate_gold_set_v2(corpus), "items must be non-empty strings")


class TestLexicalSeparations:
    def test_answer_at_or_above_the_floor_fails(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "lexical")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = dict(query["embedding_profile"])

        assert _has(validate_gold_set_v2(corpus), "dense retrieval would already admit it")

    def test_answer_just_below_the_floor_passes(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "lexical")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at("topic-0", "topic-19", BENCH_MIN_SIMILARITY - 0.01)
        query["embedding_profile"] = {"topic-0": 1.0}

        assert validate_gold_set_v2(corpus) == []

    def test_answer_must_contain_the_token(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "lexical")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["content"] = "The retention window moved without naming any ticket."

        assert _has(validate_gold_set_v2(corpus), "is missing")

    def test_query_text_must_contain_the_token(self, corpus: dict[str, Any]) -> None:
        # The sparse channel tokenises the query text, so a token only in the corpus is
        # invisible to BM25 and the answer would be unreachable by either channel.
        _query(corpus, "lexical")["query_text"] = "retention window please"

        assert _has(validate_gold_set_v2(corpus), "query_text is missing")

    def test_lexical_subset_requires_tokens(self, corpus: dict[str, Any]) -> None:
        del _query(corpus, "lexical")["lexical_tokens"]

        assert _has(validate_gold_set_v2(corpus), "needs lexical_tokens")


class TestGraphSeparations:
    def test_answer_without_a_conflict_twin_fails(self, corpus: dict[str, Any]) -> None:
        _memory_row(corpus, "gold.current.0").pop("conflicts_with", None)

        assert _has(validate_gold_set_v2(corpus), "no pending conflict twin")

    def test_pair_at_the_margin_passes(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "graph")
        topic = next(iter(query["embedding_profile"]))
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        twin = _memory_row(corpus, answer["conflicts_with"][0])
        twin["embedding_profile"] = _profile_at(topic, "topic-0", GRAPH_PAIR_MIN_COSINE)

        assert validate_gold_set_v2(corpus) == []

    def test_pair_just_below_the_margin_fails(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "graph")
        topic = next(iter(query["embedding_profile"]))
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        twin = _memory_row(corpus, answer["conflicts_with"][0])
        twin["embedding_profile"] = _profile_at(topic, "topic-0", GRAPH_PAIR_MIN_COSINE - 0.01)

        assert _has(validate_gold_set_v2(corpus), "suppression is never exercised")

    def test_twin_must_be_retrievable_for_the_query(self, corpus: dict[str, Any]) -> None:
        # Two memories that never appear in the same page cannot exercise the pairwise rule,
        # so the twin has to clear the floor for this query, not just sit near the answer.
        query = _query(corpus, "graph")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        twin = _memory_row(corpus, answer["conflicts_with"][0])
        # Same pair as before (both on the query topic), but the twin drifts to another topic.
        twin["embedding_profile"] = _profile_at("topic-margin", "topic-3", 0.9)
        answer["embedding_profile"] = {"topic-10": 1.0}
        query["embedding_profile"] = {"topic-10": 1.0}

        assert _has(validate_gold_set_v2(corpus), "would never retrieve the twin")

    def test_expectation_must_not_include_the_twin(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "graph")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        query["expected_content_keys"].append(answer["conflicts_with"][0])

        assert _has(validate_gold_set_v2(corpus), "expects the conflicting memory")


class TestReviewHardening:
    """Cases raised in review: each one used to pass or crash instead of reporting."""

    def test_non_finite_floor_is_rejected(self, corpus: dict[str, Any]) -> None:
        corpus["min_similarity"] = "NaN"

        assert _has(validate_gold_set_v2(corpus), "must be finite")

    def test_malformed_category_is_reported_not_raised(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["category"] = ["factual"]

        assert _has(validate_gold_set_v2(corpus), "invalid category")

    def test_malformed_subset_is_reported_not_raised(self, corpus: dict[str, Any]) -> None:
        corpus["queries"][0]["subset"] = ["dense"]

        assert _has(validate_gold_set_v2(corpus), "subset must be one of")

    def test_ties_can_push_the_answer_out_of_the_window(self, corpus: dict[str, Any]) -> None:
        # Strictly-closer counting misses this: ten memories tied at the answer's cosine can
        # take the window, because the vector channel sorts by distance only.
        query = _query(corpus, "dense")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at("topic-margin", "topic-0", 0.9)
        query["embedding_profile"] = {"topic-margin": 1.0}
        for index in range(ANN_LIMIT):
            corpus["memories"].append(
                _memory(
                    f"gold.tie.{index}",
                    profile=_profile_at("topic-margin", "topic-1", 0.9),
                    age=50,
                )
            )

        assert _has(validate_gold_set_v2(corpus), "ties or loses to")

    def test_every_dense_answer_is_checked(self, corpus: dict[str, Any]) -> None:
        # Recall counts every expected key, so a second, unreachable answer makes the query
        # unsatisfiable even though the first one is perfect.
        query = _query(corpus, "dense")
        corpus["memories"].append(_memory("gold.orthogonal", profile={"topic-35": 1.0}, age=30))
        query["expected_content_keys"].append("gold.orthogonal")

        assert _has(validate_gold_set_v2(corpus), "vector search would not admit it")

    def test_lexical_token_must_reach_the_answer(self, corpus: dict[str, Any]) -> None:
        # The sparse channel ANDs the query terms, so a token present in the query but absent
        # from the answer makes the answer unreachable by both channels.
        query = _query(corpus, "lexical")
        query["lexical_tokens"] = [*query["lexical_tokens"], "quasar"]
        query["query_text"] = f"{query['query_text']} quasar"

        assert _has(validate_gold_set_v2(corpus), "is missing")

    def test_graph_answer_must_fit_the_window(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "graph")
        topic = next(iter(query["embedding_profile"]))
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["embedding_profile"] = _profile_at(topic, "topic-0", 0.81)
        for index in range(ANN_LIMIT):
            corpus["memories"].append(
                _memory(f"gold.graphblock.{index}", profile={topic: 1.0}, age=40)
            )

        assert _has(validate_gold_set_v2(corpus), "can fall outside the top")


class TestSecondReviewRound:
    def test_overflowing_weight_is_a_profile_error(self) -> None:
        with pytest.raises(ProfileError, match="must be a number"):
            normalise_weights({"a": 10**400})  # type: ignore[dict-item]

    def test_unhashable_basis_is_a_profile_error(self) -> None:
        with pytest.raises(ProfileError, match="must be an integer"):
            profile_vector({"a": 1.0}, {"a": ["not", "an", "index"]})  # type: ignore[dict-item]

    def test_mixed_type_profile_keys_do_not_break_the_sort(self, corpus: dict[str, Any]) -> None:
        corpus["memories"][0]["embedding_profile"] = {"topic-0": 1.0, 7: 0.5}

        assert _has(validate_gold_set_v2(corpus), "undeclared topics")

    def test_token_must_match_whole(self, corpus: dict[str, Any]) -> None:
        # "DEC-4400" must not be satisfied by "DEC-44001".
        query = _query(corpus, "lexical")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        answer["content"] = "The ticket DEC-44001 covers a neighbouring change only."

        assert _has(validate_gold_set_v2(corpus), "is missing")

    def test_common_token_is_rejected(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "lexical")
        token = query["lexical_tokens"][0]
        for index in range(ANN_LIMIT + 2):
            corpus["memories"].append(
                _memory(f"gold.common.{index}", profile={"topic-35": 1.0}, age=30,
                        content=f"Shared boilerplate mentioning {token} for every memory.")
            )

        assert _has(validate_gold_set_v2(corpus), "does not isolate the sparse channel")

    def test_expected_answer_must_outrank_its_twin(self, corpus: dict[str, Any]) -> None:
        # Fresh but weakly supported: newer than the twin, yet composite scoring ranks it
        # below, and suppression keeps the higher-ranked row.
        query = _query(corpus, "graph")
        topic = next(iter(query["embedding_profile"]))
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        twin = _memory_row(corpus, answer["conflicts_with"][0])
        answer["embedding_profile"] = _profile_at(topic, "topic-0", 0.8)
        answer["valid_from_days_ago"] = 7
        answer["confidence"] = 0.1
        answer["usefulness_score"] = 0.0
        twin["embedding_profile"] = {topic: 1.0}
        twin["valid_from_days_ago"] = 8
        twin["confidence"] = 1.0
        twin["usefulness_score"] = 1.0

        assert _has(validate_gold_set_v2(corpus), "would be dropped")

    def test_stale_expected_answer_is_rejected(self, corpus: dict[str, Any]) -> None:
        query = _query(corpus, "graph")
        answer = _memory_row(corpus, query["expected_content_keys"][0])
        twin = _memory_row(corpus, answer["conflicts_with"][0])
        answer["valid_from_days_ago"] = 300
        twin["valid_from_days_ago"] = 10

        assert _has(validate_gold_set_v2(corpus), "is older than its")

    def test_missing_corpus_returns_a_clean_failure(self, capsys: Any) -> None:
        from validate_gold_set_v2 import main

        # A relative name resolves inside the bench directory, which the path guard allows.
        assert main(["validate", "gold_set_v2_absent.json"]) == 1
        assert "cannot read gold set" in capsys.readouterr().err


class TestQueryRules:
    def test_duplicate_query_id(self, corpus: dict[str, Any]) -> None:
        corpus["queries"].append(copy.deepcopy(corpus["queries"][0]))

        assert _has(validate_gold_set_v2(corpus), "duplicate query_id")

    def test_unknown_subset(self, corpus: dict[str, Any]) -> None:
        corpus["queries"][0]["subset"] = "vibes"

        assert _has(validate_gold_set_v2(corpus), "subset must be one of")
