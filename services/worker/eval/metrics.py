"""Pure scoring for extraction quality eval (m3.5.B.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from match import label_set, match_memories, normalize_content

CATEGORIES = (
    "factual",
    "preference",
    "behavioral",
    "episodic",
    "procedural",
)

# Re-export for existing tests/imports.
__all__ = [
    "CATEGORIES",
    "CategoryCounts",
    "TurnScore",
    "aggregate_scores",
    "gated_metric_names",
    "match_memories",
    "normalize_content",
    "score_turn",
]


@dataclass(frozen=True, slots=True)
class CategoryCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0

    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0


@dataclass(frozen=True, slots=True)
class TurnScore:
    category_counts: dict[str, CategoryCounts]
    category_assignment_correct: int
    category_assignment_total: int
    temporal_correct: int
    temporal_total: int


@dataclass(slots=True)
class _TurnAccum:
    counts: dict[str, CategoryCounts]
    assign_correct: int = 0
    temporal_correct: int = 0
    temporal_total: int = 0


def _bump_category(
    counts: dict[str, CategoryCounts],
    cat: str,
    *,
    in_p: bool,
    in_e: bool,
) -> None:
    cur = counts[cat]
    if in_p and in_e:
        counts[cat] = CategoryCounts(cur.tp + 1, cur.fp, cur.fn)
        return
    if in_p:
        counts[cat] = CategoryCounts(cur.tp, cur.fp + 1, cur.fn)
        return
    if in_e:
        counts[cat] = CategoryCounts(cur.tp, cur.fp, cur.fn + 1)


def _update_category_counts(
    counts: dict[str, CategoryCounts],
    pred_labels: frozenset[str],
    exp_labels: frozenset[str],
) -> None:
    for cat in CATEGORIES:
        _bump_category(
            counts,
            cat,
            in_p=cat in pred_labels,
            in_e=cat in exp_labels,
        )


def _normalize_temporal(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return text


def _temporal_fields_match(pred: dict[str, Any], exp: dict[str, Any]) -> bool:
    return _normalize_temporal(pred.get("valid_from")) == _normalize_temporal(
        exp.get("valid_from")
    ) and _normalize_temporal(pred.get("valid_until")) == _normalize_temporal(
        exp.get("valid_until")
    )


def _score_temporal_pair(
    pred: dict[str, Any] | None,
    exp: dict[str, Any] | None,
) -> tuple[int, int]:
    if exp is None:
        return 0, 0
    if pred is None:
        return 0, 1
    if _temporal_fields_match(pred, exp):
        return 1, 1
    return 0, 1


def _apply_pair(
    accum: _TurnAccum,
    pair: tuple[int | None, int | None],
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> None:
    pi, ei = pair
    pred = predicted[pi] if pi is not None else None
    exp = expected[ei] if ei is not None else None
    pred_labels = label_set(pred) if pred is not None else frozenset()
    exp_labels = label_set(exp) if exp is not None else frozenset()
    if pi is not None and ei is not None and pred_labels == exp_labels:
        accum.assign_correct += 1
    _update_category_counts(accum.counts, pred_labels, exp_labels)
    t_ok, t_total = _score_temporal_pair(pred, exp)
    accum.temporal_correct += t_ok
    accum.temporal_total += t_total


def score_turn(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    temporal_kinds: list[str] | None = None,
) -> TurnScore:
    """Score one turn. temporal_kinds length must match expected memories."""
    kinds = temporal_kinds or ["indefinite"] * len(expected)
    if len(kinds) != len(expected):
        raise ValueError("temporal_kinds length must match expected memories")

    accum = _TurnAccum(counts={cat: CategoryCounts() for cat in CATEGORIES})
    for pair in match_memories(predicted, expected):
        _apply_pair(accum, pair, predicted, expected)

    assign_total = max(len(predicted), len(expected), 1)
    assign_correct = accum.assign_correct
    if not predicted and not expected:
        assign_correct = 1
        assign_total = 1

    return TurnScore(
        category_counts=accum.counts,
        category_assignment_correct=assign_correct,
        category_assignment_total=assign_total,
        temporal_correct=accum.temporal_correct,
        temporal_total=accum.temporal_total,
    )


def aggregate_scores(turns: Iterable[TurnScore]) -> dict[str, float]:
    """Flatten turn scores into gate metrics (fractions 0..1)."""
    cat_tp = dict.fromkeys(CATEGORIES, 0)
    cat_fp = dict.fromkeys(CATEGORIES, 0)
    cat_fn = dict.fromkeys(CATEGORIES, 0)
    assign_ok = 0
    assign_n = 0
    temp_ok = 0
    temp_n = 0

    for turn in turns:
        for cat, counts in turn.category_counts.items():
            cat_tp[cat] += counts.tp
            cat_fp[cat] += counts.fp
            cat_fn[cat] += counts.fn
        assign_ok += turn.category_assignment_correct
        assign_n += turn.category_assignment_total
        temp_ok += turn.temporal_correct
        temp_n += turn.temporal_total

    metrics: dict[str, float] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    for cat in CATEGORIES:
        cc = CategoryCounts(cat_tp[cat], cat_fp[cat], cat_fn[cat])
        p, r = cc.precision(), cc.recall()
        metrics[f"precision_{cat}"] = p
        metrics[f"recall_{cat}"] = r
        precisions.append(p)
        recalls.append(r)
    metrics["precision_macro"] = sum(precisions) / len(precisions)
    metrics["recall_macro"] = sum(recalls) / len(recalls)
    metrics["category_assignment_accuracy"] = assign_ok / assign_n if assign_n else 1.0
    metrics["temporal_field_accuracy"] = temp_ok / temp_n if temp_n else 1.0
    return metrics


def gated_metric_names() -> list[str]:
    """Metrics the CI gate must check (per-category + temporal + assignment)."""
    names: list[str] = []
    for cat in CATEGORIES:
        names.append(f"precision_{cat}")
        names.append(f"recall_{cat}")
    names.extend(
        [
            "category_assignment_accuracy",
            "temporal_field_accuracy",
            "precision_macro",
            "recall_macro",
        ]
    )
    return names
