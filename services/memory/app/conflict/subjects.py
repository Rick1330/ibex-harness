"""spaCy subject/attribute key extraction for conflict matching (ADR-0056)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

_WS = re.compile(r"\s+")
_OBJ_DEPS = frozenset({"dobj", "attr", "pobj"})
_NSUBJ_DEPS = frozenset({"nsubj", "nsubjpass"})


def normalize_subject_key(raw: str) -> str:
    return _WS.sub(" ", raw.strip().lower())


@lru_cache(maxsize=2)
def _nlp(model_name: str) -> object:
    import spacy

    return spacy.load(model_name)


def extract_subject_key(content: str, *, model_name: str = "en_core_web_md") -> str:
    """Return a stable subject+predicate/attribute key for conflict matching."""
    text = content.strip()
    if not text:
        return ""
    return _subject_key_from_doc(_nlp(model_name)(text))


def _subject_key_from_doc(doc: Any) -> str:
    root = _find_root(doc)
    return _first_nonempty(
        _key_from_nominal_subject(doc, root),
        _key_from_root(root),
        _key_from_content_tokens(doc),
    )


def _first_nonempty(*parts: str) -> str:
    for part in parts:
        if part:
            return part
    return ""


def _find_root(doc: Any) -> Any | None:
    return next((t for t in doc if t.dep_ == "ROOT"), None)


def _object_lemmas(root: Any) -> list[str]:
    return [t.lemma_ for t in root.children if t.dep_ in _OBJ_DEPS]


def _key_from_nominal_subject(doc: Any, root: Any | None) -> str:
    token = next(
        (t for t in doc if t.dep_ in _NSUBJ_DEPS and not t.is_stop),
        None,
    )
    if token is None:
        return ""
    return normalize_subject_key(_subject_predicate_key(token.lemma_, root))


def _key_from_root(root: Any | None) -> str:
    if root is None:
        return ""
    objs = _object_lemmas(root)
    if not objs:
        return normalize_subject_key(root.lemma_)
    return normalize_subject_key(f"{root.lemma_} {objs[0]}")


def _key_from_content_tokens(doc: Any) -> str:
    tokens = [t.lemma_ for t in doc if t.is_alpha and not t.is_stop][:2]
    return normalize_subject_key(" ".join(tokens))


def _subject_predicate_key(subject_lemma: str, root: object | None) -> str:
    if root is None:
        return subject_lemma
    parts = [subject_lemma, getattr(root, "lemma_", "")]
    objs = _object_lemmas(root)
    if objs:
        parts.append(objs[0])
    return " ".join(p for p in parts if p)


def subjects_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left
