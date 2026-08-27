"""spaCy subject/attribute key extraction for conflict matching (ADR-0056)."""

from __future__ import annotations

import re
from functools import lru_cache

_WS = re.compile(r"\s+")


def normalize_subject_key(raw: str) -> str:
    return _WS.sub(" ", raw.strip().lower())


@lru_cache(maxsize=2)
def _nlp(model_name: str) -> object:
    import spacy

    return spacy.load(model_name)


def extract_subject_key(content: str, *, model_name: str = "en_core_web_md") -> str:
    """Return a stable subject/attribute key for conflict matching.

    Prefers nominal subject (nsubj/nsubjpass); falls back to ROOT lemma + object,
    then to the first two content tokens.
    """
    text = content.strip()
    if not text:
        return ""
    doc = _nlp(model_name)(text)
    for token in doc:
        if token.dep_ in {"nsubj", "nsubjpass"} and not token.is_stop:
            return normalize_subject_key(token.lemma_)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is not None:
        objs = [t.lemma_ for t in root.children if t.dep_ in {"dobj", "attr", "pobj"}]
        if objs:
            return normalize_subject_key(f"{root.lemma_} {objs[0]}")
        return normalize_subject_key(root.lemma_)
    tokens = [t.lemma_ for t in doc if t.is_alpha and not t.is_stop][:2]
    return normalize_subject_key(" ".join(tokens))


def subjects_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left
