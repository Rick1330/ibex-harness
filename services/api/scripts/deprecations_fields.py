"""The rules one deprecation entry must satisfy: shape, values, dates, and claims.

Every rule here takes one entry and returns its failures, so the caller can
aggregate them with the proxy path rule, the cross-surface rules, and the
record-level rules without any rule knowing about the others. The record's
vocabulary and loaders are in ``deprecations_model``; the orchestration is in
``check_deprecations.py``.

Standard library only; reads only the evidence path an announced entry cites.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from deprecations_model import (
    ANNOUNCED_FIELD,
    DATE_FIELDS,
    HEADER_SURFACES,
    STABILITIES,
    STATUSES,
    SURFACES,
    UNANNOUNCED_STATUSES,
    WINDOW_DAYS,
    CheckContext,
    empty_string_fields,
    entry_fields,
    missing_fields,
    mistyped_string_fields,
    non_empty_str,
    required_fields,
    root_label,
    unknown_fields,
)
from deprecations_paths import path_field_failures


def _is_unannounced(status: object) -> bool:
    """True only for a known status that has not reached ``announced``.

    The type check is load-bearing: an entry with a non-string ``status`` is reported
    by the enum rule, and this rule must not turn it into a ``TypeError``.
    """
    return isinstance(status, str) and status in UNANNOUNCED_STATUSES


def _field_failures(entry: dict[str, object], label: str, surface: object) -> list[str]:
    """Every required field present, no field outside the surface's schema, none empty."""
    allowed = entry_fields(surface)
    failures: list[str] = []
    missing = missing_fields(entry, required_fields(surface))
    unknown = unknown_fields(entry, allowed)
    empty = empty_string_fields(entry, allowed)
    if missing:
        failures.append(f"missing-field: {label} lacks {', '.join(missing)}")
    if unknown:
        failures.append(f"unknown-field: {label} has {', '.join(unknown)}")
    if empty:
        failures.append(f"empty-field: {label} has empty {', '.join(empty)}")
    failures.extend(
        f"invalid-field: {label}.{field} must be a string, not {entry[field]!r}"
        for field in mistyped_string_fields(entry, allowed)
    )
    return failures


def _enum_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for field, allowed in (("surface", SURFACES), ("stability", STABILITIES), ("status", STATUSES)):
        value = entry.get(field)
        if isinstance(value, str) and value in allowed:
            continue
        failures.append(
            f"unknown-enum: {label} has {field} {value!r}; expected one of {sorted(allowed)}"
        )
    headers = entry.get("headers_implemented")
    if not isinstance(headers, bool):
        failures.append(
            f"invalid-field: {label}.headers_implemented must be a boolean, not {headers!r}"
        )
    return failures


