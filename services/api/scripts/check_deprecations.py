"""Check the committed deprecation record (W5.4).

``engineering/architecture-v2/contracts/deprecations.json`` records every
deprecation of a REST contract, a proxy route, a gRPC method, or an MCP tool
schema. The policy it enforces is stated in
``engineering/architecture-v2/16-compatibility-and-versioning.md``: a ``stable``
contract gets **180 days** between its notice and its sunset, a ``beta`` contract
gets **31 days**, and the same window applies to all four surfaces.

The record is the notice of record. An empty ``entries`` array is the correct 1.0
state: nothing is deprecated, and an empty list proves nothing is. An entry is
added only when a deprecation is real, so a phantom deprecation cannot be
committed and a too-short window cannot be announced.

An entry carries ``id``, ``surface``, ``stability``, ``notice_date``,
``sunset_date``, ``status``, ``successor``, ``headers_implemented``,
``evidence``, the surface's selector (``contract_id`` for ``rest``/``grpc``,
``tool`` + ``server`` for ``mcp``, ``path`` for ``proxy``), and the optional
``announced_on``. ``path`` is optional in the schema only so a dedicated rule can
reject it on a non-``proxy`` entry; a ``proxy`` entry must carry it.

``notice_date`` is when the deprecation was planned; ``announced_on`` is when
consumers were actually told. The support window is measured from
``announced_on`` when it is recorded, otherwise from ``notice_date``, and an
``announced`` entry must record it: measuring from an early ``notice_date`` would
promise a window that the real announcement never gave the consumer.

``check`` fails, each with a one-line actionable message, on:

- a ``sunset_date`` that is less than 180 days (``stable``) or 31 days (``beta``)
  after the entry's announcement (``announced_on`` when recorded, otherwise
  ``notice_date``), or a date field that is present but not an exact
  ``YYYY-MM-DD`` string (``null``, a number, and a list all fail: a value that
  cannot be parsed is not a window, and skipping the window would hide the
  defect);
- ``status: announced`` without ``announced_on``, with an ``announced_on`` that
  is not an exact ``YYYY-MM-DD`` string, with one earlier than ``notice_date``,
  or with one later than the day of the check (``announcement-in-future``: an
  announcement is a past event, not a scheduled one);
- ``announced_on`` present and non-null on a ``proposed`` or ``withdrawn`` entry,
  which has not been announced;
- a field whose schema type is wrong, not merely empty: a string field that is
  not a string, or a ``successor``/``evidence`` that is a blank string;
- a ``rest`` entry whose ``contract_id`` has no row in
  ``contracts/rest-route-registry.json``, whose recorded ``stability``
  disagrees with that row, or whose ``contract_id`` appears more than once in
  that registry (the loader is not allowed to resolve the contradiction by
  keeping the last row);
- an ``mcp`` entry whose ``server`` is not ``operator`` or ``memory``, whose
  ``tool`` is absent from that server's committed ``mcp_tools.json``, or whose
  recorded ``stability`` disagrees with the tool's descriptor entry;
- a ``proxy`` entry whose ``path`` is missing, or whose ``path`` is not one exact
  route path (``^/[^/]+(/[^/]+)*$``, with no ``{}``, ``?``, ``#``, or
  whitespace), or a ``path`` on a non-``proxy`` entry;
- two announcing ``proxy`` entries on one ``path`` (``duplicate-path``), which the
  proxy refuses to start on. The scope is the loader's, not the surface's: only an
  entry the loader announces (``status: announced`` with
  ``headers_implemented: true``) enters its notice map, so a proposal and an
  announcement may name the same path, and two proposals may;
- an empty or blank ``successor``, or a ``successor`` that names the contract
  itself;
- ``status: announced`` with an ``evidence`` path that is not a string, is
  blank, does not exist as a file inside the repository, or with a
  ``sunset_date`` already in the past;
- ``headers_implemented: true`` on a ``grpc`` or ``mcp`` entry,
  ``status: announced`` on a ``rest`` or ``proxy`` entry with
  ``headers_implemented: false``, and ``headers_implemented: true`` on a
  ``rest`` or ``proxy`` entry that is still ``proposed`` or ``withdrawn``;
- an unknown ``surface``/``stability``/``status`` value, an unknown or missing
  field, a missing or malformed record schema, a duplicate ``id``, or entries
  that are not sorted by ``id``.

The header rule is per surface because the wire affordance is per surface. A REST
response and a proxy response can carry RFC 9745 ``Deprecation``, RFC 8594
``Sunset``, and a ``Link`` relation; gRPC methods and MCP tools define no standard
deprecation header, so for them the committed record is the notice of record and
``headers_implemented`` must be ``false``. The flag is a declaration, not a
measurement: this check trusts it plus the ``evidence`` path and cannot prove
that an emitter exists. Two emitters write these headers today:
``services/api/app/middleware/deprecations.py`` for ``rest`` and
``services/proxy/internal/http/deprecations.go`` for ``proxy``.

A ``grpc`` entry is validated structurally and against the window, and its
``contract_id`` is resolved against the contract registry's ``grpc_methods`` rows
for existence and stability, the same rule a ``rest`` entry gets. The registry
still declares gRPC message shapes out of scope (``out_of_scope.grpc``), where
``buf-breaking`` (W5.1) and P0-12 govern them.

No network access, no third-party dependency, deterministic sorted output. This
script never writes; it only reads the record and the two registries.

The rules live beside this file, so this module stays the entry point and the
record's envelope: ``deprecations_model`` holds the record's shape, vocabulary,
and JSON readers; ``deprecations_fields`` the per-entry value rules;
``deprecations_paths`` the proxy selector and the duplicate-path rule; and
``deprecations_cross`` the REST registry and MCP descriptor cross-checks. The
invocation is unchanged::

    cd services/api && .venv/bin/python scripts/check_deprecations.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import deprecations_cross as cross
import deprecations_fields as fields
import deprecations_paths as path_rules
from deprecations_model import (
    DEFAULT_PATHS,
    SCHEMA,
    CheckContext,
    DeprecationPaths,
    display_path,
    entry_label,
    load_mcp_tools,
    load_record,
    load_rest_registry,
    non_empty_str,
)


def _schema_failures(record: dict[str, object]) -> list[str]:
    if record.get("schema") != SCHEMA:
        return [f"unknown-enum: record schema is {record.get('schema')!r}; expected {SCHEMA!r}"]
    return []


def _duplicate_id_failures(entries: list[object]) -> list[str]:
    first_index: dict[str, int] = {}
    failures: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not non_empty_str(entry.get("id")):
            continue
        entry_id = str(entry["id"])
        if entry_id in first_index:
            failures.append(
                f"duplicate-id: {entry_id} appears at entries[{first_index[entry_id]}] and "
                f"entries[{index}]"
            )
        else:
            first_index[entry_id] = index
    return failures


def _unsorted_failures(entries: list[object]) -> list[str]:
    """Report the first entry out of order, naming what it is and what belongs there."""
    ids = [
        str(entry["id"])
        for entry in entries
        if isinstance(entry, dict) and non_empty_str(entry.get("id"))
    ]
    for index, expected in enumerate(sorted(ids)):
        if ids[index] != expected:
            return [
                (
                    f"unsorted-record: entries[{index}] is {ids[index]!r}; expected {expected!r} "
                    "(entries are sorted by id)"
                )
            ]
    return []


def _entry_failures(entry: object, index: int, context: CheckContext) -> list[str]:
    if not isinstance(entry, dict):
        return [f"invalid-row: entries[{index}] is not a JSON object"]
    label = entry_label(entry, index)
    failures = fields.entry_failures(entry, label, context)
    failures.extend(cross.registry_failures(entry, label, context))
    return failures


def _entries_failures(entries: list[object], context: CheckContext) -> list[str]:
    failures: list[str] = []
    for index, entry in enumerate(entries):
        failures.extend(_entry_failures(entry, index, context))
    failures.extend(_duplicate_id_failures(entries))
    failures.extend(path_rules.duplicate_path_failures(entries))
    failures.extend(_unsorted_failures(entries))
    return failures


def _record_has_no_entries(path: Path) -> bool:
    """True only when the record loads cleanly and declares an empty entries array."""
    record, failures = load_record(path)
    return not failures and record.get("entries") == []


def check(paths: DeprecationPaths = DEFAULT_PATHS, today: date | None = None) -> list[str]:
    """Return every failure; an empty list means the record is valid."""
    record, failures = load_record(paths.record)
    rest, rest_failures = load_rest_registry(paths.rest_registry)
    mcp, mcp_paths, mcp_failures = load_mcp_tools(paths)
    failures.extend(rest_failures)
    failures.extend(mcp_failures)
    if failures:
        return sorted(failures)

    failures.extend(_schema_failures(record))
    entries = record.get("entries")
    if not isinstance(entries, list):
        return sorted(failures + ['missing-field: record needs an "entries" array'])

    context = CheckContext(
        rest=rest,
        rest_label=display_path(paths.rest_registry),
        mcp=mcp,
        mcp_paths=mcp_paths,
        root=paths.root,
        today=today or datetime.now(UTC).date(),
    )
    failures.extend(_entries_failures(entries, context))
    return sorted(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check the committed deprecation record against the REST and MCP registries "
            "and the 180-day stable / 31-day beta support window."
        ),
        epilog=(
            "The check mode is the only mode: this script reads the record and the two "
            "registries and never writes. An empty entries array is valid and is the "
            "correct state when nothing is deprecated."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the committed record (the default, and the only mode)",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=DEFAULT_PATHS.record,
        help="path to the deprecation record (input only; never written)",
    )
    parser.add_argument("--rest-registry", type=Path, default=DEFAULT_PATHS.rest_registry)
    parser.add_argument("--mcp-root", type=Path, default=DEFAULT_PATHS.mcp_root)
    parser.add_argument("--root", type=Path, default=DEFAULT_PATHS.root)
    args = parser.parse_args(argv)
    paths = DeprecationPaths(
        record=args.record,
        rest_registry=args.rest_registry,
        mcp_root=args.mcp_root,
        root=args.root,
    )

    failures = check(paths)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"deprecation check failed: {len(failures)} problem(s) in {paths.record}")
        return 1
    print(f"deprecation record is valid: {paths.record}")
    if _record_has_no_entries(paths.record):
        print("note: an empty entries array means nothing is deprecated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
