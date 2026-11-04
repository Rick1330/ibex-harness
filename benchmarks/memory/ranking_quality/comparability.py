"""Whether several modes were scored on the same queries.

A benchmark that compares modes is only meaningful if every mode answered the same questions
with the same gold expectations. This module answers that question and nothing else: it returns
the problems it finds rather than raising, so the format layer decides what an incomparable run
means and the check itself has no dependency on it.

Kept out of the parser because it is a claim about the *run*, not the file: a perfectly
well-formed recording can still be incomparable, and then its best-looking row is simply the one
that dropped the queries it could not answer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotation only: the parser imports this module, not the other way round
    from recorded_run import QueryOutcome

GoldKey = tuple[str, tuple[str, ...]]


def _preview(ids: Sequence[str], limit: int = 3) -> str:
    shown = ", ".join(ids[:limit])
    return f"{shown}{', …' if len(ids) > limit else ''}"


def _gold_keys(outcomes: Sequence[QueryOutcome]) -> dict[str, GoldKey]:
    """What a mode was asked, per query: the subset and the relevant ids.

    ``expected_ids`` is sorted because the order a gold set lists them in cannot change a
    grade; everything else here can.
    """
    return {o.query_id: (o.subset, tuple(sorted(o.expected_ids))) for o in outcomes}


def _differences(gold: Mapping[str, GoldKey], keys: Mapping[str, GoldKey]) -> list[str]:
    missing = sorted(set(gold) - set(keys))
    extra = sorted(set(keys) - set(gold))
    differing = sorted(q for q in set(gold) & set(keys) if gold[q] != keys[q])
    problems: list[str] = []
    if missing:
        problems.append(f"missing {len(missing)} queries ({_preview(missing)})")
    if extra:
        problems.append(f"scored {len(extra)} queries the baseline did not ({_preview(extra)})")
    if differing:
        problems.append(
            f"{len(differing)} queries differ in subset or expectations ({_preview(differing)})"
        )
    return problems


def incomparable_modes(modes: Mapping[str, Sequence[QueryOutcome]]) -> list[str]:
    """Return one message per mode that was not scored like the first one, or an empty list.

    The first mode is the baseline by construction: the run is published from a single driver,
    so there is no privileged mode to pick, only an order to keep consistent.
    """
    baseline = ""
    gold: dict[str, GoldKey] | None = None
    problems: list[str] = []
    for name, outcomes in modes.items():
        keys = _gold_keys(outcomes)
        if gold is None:
            gold, baseline = keys, name
            continue
        differences = _differences(gold, keys)
        if differences:
            problems.append(
                f"mode {name!r} is not comparable to {baseline!r}: " + "; ".join(differences)
            )
    return problems
