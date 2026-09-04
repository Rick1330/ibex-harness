"""Memory matching helpers for extraction quality eval."""

from __future__ import annotations

import re
from typing import Any

_WS = re.compile(r"\s+")


def normalize_content(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def label_set(memory: dict[str, Any]) -> frozenset[str]:
    cats = memory.get("categories") or []
    return frozenset(str(item.get("label")) for item in cats if item.get("label"))


def content_similarity(a: str, b: str) -> float:
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


def _candidate_pairs(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    min_similarity: float,
) -> list[tuple[float, int, int]]:
    pairs: list[tuple[float, int, int]] = []
    for pi, pred in enumerate(predicted):
        for ei, exp in enumerate(expected):
            sim = content_similarity(str(pred.get("content", "")), str(exp.get("content", "")))
            if sim < min_similarity:
                continue
            pairs.append((sim, pi, ei))
    pairs.sort(reverse=True)
    return pairs


def _take_greedy(pairs: list[tuple[float, int, int]]) -> list[tuple[int, int]]:
    used_p: set[int] = set()
    used_e: set[int] = set()
    matched: list[tuple[int, int]] = []
    for _sim, pi, ei in pairs:
        if pi in used_p:
            continue
        if ei in used_e:
            continue
        used_p.add(pi)
        used_e.add(ei)
        matched.append((pi, ei))
    return matched


def match_memories(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    min_similarity: float = 0.55,
) -> list[tuple[int | None, int | None]]:
    """Greedy 1:1 matches; unmatched appear as (pred_i, None) or (None, exp_j)."""
    matched = _take_greedy(_candidate_pairs(predicted, expected, min_similarity))
    used_p = {pi for pi, _ei in matched}
    used_e = {ei for _pi, ei in matched}
    matches: list[tuple[int | None, int | None]] = list(matched)
    matches.extend((pi, None) for pi in range(len(predicted)) if pi not in used_p)
    matches.extend((None, ei) for ei in range(len(expected)) if ei not in used_e)
    return matches
