"""RFC 9745 ``Deprecation`` and RFC 8594 ``Sunset`` headers for REST deprecations (P1-01).

``engineering/architecture-v2/contracts/deprecations.json`` is the notice of record, and
``scripts/check_deprecations.py`` gates it at commit time. This module is the REST emitter half:
it turns the entries a response can carry into headers.

The work happens once, when the application is constructed. ``load_deprecation_headers`` reads
the record and the committed route registry
(``engineering/architecture-v2/contracts/rest-route-registry.json``) and returns
``"METHOD /path" -> RouteNotice`` for every registry route whose contract is deprecated. A
``RouteNotice`` carries the header pair and the sunset boundary it stops at. The middleware then
does one dict lookup and one date comparison per response and nothing else, and ``create_app``
mounts it only when that map is non-empty: an empty record leaves the middleware stack exactly as
it was, so the 1.0 state costs no hop, no closure and no lookup. The middleware also guards on an
empty map itself, so a direct user of it gets the same no-op.

The sunset boundary is rechecked on every request, not only when the application is built. A
process that starts inside a window would otherwise keep announcing a removal date that has
already passed until someone restarted it; the notice stops on the day after its sunset without a
restart. The record is still read once, so a record edited while the process runs is not picked
up: only the passage of time is.

The registry is the only route map. A second hand-maintained list of paths would drift from it, so
a contract is resolved by its ``contract_id`` and the route is the registry row's ``key``.

Three rules decide whether a route is in that map:

* the entry is ``surface: "rest"``, its ``status`` is ``announced``, and it declares
  ``headers_implemented: true``. A header is a claim, and the record only carries one for an entry
  that declares the emitter. A ``proposed`` entry emits nothing: the policy says both emitters act
  only on ``announced``, and a header for a deprecation consumers were never told about announces
  something that is not on offer. The checker rejects ``headers_implemented: true`` on a
  ``proposed`` entry too, so that branch is defence in depth rather than the only guard;
* its ``contract_id`` is the ``contract_id`` of a registry row, which names the route;
* its ``sunset_date`` is not in the past, and not before its announcement date, so the ``Sunset``
  value never precedes the ``Deprecation`` value. A deprecation whose removal date has passed is no
  longer a notice to give: the contract should have been removed, and a ``Sunset`` in the past tells
  a consumer to migrate by a date that has already gone. The entry is skipped rather than fatal, so
  one expired deprecation cannot silence a live one. An entry with an empty ``sunset_date``, or with
  neither ``announced_on`` nor ``notice_date``, is skipped for the same reason: the emitter cannot
  invent the date it is missing.

``Deprecation`` carries an RFC 9651 Date (``@<epoch seconds>``) for the same anchor the policy
measures the window from — ``announced_on`` when recorded, otherwise ``notice_date`` — so the
header and the record cannot disagree about when the clock started. ``Sunset`` carries the RFC 8594
HTTP-date.

Failure behaviour is fail-closed on the claim: an unreadable record, an unreadable registry, or a
record that is structurally invalid yields an empty map and one logged error per failure, so the
process serves without headers rather than serving a header the record does not support. Partial
trust is how a wrong date reaches a consumer, and the emitter cannot choose between two entries
that deprecate the same contract.

Structural validity mirrors the checker for the fields this module reads: schema id, ``entries``
array, the id, surface, stability, status, boolean, selector and date fields, duplicate ids, entry
order, and a duplicate emitting contract. The surface enum is the record's, not this module's: a
``proxy`` entry is valid here and emits nothing, because the proxy is its emitter. The policy rules
— the 180/31-day window, evidence existence, the registry and MCP cross-checks, and the
announcement timing — stay in that gate and are not copied here, because a second copy of a
business rule drifts from the first.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_REPO_ROOT: Final = Path(__file__).resolve().parents[4]
DEFAULT_RECORD: Final = _REPO_ROOT / "engineering/architecture-v2/contracts/deprecations.json"
DEFAULT_REGISTRY: Final = (
    _REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
)

SCHEMA: Final = "ibex.deprecations.v1"
_HEADER_SURFACE: Final = "rest"
# The policy in 16-compatibility-and-versioning.md is explicit: both emitters act only on
# ``announced``. A ``proposed`` entry is a plan and a ``withdrawn`` one was cancelled, so neither
# is announced on the wire. The checker also forbids ``headers_implemented: true`` on a
# ``proposed`` entry, so this is defence in depth: the emitter must not depend on that gate to
# keep a plan off the wire.
_EMITTING_STATUSES: Final = frozenset({"announced"})
# The record's surface enum, not the set of surfaces this module emits for. A proxy entry is a
# valid record entry (the proxy announces it), so rejecting it here would fail the whole record
# closed and silence the REST headers the moment the record gains its first proxy deprecation.
_SURFACES: Final = frozenset({"rest", "grpc", "mcp", "proxy"})
_STABILITIES: Final = frozenset({"stable", "beta"})
_STATUSES: Final = frozenset({"proposed", "announced", "withdrawn"})
_ENUMS: Final = (("surface", _SURFACES), ("stability", _STABILITIES), ("status", _STATUSES))
# ``announced_on`` is optional and may be explicitly null; an empty string is treated the same
# way, which is how the checker treats an empty date field.
_DATE_FIELDS: Final = ("notice_date", "sunset_date", "announced_on")

HeaderPairs = tuple[tuple[bytes, bytes], ...]


@dataclass(frozen=True)
class RouteNotice:
    """One route's headers and the sunset boundary they stop at.

    The boundary is kept beside the headers, not only compared when the application is
    built: a process that starts before a sunset keeps serving until it restarts, so the
    emitter rechecks the day on every response and stops on the day after the sunset.
    """

    headers: HeaderPairs
    sunset: date


@dataclass(frozen=True)
class DeprecationHeaders:
    """What this process will emit, and why it may emit nothing.

    ``routes`` is empty in the normal 1.0 state (the committed record has no entries) and empty
    when the record could not be trusted. ``failures`` says which of the two, so an operator can
    tell "nothing is deprecated" from "the notice of record did not load".
    """

    routes: Mapping[str, RouteNotice] = field(default_factory=dict)
    failures: tuple[str, ...] = ()


def load_deprecation_headers(
    record: Path | None = None,
    registry: Path | None = None,
    *,
    today: date | None = None,
) -> DeprecationHeaders:
    """Read the record and the registry once, and build the per-route header map.

    ``today`` exists so a test can pin the sunset boundary; production passes nothing.
    """
    routes, registry_failures = _load_routes(registry or DEFAULT_REGISTRY)
    entries, record_failures = _load_entries(record or DEFAULT_RECORD)
    failures = sorted([*registry_failures, *record_failures])
    if failures:
        for failure in failures:
            logger.error("deprecation headers disabled: %s", failure)
        return DeprecationHeaders(failures=tuple(failures))
    headers = _route_headers(routes, entries, today or _utc_today())
    if headers:
        logger.info("deprecation headers active: %d route(s)", len(headers))
    return DeprecationHeaders(routes=headers)


class DeprecationHeadersMiddleware:
    """Attach the deprecation headers to the responses of deprecated REST routes.

    Pure ASGI, so no request state is kept and no file is read per request. The router has already
    merged the matched route into ``scope`` by the time ``http.response.start`` reaches this layer;
    ``_route_key`` states why that is true and what happens when it is not.
    """

    def __init__(self, app: ASGIApp, routes: Mapping[str, RouteNotice] | None = None) -> None:
        self.app = app
        self._routes = routes or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._routes:
            await self.app(scope, receive, send)
            return
        today = _utc_today()

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                notice = self._routes.get(_route_key(scope))
                message = _add_headers(message, notice, today)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _utc_today() -> date:
    """The current UTC day, read per request so a long-running process can cross a sunset."""
    return datetime.now(UTC).date()


def _route_key(scope: Scope) -> str | None:
    """The registry key for the route the router matched, or ``None``.

    FastAPI's ``APIRoute.matches`` returns the route in the child scope, and the router merges that
    child scope into the request ``scope`` before the route handles the request, so this layer sees
    ``scope["route"]`` once the response starts. A plain Starlette ``Route`` does not set it, and an
    unmatched request (404) has no route, so both resolve to ``None`` and emit nothing. The
    template path is used, not ``scope["path"]``: the registry key is ``GET /v1/agents/{agent_id}``,
    which no request path with a real id would ever equal.
    """
    path = getattr(scope.get("route"), "path", None)
    if not isinstance(path, str):
        return None
    return f"{scope.get('method', '')} {path}"


def _add_headers(message: Message, notice: RouteNotice | None, today: date) -> Message:
    """Append the headers the route declared, never overwriting one the route already set.

    A notice whose sunset day has passed is not emitted: the record is read once, so the day
    has to be rechecked here or a process that started inside the window would keep announcing
    a removal date that has already gone.
    """
    if notice is None or not _not_before(notice.sunset, today):
        return message
    present = {name.lower() for name, _ in message.get("headers", [])}
    added = [(name, value) for name, value in notice.headers if name not in present]
    if not added:
        return message
    return {**message, "headers": [*message.get("headers", []), *added]}


def _route_headers(
    routes: Mapping[str, str],
    entries: list[dict[str, object]],
    today: date,
) -> dict[str, RouteNotice]:
    """``"METHOD /path" -> notice`` for every deprecated registry route."""
    keys_by_contract: dict[str, list[str]] = {}
    for key, contract_id in routes.items():
        keys_by_contract.setdefault(contract_id, []).append(key)
    headers: dict[str, RouteNotice] = {}
    for entry in entries:
        notice = _emit_notice(entry, today)
        if notice is None:
            continue
        for key in keys_by_contract.get(str(entry["contract_id"]), ()):
            headers[key] = notice
    return headers


def _emit_notice(entry: Mapping[str, object], today: date) -> RouteNotice | None:
    """The notice for one entry, or ``None`` when it does not carry a live notice."""
    if not _is_emitting(entry):
        return None
    announced = _announced_date(entry)
    sunset = _parse_date(entry.get("sunset_date"))
    if announced is None or sunset is None:
        return None
    if not _is_live_notice(announced, sunset, today):
        return None
    return RouteNotice(headers=_header_pairs(announced, sunset), sunset=sunset)


def _header_pairs(announced: date, sunset: date) -> HeaderPairs:
    return (
        (b"deprecation", f"@{_epoch(announced)}".encode("ascii")),
        (b"sunset", _http_date(sunset).encode("ascii")),
    )


def _announced_date(entry: Mapping[str, object]) -> date | None:
    """The anchor the policy measures the window from: ``announced_on``, else ``notice_date``."""
    return _parse_date(entry.get("announced_on")) or _parse_date(entry.get("notice_date"))


def _is_live_notice(announced: date, sunset: date, today: date) -> bool:
    """True when the sunset is not before the announcement and has not already passed."""
    return _not_before(sunset, announced) and _not_before(sunset, today)


def _not_before(day: date, anchor: date) -> bool:
    """``Sunset`` never precedes ``Deprecation``, and never names a date already gone."""
    return day >= anchor


def _is_emitting(entry: Mapping[str, object]) -> bool:
    return (
        entry.get("surface") == _HEADER_SURFACE
        and entry.get("status") in _EMITTING_STATUSES
        and entry.get("headers_implemented") is True
    )


def _epoch(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


def _http_date(day: date) -> str:
    return format_datetime(datetime(day.year, day.month, day.day, tzinfo=UTC), usegmt=True)


def _load_routes(path: Path) -> tuple[dict[str, str], list[str]]:
    """``"METHOD /path" -> contract_id`` from the committed registry."""
    payload, failures = _read_json_object(path, "rest-registry")
    if failures:
        return {}, failures
    rows = payload.get("routes")
    if not isinstance(rows, list):
        return {}, [f'missing-field: {path} needs a "routes" array']
    return _index_routes(rows, path)


def _index_routes(rows: list[object], path: Path) -> tuple[dict[str, str], list[str]]:
    routes: dict[str, str] = {}
    failures: list[str] = []
    for index, row in enumerate(rows):
        key, contract_id = _route_row(row)
        if key is None or contract_id is None:
            failures.append(
                f'invalid-route: {path} routes[{index}] needs a "METHOD /path" key and a '
                "contract_id"
            )
        elif key in routes:
            failures.append(f"duplicate-route: {path} lists {key!r} more than once")
        else:
            routes[key] = contract_id
    return routes, failures


def _route_row(row: object) -> tuple[str | None, str | None]:
    if not isinstance(row, dict):
        return None, None
    key, contract_id = row.get("key"), row.get("contract_id")
    if not _non_empty_str(key) or not _non_empty_str(contract_id):
        return None, None
    method, _, path = str(key).partition(" ")
    if not method or not path.startswith("/"):
        return None, None
    return f"{method} {path}", str(contract_id)


def _load_entries(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    record, failures = _read_json_object(path, "record")
    if failures:
        return [], failures
    if record.get("schema") != SCHEMA:
        return [], [f"unknown-enum: record schema is {record.get('schema')!r}; expected {SCHEMA!r}"]
    entries = record.get("entries")
    if not isinstance(entries, list):
        return [], ['missing-field: record needs an "entries" array']
    return _checked_entries(entries)


def _checked_entries(entries: list[object]) -> tuple[list[dict[str, object]], list[str]]:
    failures: list[str] = []
    valid: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        entry_failures = _entry_failures(entry, index)
        failures.extend(entry_failures)
        if not entry_failures and isinstance(entry, dict):
            valid.append(entry)
    failures.extend(_id_failures(valid))
    failures.extend(_contract_failures(valid))
    return valid, failures


def _entry_failures(entry: object, index: int) -> list[str]:
    if not isinstance(entry, dict):
        return [f"invalid-entry: entries[{index}] is not a JSON object"]
    label = _entry_label(entry, index)
    failures = _field_failures(entry, label)
    failures.extend(_enum_failures(entry, label))
    failures.extend(_date_failures(entry, label))
    return failures


def _field_failures(entry: dict[str, object], label: str) -> list[str]:
    """The fields the emitter reads, with the checker's type strictness."""
    failures: list[str] = []
    if not _non_empty_str(entry.get("id")):
        failures.append(f"invalid-field: {label}.id must be a non-empty string")
    headers = entry.get("headers_implemented")
    if not isinstance(headers, bool):
        failures.append(
            f"invalid-field: {label}.headers_implemented must be a boolean, not {headers!r}"
        )
    if entry.get("surface") == _HEADER_SURFACE and not _non_empty_str(entry.get("contract_id")):
        failures.append(
            f"invalid-field: {label}.contract_id must be a non-empty string on a rest entry"
        )
    return failures


