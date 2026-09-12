"""Go path/filepath.Match grammar checks for model_pattern (ADR-0075).

Kept as small flat helpers so management API rejects patterns the proxy would
fail closed on at load time.
"""

from __future__ import annotations


def go_filepath_match_error(pattern: str) -> str | None:
    """Return a reason if Go ``filepath.Match`` would return ErrBadPattern."""
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        i += 1
        if ch == "\\":
            i, err = _skip_escape(i, n)
            if err is not None:
                return err
            continue
        if ch != "[":
            continue
        i, err = _skip_character_class(pattern, i, n)
        if err is not None:
            return err
    return None


def _skip_escape(i: int, n: int) -> tuple[int, str | None]:
    if i >= n:
        return i, "trailing backslash"
    return i + 1, None


def _get_esc(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    if i >= n or pattern[i] in "-]":
        return i, "invalid character class item"
    if pattern[i] == "\\":
        return _get_esc_backslash(i + 1, n)
    i += 1
    if i >= n:
        return i, "invalid character class item"
    return i, None


def _get_esc_backslash(i: int, n: int) -> tuple[int, str | None]:
    i, err = _skip_escape(i, n)
    if err is not None:
        return i, err
    if i >= n:
        return i, "invalid character class item"
    return i, None


def _scan_class_item(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    i, err = _get_esc(pattern, i, n)
    if err is not None:
        return i, err
    if i >= n or pattern[i] != "-":
        return i, None
    return _get_esc(pattern, i + 1, n)


def _scan_class_contents(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    nrange = 0
    while i < n:
        if pattern[i] == "]" and nrange > 0:
            return i + 1, None
        i, err = _scan_class_item(pattern, i, n)
        if err is not None:
            return i, err
        nrange += 1
    return i, "unclosed character class"


def _skip_character_class(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    if i < n and pattern[i] == "^":
        i += 1
    if i >= n:
        return i, "unclosed character class"
    if pattern[i] == "]":
        return i, "empty character class"
    return _scan_class_contents(pattern, i, n)
