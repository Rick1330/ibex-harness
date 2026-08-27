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
    """Return a stable subject+predicate/attribute key for conflict matching.

    Combines nominal subject with ROOT lemma and object/attribute when present so
    distinct properties of one entity (e.g. preference vs location) do not share
    an automatic-supersession key.
    """
    text = content.strip()
    if not text:
        return ""
    doc = _nlp(model_name)(text)
    root = _find_root(doc)
    nsubj_key = _key_from_nominal_subject(doc, root)
    if nsubj_key:
        return nsubj_key
    root_key = _key_from_root(root)
    if root_key:
        return root_key
    return _key_from_content_tokens(doc)


def _find_root(doc: Any) -> Any | None:
    return next((t for t in doc if t.dep_ == "ROOT"), None)


def _object_lemmas(root: Any) -> list[str]:
    return [t.lemma_ for t in root.children if t.dep_ in _OBJ_DEPS]


def _key_from_nominal_subject(doc: Any, root: Any | None) -> str:
    for token in doc:
        if token.dep_ in _NSUBJ_DEPS and not token.is_stop:
            return normalize_subject_key(_subject_predicate_key(token.lemma_, root))
    return ""


def _key_from_root(root: Any | None) -> str:
    if root is None:
        return ""
    objs = _object_lemmas(root)
    if objs:
        return normalize_subject_key(f"{root.lemma_} {objs[0]}")
    return normalize_subject_key(root.lemma_)


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
