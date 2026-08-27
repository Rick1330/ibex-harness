"""Unit tests for subject key helpers (spaCy mocked)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.conflict.subjects import (
    extract_subject_key,
    normalize_subject_key,
    subjects_match,
)


def _patch_nlp(monkeypatch: pytest.MonkeyPatch, tokens: list[object]) -> None:
    monkeypatch.setattr(
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: tokens),
    )


def _nsubj_tokens() -> list[object]:
    return [
        SimpleNamespace(
            dep_="nsubj", lemma_="User", is_stop=False, is_alpha=True, children=[]
        ),
        SimpleNamespace(
            dep_="ROOT", lemma_="prefer", is_stop=False, is_alpha=True, children=[]
        ),
    ]


def _nsubj_obj_tokens() -> list[object]:
    obj = SimpleNamespace(
        dep_="dobj", lemma_="Python", is_stop=False, is_alpha=True, children=[]
    )
    root = SimpleNamespace(
        dep_="ROOT", lemma_="prefer", is_stop=False, is_alpha=True, children=[obj]
    )
    nsubj = SimpleNamespace(
        dep_="nsubj", lemma_="User", is_stop=False, is_alpha=True, children=[]
    )
    return [nsubj, root, obj]


def _root_obj_tokens() -> list[object]:
    obj = SimpleNamespace(
        dep_="dobj", lemma_="Python", is_stop=False, is_alpha=True, children=[]
    )
    root = SimpleNamespace(
        dep_="ROOT", lemma_="prefer", is_stop=False, is_alpha=True, children=[obj]
    )
    return [root, obj]


def _root_only_tokens() -> list[object]:
    return [
        SimpleNamespace(
            dep_="ROOT", lemma_="prefer", is_stop=False, is_alpha=True, children=[]
        )
    ]


def _fallback_tokens() -> list[object]:
    return [
        SimpleNamespace(
            dep_="punct", lemma_="!", is_stop=False, is_alpha=False, children=[]
        ),
        SimpleNamespace(
            dep_="compound",
            lemma_="language",
            is_stop=False,
            is_alpha=True,
            children=[],
        ),
        SimpleNamespace(
            dep_="compound",
            lemma_="preference",
            is_stop=False,
            is_alpha=True,
            children=[],
        ),
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
