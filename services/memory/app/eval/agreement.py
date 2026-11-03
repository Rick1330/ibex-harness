"""Inter-annotator agreement for relevance labels.

The gold set claims two independent labelers, and the milestone gate is a kappa threshold.
Reporting a raw percentage would hide chance agreement; reporting only kappa would hide a
degenerate or skewed design. So this module returns both, plus the confusion matrix the
number came from, and refuses to invent a value when kappa is undefined.

Known limitation, recorded rather than papered over: Cohen's kappa is sensitive to class
prevalence (Feinstein & Cicchetti, 1990). When one relevance level dominates the judgments,
kappa falls even though the labelers agree on almost everything, and the reverse can happen
for a balanced but adversarial split. That is why the report carries the observed agreement
and the matrix beside the statistic: a reviewer can see when kappa is measuring skew instead
of agreement. The milestone gate stays on kappa because it is the pre-registered threshold.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

type ConfusionCounts = dict[tuple[str, str], int]


@dataclass(frozen=True, slots=True)
class KappaResult:
    """Outcome of comparing two label sequences.

    ``kappa`` is ``None`` when it is mathematically undefined — both labelers used exactly
    one category, and it was the same one — because ``(p_o - p_e) / (1 - p_e)`` is ``0/0``
    there. Returning ``1.0`` would turn a degenerate design into a passing gate.
    """

    kappa: float | None
    observed_agreement: float
    expected_agreement: float
    item_count: int
    categories: tuple[str, ...]
    confusion: Mapping[tuple[str, str], int]

    @property
    def defined(self) -> bool:
        return self.kappa is not None

    def agreed_items(self) -> int:
        return sum(count for (left, right), count in self.confusion.items() if left == right)


def cohen_kappa(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
    *,
    categories: Sequence[str] | None = None,
) -> KappaResult:
    """Cohen's kappa for two labelings of the same items.

    ``categories`` fixes the label universe. Pass it explicitly when exporting a report so
    that a category nobody used still appears in the matrix; otherwise the union of the two
    labelings is used, which keeps the arithmetic identical for the observed data.
    """
    universe = _validated_universe(labels_a, labels_b, categories)
    counts = _confusion(labels_a, labels_b)
    total = len(labels_a)
    observed = _observed(counts, total)
    expected = _expected(counts, universe, total)
    return KappaResult(
        kappa=_kappa(observed, expected),
        observed_agreement=observed,
        expected_agreement=expected,
        item_count=total,
        categories=universe,
        confusion=dict(counts),
    )


def _validated_universe(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
    categories: Sequence[str] | None,
) -> tuple[str, ...]:
    """Everything that has to hold before any arithmetic happens.

    Each rule is its own function so the message names exactly one broken invariant.
    """
    _require_same_length(labels_a, labels_b)
    _require_items(labels_a)
    universe = _resolve_universe(labels_a, labels_b, categories)
    _require_unique_categories(universe)
    _require_known_labels(labels_a, labels_b, universe)
    return universe


def _require_same_length(labels_a: Sequence[str], labels_b: Sequence[str]) -> None:
    if len(labels_a) != len(labels_b):
        msg = f"label sequences differ in length: {len(labels_a)} vs {len(labels_b)}"
        raise ValueError(msg)


def _require_items(labels_a: Sequence[str]) -> None:
    if not labels_a:
        msg = "agreement needs at least one item"
        raise ValueError(msg)


def _resolve_universe(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
    categories: Sequence[str] | None,
) -> tuple[str, ...]:
    declared = tuple(categories) if categories is not None else _union(labels_a, labels_b)
    return _require_non_empty(declared)


def _require_non_empty(universe: tuple[str, ...]) -> tuple[str, ...]:
    if not universe:
        msg = "agreement needs at least one category"
        raise ValueError(msg)
    return universe


def _require_unique_categories(universe: tuple[str, ...]) -> None:
    if len(set(universe)) != len(universe):
        msg = "categories must be unique"
        raise ValueError(msg)


def _require_known_labels(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
    universe: tuple[str, ...],
) -> None:
    unknown = sorted((set(labels_a) | set(labels_b)) - set(universe))
    if unknown:
        msg = f"labels outside the declared categories: {unknown}"
        raise ValueError(msg)


def _kappa(observed: float, expected: float) -> float | None:
    if expected >= 1.0:
        # Both labelers assigned one identical category to every item: kappa is 0/0.
        return None
    return (observed - expected) / (1.0 - expected)


def _observed(counts: ConfusionCounts, total: int) -> float:
    agreements = sum(count for (left, right), count in counts.items() if left == right)
    return agreements / total


def _expected(counts: ConfusionCounts, universe: tuple[str, ...], total: int) -> float:
    row = _marginal(counts, first=True)
    column = _marginal(counts, first=False)
    # A declared category nobody used contributes 0 to the marginals.
    product = sum(row.get(label, 0) * column.get(label, 0) for label in universe)
    return product / (total * total)


def _confusion(labels_a: Sequence[str], labels_b: Sequence[str]) -> ConfusionCounts:
    counts: ConfusionCounts = {}
    for left, right in zip(labels_a, labels_b, strict=True):
        counts[(left, right)] = counts.get((left, right), 0) + 1
    return counts


def _marginal(counts: ConfusionCounts, *, first: bool) -> dict[str, int]:
    totals: dict[str, int] = {}
    for (left, right), count in counts.items():
        key = left if first else right
        totals[key] = totals.get(key, 0) + count
    return totals


def _union(labels_a: Sequence[str], labels_b: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(labels_a) | set(labels_b)))
