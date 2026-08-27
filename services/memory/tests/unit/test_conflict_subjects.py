"""Unit tests for subject key helpers (spaCy mocked)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.conflict.subjects import (
    extract_subject_key,
    normalize_subject_key,
    subjects_match,
)


def _tok(
    *,
    dep: str,
    lemma: str,
    is_stop: bool = False,
    is_alpha: bool = True,
    children: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        dep_=dep,
        lemma_=lemma,
        is_stop=is_stop,
        is_alpha=is_alpha,
        children=children or [],
    )


def _patch_nlp(monkeypatch: pytest.MonkeyPatch, tokens: list[object]) -> None:
    monkeypatch.setattr(
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: tokens),
    )


def _nsubj_tokens() -> list[object]:
    return [_tok(dep="nsubj", lemma="User"), _tok(dep="ROOT", lemma="prefer")]


def _nsubj_obj_tokens() -> list[object]:
    obj = _tok(dep="dobj", lemma="Python")
    root = _tok(dep="ROOT", lemma="prefer", children=[obj])
    return [_tok(dep="nsubj", lemma="User"), root, obj]


def _root_obj_tokens() -> list[object]:
    obj = _tok(dep="dobj", lemma="Python")
    root = _tok(dep="ROOT", lemma="prefer", children=[obj])
    return [root, obj]


def _root_only_tokens() -> list[object]:
    return [_tok(dep="ROOT", lemma="prefer")]


def _fallback_tokens() -> list[object]:
    return [
        _tok(dep="punct", lemma="!", is_alpha=False),
        _tok(dep="compound", lemma="language"),
        _tok(dep="compound", lemma="preference"),
    ]


def test_normalize_subject_key() -> None:
    assert normalize_subject_key("  Pref Language  ") == "pref language"


def test_subjects_match_substring() -> None:
    assert subjects_match("pref", "pref language") is True
    assert subjects_match("", "x") is False
    assert subjects_match("a", "b") is False
    assert subjects_match("same", "same") is True


def test_extract_empty() -> None:
    assert extract_subject_key("   ") == ""


@pytest.mark.parametrize(
    ("factory", "text", "expected"),
    [
        (_nsubj_tokens, "User prefers Python", "user prefer"),
        (_nsubj_obj_tokens, "User prefers Python", "user prefer python"),
        (_root_obj_tokens, "prefer Python", "prefer python"),
        (_root_only_tokens, "prefer", "prefer"),
        (_fallback_tokens, "language preference!", "language preference"),
    ],
)
def test_extract_subject_key_paths(
    monkeypatch: pytest.MonkeyPatch,
    factory: object,
    text: str,
    expected: str,
) -> None:
    _patch_nlp(monkeypatch, factory())  # type: ignore[operator]
    assert extract_subject_key(text) == expected


def test_distinct_entity_properties_do_not_match() -> None:
    """Same entity, unrelated attributes must not share a supersession key."""
    assert subjects_match("user prefer python", "user live seattle") is False
