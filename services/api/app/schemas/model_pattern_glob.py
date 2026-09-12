"""Go path/filepath.Match grammar checks for model_pattern (ADR-0075).

Kept as small flat helpers so management API rejects patterns the proxy would
fail closed on at load time.
"""

from __future__ import annotations

from app.schemas.model_pattern_charclass import skip_character_class


def go_filepath_match_error(pattern: str) -> str | None:
    """Return a reason if Go ``filepath.Match`` would return ErrBadPattern."""
    i = 0
    n = len(pattern)
    while i < n:
        i, err = _advance_pattern(pattern, i, n)
        if err is not None:
            return err
    return None


def _advance_pattern(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    ch = pattern[i]
    i += 1
    if ch == "\\":
        return _skip_escape(i, n)
    if ch == "[":
        return skip_character_class(pattern, i, n)
    return i, None


def _skip_escape(i: int, n: int) -> tuple[int, str | None]:
    if i >= n:
        return i, "trailing backslash"
    return i + 1, None