def _parse_date(value: object) -> date | None:
    """Return the date only for an exact ``YYYY-MM-DD`` string."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _date_failure(entry: dict[str, object], field: str, label: str) -> str | None:
    """Return the failure for a date field that is present but not ``YYYY-MM-DD``.

    Any present value is judged, including a non-string one: ``null`` or an
    integer cannot be parsed, so the window would never be evaluated.
    """
    if field not in entry:
        return None
    value = entry[field]
    if value == "":
        return None
    if _parse_date(value) is not None:
        return None
    return f"invalid-date: {label}.{field} is {value!r}; expected YYYY-MM-DD"


def _date_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for field in DATE_FIELDS:
        failure = _date_failure(entry, field, label)
        if failure is not None:
            failures.append(failure)
    return failures


def _missing_announcement_failure(label: str) -> str:
    return (
        f"missing-announcement: {label} is announced but has no announced_on; record the date "
        "consumers were told, because the window is measured from it"
    )


def _announced_on_failures(
    entry: dict[str, object], label: str, context: CheckContext
) -> list[str]:
    """An ``announced`` entry is dated; a proposal or withdrawal carries no date."""
    value = entry.get(ANNOUNCED_FIELD)
    status = entry.get("status")
    if status == "announced":
        return _announcement_date_failures(entry, label, value, context)
    if value is None or not _is_unannounced(status):
        return []
    return [
        (
            f"unexpected-announcement: {label} is {status}, so {ANNOUNCED_FIELD} must be absent "
            f"or null, not {value!r}"
        )
    ]


def _announcement_date_failures(
    entry: dict[str, object], label: str, value: object, context: CheckContext
) -> list[str]:
    """The date the entry was announced: required, real, and between its notice and today."""
    if value is None:
        return [_missing_announcement_failure(label)]
    announced = _parse_date(value)
    if announced is None:
        return [f"invalid-date: {label}.{ANNOUNCED_FIELD} is {value!r}; expected YYYY-MM-DD"]
    notice = _parse_date(entry.get("notice_date"))
    if notice is not None and announced < notice:
        return [
            (
                f"announcement-before-notice: {label} was announced on {announced.isoformat()} "
                f"before its notice_date {notice.isoformat()}; the window cannot start before "
                "the notice"
            )
        ]
    if announced > context.today:
        return [
            (
                f"announcement-in-future: {label} records {ANNOUNCED_FIELD} "
                f"{announced.isoformat()}, which is after today {context.today.isoformat()}; an "
                "announcement is a past event, so record it once consumers have been told"
            )
        ]
    return []


def _window_anchor(entry: dict[str, object]) -> tuple[str, date] | None:
    """The field and date the support window is measured from.

    A recorded announcement wins over ``notice_date``: a plan dated months before
    consumers were told would otherwise promise a window the announcement never
    gave. Without an announcement, ``notice_date`` is the planned start.
    """
    for field in (ANNOUNCED_FIELD, "notice_date"):
        parsed = _parse_date(entry.get(field))
        if parsed is not None:
            return field, parsed
    return None


def _window_days(entry: dict[str, object]) -> tuple[str, str, date, date, int] | None:
    """Return the class, anchor field, anchor date, sunset, and window length."""
    stability = entry.get("stability")
    if not isinstance(stability, str):
        return None
    if stability not in WINDOW_DAYS:
        return None
    anchor = _window_anchor(entry)
    if anchor is None:
        return None
    sunset = _parse_date(entry.get("sunset_date"))
    if sunset is None:
        return None
    field, start = anchor
    return str(stability), field, start, sunset, (sunset - start).days


def _window_failures(entry: dict[str, object], label: str) -> list[str]:
    window = _window_days(entry)
    if window is None:
        return []
    stability, anchor_field, anchor, sunset, actual = window
    minimum = WINDOW_DAYS[stability]
    if actual >= minimum:
        return []
    return [
        (
            f"window-too-short: {label} is {stability}, so sunset_date {sunset.isoformat()} must be "
            f"at least {minimum} days after {anchor_field} {anchor.isoformat()}; this window is "
            f"{actual} day(s)"
        )
    ]


def _contract_target(entry: dict[str, object]) -> str:
    for field in ("contract_id", "tool"):
        value = entry.get(field)
        if non_empty_str(value):
            return str(value)
    return ""


def _successor_failures(entry: dict[str, object], label: str) -> list[str]:
    successor = entry.get("successor")
    if not non_empty_str(successor):
        return []
    if not str(successor).strip():
        return [f"empty-field: {label} has empty successor"]
    if successor == _contract_target(entry):
        return [f"successor-is-self: {label} names {successor!r} as its own successor"]
    return []


def _evidence_reason(evidence: str, root: Path) -> str | None:
    """Return the rule ``evidence`` breaks, or ``None`` when it cites a real repository file."""
    if Path(evidence).is_absolute():
        return "is an absolute path; cite a file inside the repository"
    try:
        resolved = (root / evidence).resolve()
    except OSError:
        return "cannot be resolved"
    if not resolved.is_relative_to(root.resolve()):
        return (
            f"resolves outside {root_label(root)}; evidence must cite a file inside the repository"
        )
    if not resolved.exists():
        return f"does not exist under {root_label(root)}"
    if not resolved.is_file():
        return "is not a regular file"
    return None


def _evidence_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    evidence = entry.get("evidence")
    if not non_empty_str(evidence):
        return []
    reason = _evidence_reason(str(evidence), context.root)
    if reason is None:
        return []
    return [f"missing-evidence: {label} cites {evidence!r}, which {reason}"]


def _not_applicable_header_failure(label: str, surface: str) -> str:
    return (
        f"headers-not-applicable: {label} is {surface}, which has no standard deprecation "
        "header, so headers_implemented must be false; the record is the notice of record"
    )


def _missing_header_failure(label: str) -> str:
    return (
        f"headers-not-implemented: {label} is announced, so headers_implemented must be true; "
        "implement Deprecation and Sunset before announcing"
    )


def _premature_header_failure(label: str, status: str) -> str:
    return (
        f"headers-before-announcement: {label} is {status}, so headers_implemented must be false "
        "until it is announced; a header claims an emitter for a deprecation consumers were "
        "never told about"
    )


def _header_failures(entry: dict[str, object], label: str) -> list[str]:
    """``headers_implemented`` is a per-surface claim: only REST has such headers.

    gRPC methods and MCP tools define no standard deprecation header, so an entry
    for them declaring one is a false claim. A REST entry is the mirror image: the
    flag is true exactly while the entry is announced, because a header for a
    proposed or withdrawn deprecation announces something that is not on offer, and
    an announced entry cannot exist before its emitter ships.
    """
    surface = entry.get("surface")
    if not isinstance(surface, str):
        return []
    headers = entry.get("headers_implemented")
    if surface not in HEADER_SURFACES:
        return [_not_applicable_header_failure(label, surface)] if headers is True else []
    status = entry.get("status")
    if status == "announced":
        return [] if headers is True else [_missing_header_failure(label)]
    if headers is True and _is_unannounced(status):
        return [_premature_header_failure(label, str(status))]
    return []


def _status_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    """An announced deprecation must cite live evidence and still be in window."""
    if entry.get("status") != "announced":
        return []
    failures = _evidence_failures(entry, label, context)
    sunset = _parse_date(entry.get("sunset_date"))
    if sunset is not None and sunset < context.today:
        failures.append(
            f"sunset-passed: {label} is announced but sunset_date {sunset.isoformat()} is in the "
            "past; withdraw it or record the completed removal"
        )
    return failures


def entry_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    """Every rule that reads one entry, in the order the messages were always emitted."""
    failures = _field_failures(entry, label, entry.get("surface"))
    failures.extend(path_field_failures(entry, label))
    failures.extend(_enum_failures(entry, label))
    failures.extend(_date_failures(entry, label))
    failures.extend(_announced_on_failures(entry, label, context))
    failures.extend(_header_failures(entry, label))
    failures.extend(_window_failures(entry, label))
    failures.extend(_successor_failures(entry, label))
    failures.extend(_status_failures(entry, label, context))
    return failures
