"""A deterministic stand-in for the cross-encoder, so CI can gate the *plumbing*.

The real reranker is a network service, and the benchmark needs to tell two things apart:

* does the rerank stage run at all, and does its ordering reach the page?
* does a specific cross-encoder model rank better than fusion?

The first question is answerable in CI with a scorer that is fixed, fast, and states its own
name. The second is not, and this stub must never be presented as an answer to it: every
artifact it contributes to carries ``stub/lexical-overlap@1`` in place of a model name, so no
reader can mistake the number for a measurement of ``bge-reranker-v2-m3``.

The score is the share of the query's terms that appear in the document. That is enough to
reorder a fused window by text, which is all the plumbing check needs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

LABEL = "stub/lexical-overlap@1"

_TERM = re.compile(r"[a-z0-9]+")
# Single characters carry no signal and would make a document match any query that shares one.
_MIN_TERM_LENGTH = 2


def terms(text: str) -> set[str]:
    return {
        term for term in _TERM.findall(text.lower()) if len(term) >= _MIN_TERM_LENGTH
    }


def overlap_score(query: str, document: str) -> float:
    """Share of the query's terms the document contains, in ``[0, 1]``."""
    wanted = terms(query)
    if not wanted:
        return 0.0
    return len(wanted & terms(document)) / len(wanted)


class LexicalOverlapReranker:
    """The rerank client interface the read path calls, backed by ``overlap_score``.

    It also counts what it was asked, so the driver can prove the stage was reached instead of
    trusting that a mode which *declares* reranking actually reranked anything.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.documents_scored = 0

    # The ``async`` is the protocol contract, not an accident: the real client's
    # ``RerankClient.rerank`` is ``async def`` and the read path awaits it inside
    # ``asyncio.wait_for``, so a sync stub would break ``hybrid_rerank``.
    async def rerank(  # NOSONAR(S7503)
        self, query: str, documents: Sequence[str]
    ) -> list[float]:
        """One score per document, in the order given.

        The service client returns a bare list, so a short list would silently shift every
        later score onto the wrong document; the length is asserted here rather than trusted.
        """
        self.calls += 1
        self.documents_scored += len(documents)
        return [overlap_score(query, document) for document in documents]

    async def aclose(self) -> None:
        """Match the client's interface: the read path closes what it was given."""
