"""Character-class scan for Go filepath.Match (ADR-0075)."""

from __future__ import annotations

_INVALID_CLASS_ITEM = "invalid character class item"


def skip_character_class(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Advance past a ``[...]`` class starting at ``i`` (after ``[``)."""
    i = _skip_negation(pattern, i, n)
    err = _require_open_class(i, n)
    if err is not None:
        return i, err
    if pattern[i] == "]":
        return i, "empty character class"
    return _scan_class_contents(pattern, i, n)


def _skip_negation(pattern: str, i: int, n: int) -> int:
    if i < n and pattern[i] == "^":
        return i + 1
    return i


def _require_open_class(i: int, n: int) -> str | None:
    if i >= n:
        return "unclosed character class"
    return None


def _scan_class_contents(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    nrange = 0
    while i < n:
        if _class_closed(pattern, i, nrange):
            return i + 1, None
        i, err = _scan_class_item(pattern, i, n)
        if err is not None:
            return i, err
        nrange += 1
    return i, "unclosed character class"


def _class_closed(pattern: str, i: int, nrange: int) -> bool:
    return pattern[i] == "]" and nrange > 0


def _scan_class_item(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    i, err = _get_esc(pattern, i, n)
    if err is not None:
        return i, err
    return _maybe_range(pattern, i, n)


def _maybe_range(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    if i >= n or pattern[i] != "-":
        return i, None
    return _get_esc(pattern, i + 1, n)


def _get_esc(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    if _invalid_class_start(pattern, i, n):
        return i, _INVALID_CLASS_ITEM
    if pattern[i] == "\\":
        return _get_esc_backslash(i + 1, n)
    return _consume_plain(i, n)


def _invalid_class_start(pattern: str, i: int, n: int) -> bool:
    return i >= n or pattern[i] in "-]"


def _consume_plain(i: int, n: int) -> tuple[int, str | None]:
    i += 1
    if i >= n:
        return i, _INVALID_CLASS_ITEM
    return i, None


def _get_esc_backslash(i: int, n: int) -> tuple[int, str | None]:
    if i >= n:
        return i, "trailing backslash"
    i += 1
    if i >= n:
        return i, _INVALID_CLASS_ITEM
    return i, None
