"""The contract-ID grammar used by the REST route registry check.

A contract ID is derived mechanically as ``<surface>.<resource>.<action>.v1``
(see ``check_contract_registry.py``). This module validates one candidate ID and
extracts the IDs documented in the contract document.

It is a segment validator rather than a regex: the pattern it replaces repeated
a group that itself carries a quantifier (``(\\.[a-z0-9-]+)*``), which a long
document full of near-miss IDs can drive into pathological backtracking.
Checking each segment against an explicit character set is linear and accepts
exactly the same language.

Standard library only; no I/O.
"""

from __future__ import annotations

from typing import Final

DOC_ID_VERSION: Final = "v1"
DOC_ID_HEAD_CHARS: Final = frozenset("abcdefghijklmnopqrstuvwxyz")
DOC_ID_CHARS: Final = DOC_ID_HEAD_CHARS | frozenset("0123456789-")
DOC_ID_RUN_CHARS: Final = DOC_ID_CHARS | {"."}


def _is_id_segment(segment: str) -> bool:
    """True for a later segment: ``[a-z0-9-]+``."""
    return bool(segment) and all(char in DOC_ID_CHARS for char in segment)


def _is_id_head(segment: str) -> bool:
    """True for the first segment: ``[a-z][a-z0-9-]*``."""
    return (
        bool(segment)
        and segment[0] in DOC_ID_HEAD_CHARS
        and all(char in DOC_ID_CHARS for char in segment[1:])
    )


def _is_contract_id(candidate: str) -> bool:
    """True when ``candidate`` is exactly ``[a-z][a-z0-9-]*(\\.[a-z0-9-]+)*\\.v1``."""
    segments = candidate.split(".")
    return (
        len(segments) >= 2
        and segments[-1] == DOC_ID_VERSION
        and _is_id_head(segments[0])
        and all(_is_id_segment(segment) for segment in segments[1:-1])
    )


def _id_runs(text: str) -> list[str]:
    """Split ``text`` into maximal runs of the characters a contract ID can hold."""
    runs: list[str] = []
    run: list[str] = []
    for char in text + "\0":
        if char in DOC_ID_RUN_CHARS:
            run.append(char)
        elif run:
            runs.append("".join(run))
            run = []
    return runs


def _longest_contract_id(run: str) -> str | None:
    """The longest validated ``.``-prefix of ``run``, or ``None``.

    A contract ID counts as documented when it appears as a whole prefix of a
    longer dotted token (``ibex.auth.v1`` in ``ibex.auth.v1.PrincipalContext``),
    which is what the previous unanchored pattern matched.
    """
    segments = run.split(".")
    for end in range(len(segments), 1, -1):
        candidate = ".".join(segments[:end])
        if _is_contract_id(candidate):
            return candidate
    return None


def documented_contract_ids(text: str) -> frozenset[str]:
    """Every contract ID in ``text``, one validated prefix per ID-character run."""
    ids: set[str] = set()
    for run in _id_runs(text):
        match = _longest_contract_id(run)
        if match is not None:
            ids.add(match)
    return frozenset(ids)
