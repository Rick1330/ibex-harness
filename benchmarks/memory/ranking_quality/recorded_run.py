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

from comparability import incomparable_modes

# A row names itself through these; keeping them together means a row missing any of them is
# reported once, not field by field.
ROW_FIELDS = ("query_id", "subset", "ranked_ids", "expected_ids")
STRING_FIELDS = ("query_id", "subset")


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


def _id_list(mode: str, index: int, field: str, value: Any) -> tuple[str, ...]:
    """Ids are a list of strings, never a string.

    ``tuple("ab")`` is ``("a", "b")``, so coercing would invent two ids and score the row
    without complaint -- which is why this rejects rather than converts.
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RecordedRunError(f"mode {mode!r} row {index} field {field!r} must be a list of strings")
    return tuple(value)


def _row_values(mode: str, index: int, row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return {name: row[name] for name in ROW_FIELDS}
    except KeyError as exc:
        raise RecordedRunError(f"mode {mode!r} row {index} is missing {exc.args[0]!r}") from exc


def _require_strings(mode: str, index: int, values: Mapping[str, Any]) -> None:
    for field in STRING_FIELDS:
        if not isinstance(values[field], str):
            raise RecordedRunError(
                f"mode {mode!r} row {index} field {field!r} must be a string"
            )


def _parse_row(mode: str, index: int, row: Any) -> QueryOutcome:
    if not isinstance(row, Mapping):
        raise RecordedRunError(f"mode {mode!r} row {index} is not an object")
    values = _row_values(mode, index, row)
    _require_strings(mode, index, values)
    return QueryOutcome(
        query_id=values["query_id"],
        subset=values["subset"],
        ranked_ids=_id_list(mode, index, "ranked_ids", values["ranked_ids"]),
        expected_ids=_id_list(mode, index, "expected_ids", values["expected_ids"]),
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


def _require_rows(mode: str, rows: Any) -> None:
    if isinstance(rows, list) and not rows:
        # With a single mode there is nothing to compare against, so an empty run would
        # otherwise publish ndcg 0.0 over zero queries as if it were a measurement.
        raise RecordedRunError(
            f"mode {mode!r} has no rows; a scored mode needs at least one query"
        )


def _mode_rows(modes: Mapping[str, Any], source: str) -> dict[str, list[QueryOutcome]]:
    parsed: dict[str, list[QueryOutcome]] = {}
    for name, rows in modes.items():
        _require_rows(name, rows)
        parsed[name] = parse_outcomes(name, rows)
    return parsed


def _parse_modes(document: Mapping[str, Any], source: str) -> dict[str, list[QueryOutcome]]:
    """Parse every mode and refuse one that is empty or scored on different queries."""
    modes = document.get("modes")
    if not isinstance(modes, Mapping) or not modes:
        raise RecordedRunError(f"{source} has no modes to score")
    parsed = _mode_rows(modes, source)
    problems = incomparable_modes(parsed)
    if problems:
        raise RecordedRunError("; ".join(problems))
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
