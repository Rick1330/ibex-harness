"""Reading a recorded multi-mode run: the file format, and what makes one unusable.

Kept apart from scoring on purpose. Scoring is arithmetic over ``QueryOutcome`` values and has
no opinion about JSON; this module owns the format and every rule that decides whether a run
can be published at all. The rules are strict because each one describes a way a run can look
valid while its numbers are wrong or unlabelled.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Files and rows name themselves through these; keeping them together means a row missing any
# of them is reported once, not field by field.
ROW_FIELDS = ("query_id", "subset", "ranked_ids", "expected_ids")


class RecordedRunError(ValueError):
    """A recorded run whose numbers would be wrong or unlabelled if published.

    A ``ValueError`` so callers that already catch malformed input keep working, but named so a
    reader (and a test) can tell it apart from a parse failure inside the JSON decoder.
    """


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """What one mode returned for one query."""

    query_id: str
    subset: str
    ranked_ids: Sequence[str]
    expected_ids: Sequence[str]


@dataclass(frozen=True, slots=True)
class RecordedRun:
    """A recorded run plus the provenance the artifact has to publish with it."""

    modes: Mapping[str, list[QueryOutcome]]
    reranker: str
    gold_set: str | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``json.loads`` keeps the last of a repeated key and reports nothing.

    Two ``full_graph`` blocks would silently collapse to one, so a whole mode could vanish
    from a run that still publishes as complete.
    """
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise RecordedRunError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _required_label(document: Mapping[str, Any], field: str, source: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise RecordedRunError(
            f"{source} does not name its {field}; a published number must carry it"
        )
    return value


def _optional_label(document: Mapping[str, Any], field: str, source: str) -> str | None:
    value = document.get(field)
    if value is not None and not isinstance(value, str):
        raise RecordedRunError(f"{source} {field} must be a string")
    return value


def _string_field(mode: str, index: int, field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise RecordedRunError(f"mode {mode!r} row {index} field {field!r} must be a string")
    return value


def _id_list(mode: str, index: int, field: str, value: Any) -> tuple[str, ...]:
    """Ids are a list of strings, never a string.

    ``tuple("ab")`` is ``("a", "b")``, so coercing would invent two ids and score the row
    without complaint -- which is why this rejects rather than converts.
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RecordedRunError(f"mode {mode!r} row {index} field {field!r} must be a list of strings")
    return tuple(value)


def _row_fields(mode: str, index: int, row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return {name: row[name] for name in ROW_FIELDS}
    except KeyError as exc:
        raise RecordedRunError(f"mode {mode!r} row {index} is missing {exc.args[0]!r}") from exc


def _parse_row(mode: str, index: int, row: Any) -> QueryOutcome:
    if not isinstance(row, Mapping):
        raise RecordedRunError(f"mode {mode!r} row {index} is not an object")
    fields = _row_fields(mode, index, row)
    return QueryOutcome(
        query_id=_string_field(mode, index, "query_id", fields["query_id"]),
        subset=_string_field(mode, index, "subset", fields["subset"]),
        ranked_ids=_id_list(mode, index, "ranked_ids", fields["ranked_ids"]),
        expected_ids=_id_list(mode, index, "expected_ids", fields["expected_ids"]),
    )


def parse_outcomes(mode: str, rows: Any) -> list[QueryOutcome]:
    """Turn one mode's recorded rows into outcomes, naming the bad row when one is malformed."""
    if not isinstance(rows, list):
        # ValueError, not TypeError: the input is a file, and a file with the wrong shape is
        # malformed data rather than a caller misusing an API.
        raise RecordedRunError(
            f"mode {mode!r} must be a list of rows, got {type(rows).__name__}"
        )
    return [_parse_row(mode, index, row) for index, row in enumerate(rows)]


def _preview(ids: Sequence[str], limit: int = 3) -> str:
    shown = ", ".join(ids[:limit])
    return f"{shown}{', …' if len(ids) > limit else ''}"


def _comparability_problems(
    gold: Mapping[str, tuple[str, tuple[str, ...]]],
    keys: Mapping[str, tuple[str, tuple[str, ...]]],
) -> list[str]:
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


def assert_comparable(modes: Mapping[str, Sequence[QueryOutcome]]) -> None:
    """Every mode must be scored on the same queries, with the same gold expectations.

    The gate compares modes against each other, so a mode that silently dropped its hard
    queries would report a better mean while still clearing the per-subset minimum-count
    check. Cross-checking the gold keys is the only thing that catches that.
    """
    gold: dict[str, tuple[str, tuple[str, ...]]] | None = None
    baseline = ""
    for name, outcomes in modes.items():
        keys = {o.query_id: (o.subset, tuple(sorted(o.expected_ids))) for o in outcomes}
        if gold is None:
            gold, baseline = keys, name
            continue
        problems = _comparability_problems(gold, keys)
        if problems:
            raise RecordedRunError(
                f"mode {name!r} is not comparable to {baseline!r}: " + "; ".join(problems)
            )


def _load_document(path: Path) -> Mapping[str, Any]:
    """Decode the recording, rejecting repeated keys and a non-object root."""
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except ValueError as exc:
        raise RecordedRunError(f"{path.name}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise RecordedRunError(f"{path.name} is not a JSON object")
    return document


def _parse_modes(document: Mapping[str, Any], source: str) -> dict[str, list[QueryOutcome]]:
    """Parse every mode and refuse one that is empty or scored on different queries."""
    modes = document.get("modes")
    if not isinstance(modes, Mapping) or not modes:
        raise RecordedRunError(f"{source} has no modes to score")
    parsed: dict[str, list[QueryOutcome]] = {}
    for name, rows in modes.items():
        if isinstance(rows, list) and not rows:
            # With a single mode there is nothing to compare against, so an empty run would
            # otherwise publish ndcg 0.0 over zero queries as if it were a measurement.
            raise RecordedRunError(
                f"mode {name!r} has no rows; a scored mode needs at least one query"
            )
        parsed[name] = parse_outcomes(name, rows)
    assert_comparable(parsed)
    return parsed


def load_recorded(path: Path) -> RecordedRun:
    """Read a recorded run and refuse one that cannot be published honestly.

    The path is resolved by the caller through ``path_guard``; this function only parses and
    validates. Everything it rejects is a run whose numbers would be wrong or unlabelled rather
    than merely malformed.
    """
    document = _load_document(path)
    return RecordedRun(
        modes=_parse_modes(document, path.name),
        reranker=_required_label(document, "reranker", path.name),
        gold_set=_optional_label(document, "gold_set", path.name),
    )
