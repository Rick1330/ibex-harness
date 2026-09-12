"""Go path/filepath.Match grammar checks for model_pattern (ADR-0075).

Kept separate from Pydantic schemas so CodeScene overall-complexity stays
bounded on the request/response models module.
"""

from __future__ import annotations

_MAX_PATTERN_LEN = 256


def normalize_model_pattern(pattern: str) -> str:
    """Strip, bound length, and reject patterns Go filepath.Match would reject."""
    normalized = pattern.strip()
    if not normalized:
        raise ValueError("model_pattern is required")
    if len(normalized) > _MAX_PATTERN_LEN:
        raise ValueError(f"model_pattern exceeds {_MAX_PATTERN_LEN} characters")
    reason = _go_filepath_match_error(normalized)
    if reason is not None:
        raise ValueError(f"model_pattern has invalid glob syntax ({reason})")
    return normalized


def _skip_escape(i: int, n: int) -> tuple[int, str | None]:
    """Advance past a backslash escape; i points at the char after '\\'."""
    if i >= n:
        return i, "trailing backslash"
    return i + 1, None


def _get_esc(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Mirror Go path.match getEsc for character-class items."""
    if i >= n or pattern[i] in "-]":
        return i, "invalid character class item"
    if pattern[i] == "\\":
        return _get_esc_backslash(pattern, i + 1, n)
    i += 1
    if i >= n:
        return i, "invalid character class item"
    return i, None


def _get_esc_backslash(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    i, err = _skip_escape(i, n)
    if err is not None:
        return i, err
    if i >= n:
        return i, "invalid character class item"
    return i, None


def _scan_class_item(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Consume one class item, optionally as a lo-hi range."""
    i, err = _get_esc(pattern, i, n)
    if err is not None:
        return i, err
    if i >= n or pattern[i] != "-":
        return i, None
    return _get_esc(pattern, i + 1, n)


def _scan_class_contents(pattern: str, i: int, n: int) -> tuple[int, str | None]:
    """Scan Go-style ranges inside a character class; i is first content index."""
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
    """Advance past a [...] class; i points at the char after '['."""
    if i < n and pattern[i] == "^":
        i += 1
    if i >= n:
        return i, "unclosed character class"
    if pattern[i] == "]":
        return i, "empty character class"
    return _scan_class_contents(pattern, i, n)


def _go_filepath_match_error(pattern: str) -> str | None:
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