def _enum_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for name, allowed in _ENUMS:
        value = entry.get(name)
        if not (isinstance(value, str) and value in allowed):
            failures.append(
                f"unknown-enum: {label} has {name} {value!r}; expected one of {sorted(allowed)}"
            )
    return failures


def _date_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for name in _DATE_FIELDS:
        value = entry.get(name)
        if value is None or value == "":
            continue
        if _parse_date(value) is None:
            failures.append(f"invalid-date: {label}.{name} is {value!r}; expected YYYY-MM-DD")
    return failures


def _id_failures(entries: list[dict[str, object]]) -> list[str]:
    ids = [str(entry["id"]) for entry in entries]
    failures: list[str] = []
    seen: set[str] = set()
    for entry_id in ids:
        if entry_id in seen:
            failures.append(f"duplicate-id: {entry_id} appears more than once")
        seen.add(entry_id)
    ordered = sorted(ids)
    if ids != ordered:
        index = next(
            position
            for position, (actual, expected) in enumerate(zip(ids, ordered, strict=True))
            if actual != expected
        )
        failures.append(
            f"unsorted-record: entries[{index}] is {ids[index]!r}; expected {ordered[index]!r} "
            "(entries are sorted by id)"
        )
    return failures


def _contract_failures(entries: list[dict[str, object]]) -> list[str]:
    """Two live entries for one contract are a contradiction the emitter must not resolve."""
    first_entry: dict[str, str] = {}
    failures: list[str] = []
    for entry in entries:
        if not _is_emitting(entry):
            continue
        contract_id = str(entry["contract_id"])
        first = first_entry.get(contract_id)
        if first is None:
            first_entry[contract_id] = str(entry["id"])
            continue
        failures.append(
            f"duplicate-contract: {first} and {entry['id']} both deprecate {contract_id}; the "
            "emitter cannot choose between them"
        )
    return failures


def _read_json_object(path: Path, label: str) -> tuple[dict[str, object], list[str]]:
    if not path.exists():
        return {}, [f"missing-{label}: {path} does not exist"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        return {}, [f"unreadable-{label}: {path}: {error}"]
    except json.JSONDecodeError as error:
        return {}, [f"invalid-{label}: {path}: {error}"]
    except RecursionError:
        return {}, [f"invalid-{label}: {path}: JSON is nested too deeply to read"]
    if not isinstance(payload, dict):
        return {}, [f"invalid-{label}: {path} must be a JSON object"]
    return payload, []


def _parse_date(value: object) -> date | None:
    """Return the date only for an exact ``YYYY-MM-DD`` string."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _entry_label(entry: dict[str, object], index: int) -> str:
    return str(entry["id"]) if _non_empty_str(entry.get("id")) else f"entries[{index}]"
