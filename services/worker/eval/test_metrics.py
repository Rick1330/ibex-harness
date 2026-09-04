"""Unit tests for extraction eval scoring (no LLM)."""

from __future__ import annotations

from metrics import (
    CATEGORIES,
    aggregate_scores,
    match_memories,
    normalize_content,
    score_turn,
)


def _mem(content: str, *labels: str, valid_until: str | None = None) -> dict:
    return {
        "content": content,
        "categories": [{"label": lab, "confidence": 0.9} for lab in labels],
        "confidence": 0.9,
        "valid_from": None,
        "valid_until": valid_until,
    }


def test_normalize_content_collapses_whitespace() -> None:
    assert normalize_content("  Hello   WORLD \n") == "hello world"


def test_exact_match_perfect_scores() -> None:
    expected = [_mem("User prefers dark mode in the IDE", "preference")]
    predicted = [_mem("User prefers dark mode in the IDE", "preference")]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
    metrics = aggregate_scores([turn])
    assert metrics["precision_preference"] == 1.0
    assert metrics["recall_preference"] == 1.0
    assert metrics["category_assignment_accuracy"] == 1.0
    assert metrics["temporal_field_accuracy"] == 1.0


def test_over_label_penalizes_category_assignment() -> None:
    expected = [_mem("User prefers dark mode in the IDE", "preference")]
    predicted = [
        _mem("User prefers dark mode in the IDE", "preference", "behavioral")
    ]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
    metrics = aggregate_scores([turn])
    assert metrics["category_assignment_accuracy"] == 0.0
    assert metrics["precision_preference"] == 1.0
    assert metrics["precision_behavioral"] == 0.0


def test_under_label_penalizes_category_assignment() -> None:
    expected = [
        _mem("User prefers dark mode and uses vim daily", "preference", "behavioral")
    ]
    predicted = [_mem("User prefers dark mode and uses vim daily", "preference")]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
    metrics = aggregate_scores([turn])
    assert metrics["category_assignment_accuracy"] == 0.0
    assert metrics["recall_behavioral"] == 0.0


def test_unmatched_predicted_is_false_positive() -> None:
    expected = [_mem("Company HQ is in Austin Texas USA", "factual")]
    predicted = [
        _mem("Company HQ is in Austin Texas USA", "factual"),
        _mem("Hallucinated favorite color is purple now", "preference"),
    ]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
    metrics = aggregate_scores([turn])
    assert metrics["precision_preference"] == 0.0
    assert metrics["recall_factual"] == 1.0
    assert metrics["category_assignment_accuracy"] == 0.5


def test_unmatched_expected_is_false_negative() -> None:
    expected = [
        _mem("Company HQ is in Austin Texas USA", "factual"),
        _mem("User prefers dark mode in the IDE", "preference"),
    ]
    predicted = [_mem("Company HQ is in Austin Texas USA", "factual")]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite", "indefinite"])
    metrics = aggregate_scores([turn])
    assert metrics["recall_preference"] == 0.0
    assert metrics["precision_factual"] == 1.0


def test_temporal_supersession_requires_valid_until() -> None:
    expected = [
        _mem(
            "User works at Acme Corp as an engineer",
            "factual",
            valid_until="2026-06-01T00:00:00Z",
        )
    ]
    predicted = [_mem("User works at Acme Corp as an engineer", "factual")]
    bad = score_turn(predicted, expected, temporal_kinds=["supersession"])
    assert aggregate_scores([bad])["temporal_field_accuracy"] == 0.0

    good_pred = [
        _mem(
            "User works at Acme Corp as an engineer",
            "factual",
            valid_until="2026-06-01T00:00:00Z",
        )
    ]
    good = score_turn(good_pred, expected, temporal_kinds=["supersession"])
    assert aggregate_scores([good])["temporal_field_accuracy"] == 1.0


def test_temporal_indefinite_requires_null_valid_until() -> None:
    expected = [_mem("Python is the primary language here", "factual")]
    predicted = [
        _mem(
            "Python is the primary language here",
            "factual",
            valid_until="2026-12-01T00:00:00Z",
        )
    ]
    turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
    assert aggregate_scores([turn])["temporal_field_accuracy"] == 0.0


def test_per_category_metrics_not_hidden_by_macro() -> None:
    turns = [
        score_turn(
            [_mem("HQ is in Austin Texas United States", "factual")],
            [_mem("HQ is in Austin Texas United States", "factual")],
            temporal_kinds=["indefinite"],
        ),
        score_turn(
            [],
            [_mem("User prefers dark mode in the IDE", "preference")],
            temporal_kinds=["indefinite"],
        ),
    ]
    metrics = aggregate_scores(turns)
    assert metrics["recall_factual"] == 1.0
    assert metrics["recall_preference"] == 0.0
    assert metrics["recall_macro"] < 1.0


def test_match_memories_greedy_one_to_one() -> None:
    predicted = [
        _mem("User prefers dark mode in the IDE", "preference"),
        _mem("Deploy uses canary then full rollout", "procedural"),
    ]
    expected = [
        _mem("User prefers dark mode in the IDE", "preference"),
        _mem("Deploy uses canary then full rollout", "procedural"),
    ]
    pairs = match_memories(predicted, expected)
    matched = {(p, e) for p, e in pairs if p is not None and e is not None}
    assert matched == {(0, 0), (1, 1)}


def test_all_categories_present_in_aggregate_keys() -> None:
    metrics = aggregate_scores([])
    for cat in CATEGORIES:
        assert f"precision_{cat}" in metrics
        assert f"recall_{cat}" in metrics


def test_content_similarity_edges_and_substring() -> None:
    from metrics import _content_similarity, match_memories

    assert _content_similarity("", "x") == 0.0
    assert _content_similarity("user prefers dark mode", "user prefers dark") == 0.85
    # Two predicted compete for one expected — only one match kept
    predicted = [
        _mem("User prefers dark mode in the IDE", "preference"),
        _mem("User prefers dark mode in the IDE tonight", "preference"),
    ]
    expected = [_mem("User prefers dark mode in the IDE", "preference")]
    pairs = match_memories(predicted, expected)
    matched = [(p, e) for p, e in pairs if p is not None and e is not None]
    assert len(matched) == 1


def test_score_turn_rejects_mismatched_temporal_kinds() -> None:
    import pytest

    with pytest.raises(ValueError, match="temporal_kinds"):
        score_turn(
            [_mem("User prefers dark mode in the IDE", "preference")],
            [
                _mem("User prefers dark mode in the IDE", "preference"),
                _mem("Company HQ is in Austin Texas USA", "factual"),
            ],
            temporal_kinds=["indefinite"],
        )


def test_empty_both_sides_assignment_is_perfect() -> None:
    turn = score_turn([], [], temporal_kinds=[])
    assert aggregate_scores([turn])["category_assignment_accuracy"] == 1.0
