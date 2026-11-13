"""The proxy selector: one exact route path, and the duplicate-path rule.

A ``proxy`` entry is addressed by the request path the proxy matches rather than by
a contract id, so it carries a field the other surfaces must not and a grammar the
proxy's own startup check enforces. Two entries that both announce one path are a
contradiction the loader refuses to resolve by keeping the last one, so the
duplicate rule mirrors that check instead of widening it.

Standard library only; reads nothing.
"""

from __future__ import annotations

import re
from typing import Final

from deprecations_model import entry_label

# The proxy surface is addressed by an exact request path rather than a contract
# id, so it owns a selector the other surfaces must not carry.
PROXY_SURFACE: Final = "proxy"
# One exact route path: a leading slash and non-empty segments, with no empty
# segment from a doubled or trailing slash.
PATH_PATTERN: Final = re.compile(r"^/[^/]+(/[^/]+)*$")
# Characters no served route path contains. The pattern admits them inside a
# segment, so they are checked separately, matching the proxy's validator.
PATH_FORBIDDEN: Final = frozenset("{}?#")


def _path_has_forbidden_character(path: str) -> bool:
    """True when a path carries a template, query, fragment, or whitespace."""
    return bool(PATH_FORBIDDEN.intersection(path)) or any(character.isspace() for character in path)


def is_exact_path(path: str) -> bool:
    """True for one exact route path, which the proxy can match and a request can equal."""
    return bool(PATH_PATTERN.fullmatch(path)) and not _path_has_forbidden_character(path)


def path_field_failures(entry: dict[str, object], label: str) -> list[str]:
    """``path`` is the proxy selector: required there, forbidden elsewhere.

    The proxy rejects a path it could never match as a startup error, so a record
    that passes this check must not stop it. The grammar is the proxy's: one
    exact route path with no template, query, fragment, or trailing slash. The
    field is dedicated so a non-``proxy`` entry with ``path`` keeps the exact
    ``unknown-field`` message it had when ``path`` was not in the schema.
    """
    surface = entry.get("surface")
    if surface != PROXY_SURFACE:
        return [f"unknown-field: {label} has path"] if "path" in entry else []
    if "path" not in entry:
        return [f"missing-field: {label} lacks path"]
    path = entry.get("path")
    if not isinstance(path, str):
        return [f"invalid-field: {label}.path must be a string, not {path!r}"]
    if not path:
        return [f"empty-field: {label} has empty path"]
    if is_exact_path(path):
        return []
    return [
        (
            f"invalid-path: {label}.path {path!r} must be one exact route path "
            "(no trailing slash, no template, no query)"
        )
    ]


def _announcing_path(entry: dict[str, object]) -> str | None:
    """The path this entry announces, or ``None`` when the proxy would not announce it.

    The loader (``buildDeprecationNotices``) inserts only an entry it announces —
    ``status: announced`` with ``headers_implemented: true`` — and drops the rest
    before it looks at the path. An entry whose path the loader rejects never
    reaches that check either; ``invalid-path`` already reports it.
    """
    if entry.get("surface") != PROXY_SURFACE:
        return None
    if entry.get("status") != "announced" or entry.get("headers_implemented") is not True:
        return None
    path = entry.get("path")
    if not isinstance(path, str) or not is_exact_path(path):
        return None
    return path


def duplicate_path_failures(entries: list[object]) -> list[str]:
    """Two proxy entries cannot announce one path: the loader fails startup on it.

    The proxy keys its notices by exact request path, so a second entry for a path
    already in the map is a contradiction it refuses to resolve by keeping the last
    one. This rule mirrors that check rather than widening it: two proposals, or a
    proposal and an announcement, are not a duplicate there and are not one here.
    """
    first_id: dict[str, str] = {}
    failures: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        path = _announcing_path(entry)
        if path is None:
            continue
        entry_id = entry_label(entry, index)
        first = first_id.get(path)
        if first is None:
            first_id[path] = entry_id
            continue
        failures.append(f"duplicate-path: {first} and {entry_id} both announce {path}")
    return failures
