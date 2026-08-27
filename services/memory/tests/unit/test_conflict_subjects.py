"""Unit tests for subject key helpers (spaCy mocked)."""

from __future__ import annotations

from types import SimpleNamespace

from app.conflict.subjects import (
    extract_subject_key,
    normalize_subject_key,
    subjects_match,
)


def test_normalize_subject_key() -> None:
    assert normalize_subject_key("  Pref Language  ") == "pref language"


def test_subjects_match_substring() -> None:
    assert subjects_match("pref", "pref language") is True
    assert subjects_match("", "x") is False
    assert subjects_match("a", "b") is False
    assert subjects_match("same", "same") is True


def test_extract_empty() -> None:
    assert extract_subject_key("   ") == ""


def test_extract_nsubj(monkeypatch: object) -> None:
    tokens = [
        SimpleNamespace(
            dep_="nsubj",
            lemma_="User",
            is_stop=False,
            is_alpha=True,
            children=[],
        ),
        SimpleNamespace(
            dep_="ROOT",
            lemma_="prefer",
            is_stop=False,
            is_alpha=True,
            children=[],
        ),
    ]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: tokens),
    )
    assert extract_subject_key("User prefers Python") == "user"


def test_extract_root_with_obj(monkeypatch: object) -> None:
    obj = SimpleNamespace(
        dep_="dobj",
        lemma_="Python",
        is_stop=False,
        is_alpha=True,
        children=[],
    )
    root = SimpleNamespace(
        dep_="ROOT",
        lemma_="prefer",
        is_stop=False,
        is_alpha=True,
        children=[obj],
    )
    tokens = [root, obj]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: tokens),
    )
    assert extract_subject_key("prefer Python") == "prefer python"


def test_extract_root_only(monkeypatch: object) -> None:
    root = SimpleNamespace(
        dep_="ROOT",
        lemma_="prefer",
        is_stop=False,
        is_alpha=True,
        children=[],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: [root]),
    )
    assert extract_subject_key("prefer") == "prefer"


def test_extract_token_fallback(monkeypatch: object) -> None:
    tokens = [
        SimpleNamespace(
            dep_="punct",
            lemma_="!",
            is_stop=False,
            is_alpha=False,
            children=[],
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
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.conflict.subjects._nlp",
        lambda _model: (lambda _text: tokens),
    )
    assert extract_subject_key("language preference!") == "language preference"
