"""Pure scoring for extraction quality eval (m3.5.B.4).

Deterministic: no LLM calls. Align predicted vs expected memories within a turn
by normalized content, then score per-category P/R, exact category-set accuracy,
and temporal-field accuracy separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

CATEGORIES = (
    "factual",
    "preference",
    "behavioral",
    "episodic",
    "procedural",
)

_WS = re.compile(r"\s+")


def normalize_content(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def label_set(memory: dict[str, Any]) -> frozenset[str]:
    cats = memory.get("categories") or []
    return frozenset(str(item.get("label")) for item in cats if item.get("label"))


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


def _content_similarity(a: str, b: str) -> float:
    na, nb = normalize_content(a), normalize_content(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_memories(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    min_similarity: float = 0.55,
) -> list[tuple[int | None, int | None]]:
    """Greedy 1:1 matches; unmatched appear as (pred_i, None) or (None, exp_j)."""
    pairs: list[tuple[float, int, int]] = []
    for pi, pred in enumerate(predicted):
        for ei, exp in enumerate(expected):
            sim = _content_similarity(str(pred.get("content", "")), str(exp.get("content", "")))
            if sim >= min_similarity:
                pairs.append((sim, pi, ei))
    pairs.sort(reverse=True)
    used_p: set[int] = set()
    used_e: set[int] = set()
    matches: list[tuple[int | None, int | None]] = []
    for _sim, pi, ei in pairs:
        if pi in used_p or ei in used_e:
            continue
        used_p.add(pi)
        used_e.add(ei)
        matches.append((pi, ei))
    for pi in range(len(predicted)):
        if pi not in used_p:
            matches.append((pi, None))
    for ei in range(len(expected)):
        if ei not in used_e:
            matches.append((None, ei))
    return matches


def score_turn(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    temporal_kinds: list[str] | None = None,
) -> TurnScore:
    """Score one turn. temporal_kinds[i] is 'supersession' | 'indefinite' for expected[i]."""
    kinds = temporal_kinds or ["indefinite"] * len(expected)
    if len(kinds) != len(expected):
        raise ValueError("temporal_kinds length must match expected memories")

    matches = match_memories(predicted, expected)
    counts = {cat: CategoryCounts() for cat in CATEGORIES}
    assign_correct = 0
    assign_total = max(len(predicted), len(expected), 1)
    temporal_correct = 0
    temporal_total = 0

    for pi, ei in matches:
        pred = predicted[pi] if pi is not None else None
        exp = expected[ei] if ei is not None else None
        pred_labels = label_set(pred) if pred is not None else frozenset()
        exp_labels = label_set(exp) if exp is not None else frozenset()

        if pi is not None and ei is not None and pred_labels == exp_labels:
            assign_correct += 1

        for cat in CATEGORIES:
            in_p = cat in pred_labels
            in_e = cat in exp_labels
            cur = counts[cat]
            if in_p and in_e:
                counts[cat] = CategoryCounts(cur.tp + 1, cur.fp, cur.fn)
            elif in_p and not in_e:
                counts[cat] = CategoryCounts(cur.tp, cur.fp + 1, cur.fn)
            elif in_e and not in_p:
                counts[cat] = CategoryCounts(cur.tp, cur.fp, cur.fn + 1)

        if ei is not None and exp is not None:
            kind = kinds[ei]
            temporal_total += 1
            until = None if pred is None else pred.get("valid_until")
            if kind == "supersession" and until is not None:
                temporal_correct += 1
            elif kind == "indefinite" and until is None:
                temporal_correct += 1

    # Cap assign_total when both empty → already 1; when both empty correct stays 0
    if not predicted and not expected:
        assign_correct = 1
        assign_total = 1

    return TurnScore(
        category_counts=counts,
        category_assignment_correct=assign_correct,
        category_assignment_total=assign_total,
        temporal_correct=temporal_correct,
        temporal_total=temporal_total,
    )


def aggregate_scores(turns: Iterable[TurnScore]) -> dict[str, float]:
    """Flatten turn scores into gate metrics (fractions 0..1)."""
    cat_tp = {c: 0 for c in CATEGORIES}
    cat_fp = {c: 0 for c in CATEGORIES}
    cat_fn = {c: 0 for c in CATEGORIES}
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
    metrics["category_assignment_accuracy"] = (
        assign_ok / assign_n if assign_n else 1.0
    )
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
