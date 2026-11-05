"""Memory read repository — find_similar with vector + GIN fallback (milestone 3.D.1)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.rerank import RerankClient, RerankClientError
from app.config import Settings
from app.org_context import set_service_org
from app.read.conflicts import (
    collapse_conflict_pairs,
    conflict_groups_from_row,
    record_suppressed,
)
from app.read.full_text import (
    FullTextHit,
    FullTextSearchQuery,
    full_text_search,
    is_searchable_query,
)
from app.read.metrics import RERANK, RERANK_LATENCY, SEARCH_FALLBACK, SEARCH_HYBRID
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.pii_guard import PiiReadGuard
from app.read.ranking import (
    HydratedHit,
    RankedCandidate,
    RankOptions,
    fuse_candidates,
    merge_candidates,
    rank_hydrated_hits,
)
from app.tracing import start_span
from app.vectorstore.base import SearchHit, SearchMode, SearchRequest, VectorStore

logger = logging.getLogger(__name__)

_HYDRATE_SQL = """
SELECT m.id, m.org_id, m.agent_id, m.content, m.category, m.confidence, m.status,
       m.created_at, m.updated_at, m.valid_from, m.usefulness_score, m.retrieval_count,
       m.lifecycle_revision,
       COALESCE(
         (
           SELECT array_agg(ml.label ORDER BY ml.confidence DESC, ml.label ASC)
           FROM ibex_core.memory_labels ml
           WHERE ml.memory_id = m.id AND ml.org_id = m.org_id
         ),
         ARRAY[m.category]
       ) AS categories,
       COALESCE(
         (
           SELECT array_agg(e.id ORDER BY e.id)
           FROM ibex_core.memory_conflict_escalations e
           WHERE e.org_id = m.org_id
             AND e.status = 'pending'
             AND (e.new_memory_id = m.id OR e.candidate_memory_id = m.id)
         ),
         ARRAY[]::uuid[]
       ) AS conflict_groups
FROM ibex_core.memories m
WHERE m.org_id = :org_id
  AND m.id = ANY(CAST(:memory_ids AS uuid[]))
  AND m.confidence >= :min_confidence
  AND m.status = 'active'
  AND m.deleted_at IS NULL
  AND m.tombstoned = FALSE
  AND (m.expires_at IS NULL OR m.expires_at > CURRENT_TIMESTAMP)
  AND m.valid_from <= CURRENT_TIMESTAMP
  AND (m.valid_until IS NULL OR m.valid_until > CURRENT_TIMESTAMP)
"""


@dataclass(frozen=True, slots=True)
class _Refill:
    """Rows and guard already paid for by an earlier ranking pass.

    Bundled so the refill entry point stays under the argument limit and the
    two values travel together: a refill without the request's guard would
    re-scan rows the first pass already judged.
    """

    hydrated: Mapping[UUID, HydratedHit] | None = None
    guard: PiiReadGuard | None = None


@dataclass(frozen=True, slots=True)
class _RerankWindow:
    """The hydrated window one rerank stage scores, and the request's guard."""

    query: FindSimilarQuery
    window: list[RankedCandidate]
    hydrated: Mapping[UUID, HydratedHit]
    guard: PiiReadGuard


# One snapshot for the merged fallback page. The vector and full-text hydration
# statements run at different moments, so a row read early can carry an empty
# conflict set while its counterpart read later names the escalation. Re-reading
# the groups for the whole candidate set makes the suppression decision
# consistent with a single point in time.
_CONFLICT_GROUPS_SNAPSHOT_SQL = """
SELECT m.id AS memory_id,
       COALESCE(
         (
           SELECT array_agg(e.id ORDER BY e.id)
           FROM ibex_core.memory_conflict_escalations e
           WHERE e.org_id = m.org_id
             AND e.status = 'pending'
             AND (e.new_memory_id = m.id OR e.candidate_memory_id = m.id)
         ),
         ARRAY[]::uuid[]
       ) AS conflict_groups
FROM ibex_core.memories m
WHERE m.org_id = :org_id
  AND m.id = ANY(CAST(:memory_ids AS uuid[]))
"""


def _validate_find_similar_query(query: FindSimilarQuery) -> None:
    if query.limit < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    if query.min_confidence < 0.0 or query.min_confidence > 1.0:
        msg = "min_confidence must be in [0, 1]"
        raise ValueError(msg)


def _fts_fallback_enabled(
    settings: Settings,
    *,
    vector_count: int,
    limit: int,
    query_text: str,
) -> bool:
    return (
        settings.search_fallback_enabled
        and vector_count < limit
        and is_searchable_query(query_text)
    )


def _pii_allowed(hits: Iterable[HydratedHit], guard: PiiReadGuard) -> set[UUID]:
    """Ids the read-path Tier-1 guard would return for this window."""
    return {item.id for item in guard.allow([hit.result for hit in hits])}


def _hybrid_enabled(settings: Settings, *, query_text: str) -> bool:
    """The parallel channel ignores how full the vector page is.

    The old gate skipped full-text whenever the vector page was already full,
    which is exactly when an exact-token match was most likely to be missing.
    """
    return settings.search_hybrid_enabled and is_searchable_query(query_text)


def _rerank_host(client: RerankClient) -> str:
    """Endpoint host for the rerank span.

    Tests inject duck-typed rerankers that implement ``rerank`` without ``host``,
    so the lookup stays tolerant and anything that is not a string is dropped
    rather than handed to ``set_attribute``.
    """
    host = getattr(client, "host", "")
    return host if isinstance(host, str) else ""


class MemoryReadRepository:
    """Tenant-scoped semantic search; vector primary, GIN supplemental."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: VectorStore,
        settings: Settings,
        *,
        rerank_client: RerankClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._settings = settings
        self._rerank_client = rerank_client

    async def find_similar(self, query: FindSimilarQuery) -> list[MemorySearchResult]:
        _validate_find_similar_query(query)
        if _hybrid_enabled(self._settings, query_text=query.query_text):
            return await self._find_similar_hybrid(query)
        return await self._find_similar_fallback(query)

    async def _find_similar_hybrid(
        self, query: FindSimilarQuery
    ) -> list[MemorySearchResult]:
        """Both channels run; RRF picks the window composite scoring then orders.

        Two stages, deliberately: reciprocal rank fusion decides *which* candidates
        enter the page — it is the only stage that can weigh a cosine rank against
        a ``ts_rank_cd`` rank — and ADR-0068 composite scoring still decides the
        order inside that window, so recency, confidence, and usefulness keep their
        meaning. The admitted window is the page size, so hydration stays bounded
        by ``limit`` no matter how much either channel returns.
        """
        # Independent sessions, so the two channels overlap instead of adding up.
        vector_candidates, fts_hits = await asyncio.gather(
            self._vector_candidates(query),
            full_text_search(
                self._session_factory,
                FullTextSearchQuery(
                    org_id=query.org_id,
                    agent_id=query.agent_id,
                    query_text=query.query_text,
                    limit=query.limit,
                    min_confidence=query.min_confidence,
                ),
            ),
        )
        fts_candidates = _fts_candidates(fts_hits, cap=query.limit)
        fused = fuse_candidates(
            vector_candidates,
            fts_candidates,
            k=self._settings.search_rrf_k,
        )
        rank_opts = RankOptions(
            relevance_floor=self._settings.composite_relevance_floor,
            weights=self._settings.rank_weights(),
        )
        SEARCH_HYBRID.labels(
            vector=str(bool(vector_candidates)).lower(),
            full_text=str(bool(fts_candidates)).lower(),
        ).inc()
        # One guard per request: a refill must not re-scan (or re-count) rows the
        # first pass already judged.
        guard = PiiReadGuard()
        if self._rerank_available():
            return await self._rank_reranked(query, fused, rank_opts, guard)
        return await self._rank_fused_window(
            query, fused, rank_opts, _Refill(guard=guard)
        )

    def _rerank_available(self) -> bool:
        return self._settings.rerank_enabled and self._rerank_client is not None

    async def _rank_reranked(
        self,
        query: FindSimilarQuery,
        fused: list[RankedCandidate],
        rank_opts: RankOptions,
        guard: PiiReadGuard,
    ) -> list[MemorySearchResult]:
        """Cross-encode the fused window, then composite-score it.

        The reranker replaces the *relevance* component, not the order: a
        cross-encoder answers "how well does this document answer this query",
        which is exactly what cosine similarity and ``ts_rank_cd`` approximate on
        incomparable scales. Recency, confidence, usefulness, and the relevance
        floor keep their ADR-0068 meaning.

        The window is the fused union capped by ``rerank_max_candidates``, so a
        rerank never sees the corpus. Any failure degrades to the fused order --
        a slow reranker must not turn a search into an error.

        Conflict suppression runs after the rerank order is decided. Unlike the
        fused path there is nothing to refill from: the reranked window is
        already the widest the settings allow, so a suppressed pair costs a slot
        here rather than a wider hydration.
        """
        client = self._rerank_client
        if client is None:  # pragma: no cover - _rerank_available() guards the call
            return await self._rank_fused_window(
                query, fused, rank_opts, _Refill(guard=guard)
            )
        window = fused[: self._settings.rerank_max_candidates]
        hydrated = await self._hydrate_hits(
            org_id=query.org_id,
            candidates=window,
            min_confidence=query.min_confidence,
        )
        overrides, allowed = await self._rerank_scores(
            client, _RerankWindow(query, window, hydrated, guard)
        )
        if overrides is None:
            return await self._rank_fused_window(
                query, fused, rank_opts, _Refill(hydrated, guard)
            )
        # Blocked rows are excluded from ranking as well as from the rerank stage: a
        # blocked row holding its retrieval relevance could keep `ranked` non-empty
        # while the caller's final PII filter removes the only entry, turning a
        # recoverable page into an empty one.
        scored = rank_hydrated_hits(
            [item for item in window if item.memory_id in allowed],
            hydrated,
            replace(rank_opts, relevance_overrides=overrides),
        )
        kept = self._collapse(scored)
        record_suppressed(len(scored), len(kept))
        ranked = kept[: query.limit]
        if ranked:
            RERANK.labels(result="applied").inc()
            return ranked
        # The relevance floor emptied the page the reranker scored. Falling back is
        # the only way to return something, but mixing reranked and unreranked
        # relevance inside one page is not: the whole page comes from the fused order.
        RERANK.labels(result="emptied").inc()
        return await self._rank_fused_window(
            query, fused, rank_opts, _Refill(hydrated, guard)
        )

    async def _rerank_scores(
        self,
        client: RerankClient,
        spec: _RerankWindow,
    ) -> tuple[dict[UUID, float] | None, set[UUID]]:
        """Score the window, returning the overrides and the rows the guard allows.

        Content the read guard would block must not reach a third-party inference
        endpoint, so the same Tier-1 filter runs before the documents are built. The
        caller reuses the allowed set so blocked rows are also excluded from ranking.
        """
        allowed = _pii_allowed(spec.hydrated.values(), spec.guard)
        ids = [
            item.memory_id
            for item in spec.window
            if item.memory_id in spec.hydrated and item.memory_id in allowed
        ]
        if len(ids) < 2:
            # Nothing to reorder: a single candidate already holds the page.
            RERANK.labels(result="skipped").inc()
            return None, allowed
        documents = [spec.hydrated[memory_id].result.content for memory_id in ids]
        started = time.monotonic()
        host = _rerank_host(client)
        with start_span(
            "rerank",
            attributes={
                "server.address": host,
                "rerank.endpoint_host": host,
            },
        ) as span:
            try:
                scores = await asyncio.wait_for(
                    client.rerank(spec.query.query_text, documents),
                    timeout=self._settings.rerank_timeout_ms / 1000,
                )
                span.set_attribute("rerank.outcome", "applied")
            except (TimeoutError, RerankClientError) as exc:
                span.set_attribute("rerank.outcome", "degraded")
                RERANK.labels(result="degraded").inc()
                logger.warning(
                    "rerank degraded (%s) candidates=%d timeout_ms=%d",
                    type(exc).__name__,
                    len(ids),
                    self._settings.rerank_timeout_ms,
                )
                return None, allowed
            finally:
                # A timed-out call is the slow call the latency panel must show.
                RERANK_LATENCY.observe(time.monotonic() - started)
            return dict(zip(ids, scores, strict=True)), allowed

    async def _rank_fused_window(
        self,
        query: FindSimilarQuery,
        fused: list[RankedCandidate],
        rank_opts: RankOptions,
        refill: _Refill | None = None,
    ) -> list[MemorySearchResult]:
        """Hydrate the fused window, then refill only if the page came up short.

        Admission is the window, so hydration normally costs the page size. A
        candidate can still be dropped after admission -- below the confidence
        floor, below the relevance floor, or by the PII re-check -- and dropping
        it must not shorten the page while eligible fused candidates wait behind
        it. The union is bounded by ``2 * limit``, so the refill is one extra
        batch at most.

        ``hydrated`` lets a caller that has already paid for a wider window (the
        rerank path) hand its rows over, so a degrade does not re-query rows it
        already has.

        Conflict suppression runs before the page is cut, so a pair costs one
        slot rather than shortening the page: the dropped side is replaced by the
        next eligible candidate, exactly like a confidence or PII drop.

        The PII re-check runs *before* the collapse, not after: a blocked
        higher-ranked side would otherwise suppress its counterpart and then
        disappear itself, turning two recoverable hits into a short page.
        """
        carried = refill or _Refill()
        pii = carried.guard or PiiReadGuard()
        rows: dict[UUID, HydratedHit] = dict(carried.hydrated or {})
        admitted = fused[: query.limit]
        rows.update(
            await self._hydrate_missing(query, admitted, rows)
        )
        ranked = rank_hydrated_hits(admitted, rows, rank_opts)
        allowed = pii.allow(ranked)
        kept = self._collapse(allowed)
        remaining = fused[query.limit :]
        if len(kept) >= query.limit or not remaining:
            record_suppressed(len(allowed), len(kept))
            return kept[: query.limit]
        rows.update(await self._hydrate_missing(query, remaining, rows))
        # Refilling replaces the dropped slots; it does not widen the page. The
        # first pass is not counted: its drops are speculative until this one.
        refilled = rank_hydrated_hits(fused, rows, rank_opts)
        allowed = pii.allow(refilled)
        kept = self._collapse(allowed)
        record_suppressed(len(allowed), len(kept))
        return kept[: query.limit]

    def _collapse(self, results: Sequence[MemorySearchResult]) -> list[MemorySearchResult]:
        """Apply unresolved-conflict suppression unless the operator turned it off.

        `record_suppressed` stays at the call sites so the metric keeps reporting the drop it
        actually made: with the switch off it reports zero, which is the truth.
        """
        if not self._settings.conflict_suppression_enabled:
            return list(results)
        return collapse_conflict_pairs(results)

    async def _conflict_groups_snapshot(
        self,
        org_id: UUID,
        hydrated: Mapping[UUID, HydratedHit],
    ) -> dict[UUID, HydratedHit]:
        """Re-read pending conflict groups for the whole candidate set at once."""
        if not hydrated:
            return dict(hydrated)
        async with self._session_factory() as session, session.begin():
            await set_service_org(session, org_id)
            rows = (
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                        _CONFLICT_GROUPS_SNAPSHOT_SQL
                    ),
                    {
                        "org_id": str(org_id),
                        "memory_ids": [str(memory_id) for memory_id in hydrated],
                    },
                )
            ).mappings().all()
        groups = {
            UUID(str(row["memory_id"])): tuple(
                UUID(str(value)) for value in row["conflict_groups"]
            )
            for row in rows
        }
        return {
            memory_id: HydratedHit(
                result=replace(hit.result, conflict_groups=groups.get(memory_id, ())),
                valid_from=hit.valid_from,
                usefulness_score=hit.usefulness_score,
                retrieval_count=hit.retrieval_count,
            )
            for memory_id, hit in hydrated.items()
        }

    async def _hydrate_missing(
        self,
        query: FindSimilarQuery,
        candidates: list[RankedCandidate],
        known: Mapping[UUID, HydratedHit],
    ) -> dict[UUID, HydratedHit]:
        """Hydrate only the candidates the caller does not already hold."""
        missing = [item for item in candidates if item.memory_id not in known]
        if not missing:
            return {}
        return await self._hydrate_hits(
            org_id=query.org_id,
            candidates=missing,
            min_confidence=query.min_confidence,
        )

    async def _find_similar_fallback(
        self, query: FindSimilarQuery
    ) -> list[MemorySearchResult]:
        vector_candidates = await self._vector_candidates(query)
        vector_hydrated = await self._hydrate_hits(
            org_id=query.org_id,
            candidates=vector_candidates,
            min_confidence=query.min_confidence,
        )
        floor = self._settings.composite_relevance_floor
        rank_opts = RankOptions(
            relevance_floor=floor,
            weights=self._settings.rank_weights(),
        )
        pii = PiiReadGuard()
        vector_ranked = rank_hydrated_hits(
            vector_candidates,
            vector_hydrated,
            rank_opts,
        )
        allowed = pii.allow(vector_ranked)
        vector_kept = self._collapse(allowed)
        vector_page = vector_kept[: query.limit]
        if len(vector_page) >= query.limit:
            record_suppressed(len(allowed), len(vector_kept))
            return vector_page

        # The full-text supplement is sized from the page the caller will see, not
        # from the pre-suppression count: a suppressed hit leaves the same missing
        # slot as a confidence drop, and ignoring it would shorten the page while
        # an eligible full-text candidate waited.
        fts_candidates = await self._fts_candidates(
            query,
            vector_ranked=vector_page,
            vector_candidates=vector_candidates,
        )
        if not fts_candidates:
            record_suppressed(len(allowed), len(vector_kept))
            return vector_page

        merged = merge_candidates(vector_candidates, fts_candidates)
        fts_hydrated = await self._hydrate_hits(
            org_id=query.org_id,
            candidates=fts_candidates,
            min_confidence=query.min_confidence,
        )
        all_hydrated = {**fts_hydrated, **vector_hydrated}
        # Only worth a second read when some row already names a pending
        # escalation: otherwise no conflict could have been visible at either
        # snapshot, and the page is conflict-free by construction.
        if any(hit.result.conflict_groups for hit in all_hydrated.values()):
            all_hydrated = await self._conflict_groups_snapshot(query.org_id, all_hydrated)
        ranked = rank_hydrated_hits(merged, all_hydrated, rank_opts)
        allowed = pii.allow(ranked)
        kept = self._collapse(allowed)
        record_suppressed(len(allowed), len(kept))
        return kept[: query.limit]

    async def _vector_candidates(self, query: FindSimilarQuery) -> list[RankedCandidate]:
        with start_span(
            "vector_search",
            attributes={
                "db.system": "postgresql",
                "search.mode": "user_retrieval",
            },
        ):
            vector_hits = await self._vector_store.search(
                SearchRequest(
                    org_id=query.org_id,
                    agent_id=query.agent_id,
                    query_embedding=query.query_embedding,
                    limit=query.limit,
                    min_similarity=query.min_similarity,
                    mode=SearchMode.USER_RETRIEVAL,
                )
            )
            return _vector_candidates(vector_hits)

    async def _fts_candidates(
        self,
        query: FindSimilarQuery,
        *,
        vector_ranked: list[MemorySearchResult],
        vector_candidates: list[RankedCandidate],
    ) -> list[RankedCandidate]:
        if not _fts_fallback_enabled(
            self._settings,
            vector_count=len(vector_ranked),
            limit=query.limit,
            query_text=query.query_text,
        ):
            return []

        # Exclude every vector ANN hit (including below-floor gated IDs) so FTS cannot
        # reintroduce them via the 0.5 sentinel or waste slots on duplicates.
        exclude = frozenset(item.memory_id for item in vector_candidates)
        # Size the supplement by the page, not by the deficit. A supplement hit can
        # itself be the losing side of a conflict, and truncating to the deficit
        # would then return a short page while further eligible GIN matches were
        # already fetched.
        fts_hits = await full_text_search(
            self._session_factory,
            FullTextSearchQuery(
                org_id=query.org_id,
                agent_id=query.agent_id,
                query_text=query.query_text,
                limit=query.limit + len(exclude),
                min_confidence=query.min_confidence,
                exclude_ids=exclude,
            ),
        )
        fts_candidates = _fts_candidates(fts_hits, cap=query.limit)
        if not fts_candidates:
            return []

        SEARCH_FALLBACK.labels(triggered="true").inc()
        return fts_candidates

    async def _hydrate_hits(
        self,
        *,
        org_id: UUID,
        candidates: list[RankedCandidate],
        min_confidence: float,
    ) -> dict[UUID, HydratedHit]:
        if not candidates:
            return {}
        with start_span(
            "hydration",
            attributes={
                "db.system": "postgresql",
                "db.operation": "hydrate",
                "memory.candidate_count": len(candidates),
            },
        ):
            ids = [str(item.memory_id) for item in candidates]
            async with self._session_factory() as session, session.begin():
                await set_service_org(session, org_id)
                result = await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                        _HYDRATE_SQL
                    ),
                    {
                        "org_id": str(org_id),
                        "memory_ids": ids,
                        "min_confidence": min_confidence,
                    },
                )
                rows = result.mappings().all()

            score_by_id = {item.memory_id: item for item in candidates}
            out: dict[UUID, HydratedHit] = {}
            for row in rows:
                memory_id = UUID(str(row["id"]))
                ranked = score_by_id.get(memory_id)
                if ranked is None:
                    continue
                out[memory_id] = HydratedHit(
                    result=MemorySearchResult(
                        id=memory_id,
                        org_id=UUID(str(row["org_id"])),
                        agent_id=UUID(str(row["agent_id"])),
                        content=str(row["content"]),
                        category=str(row["category"]),
                        confidence=float(row["confidence"]),
                        status=str(row["status"]),
                        similarity=ranked.score,
                        source=ranked.source,
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        categories=_categories_from_row(row),
                        lifecycle_revision=int(row.get("lifecycle_revision", 1)),
                        conflict_groups=conflict_groups_from_row(row),
                    ),
                    valid_from=row["valid_from"],
                    usefulness_score=float(row["usefulness_score"]),
                    retrieval_count=int(row["retrieval_count"]),
                )
            return out


def _categories_from_row(row: Mapping[str, object]) -> tuple[str, ...]:
    raw = row.get("categories")
    if raw is None:
        return (str(row["category"]),)
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(label) for label in raw)  # type: ignore[union-attr]


def _vector_candidates(hits: list[SearchHit]) -> list[RankedCandidate]:
    return [
        RankedCandidate(memory_id=hit.memory_id, score=hit.similarity, source="vector")
        for hit in hits
    ]


def _fts_candidates(hits: list[FullTextHit], *, cap: int) -> list[RankedCandidate]:
    # ts_rank_cd is unbounded; HTTP/context treat ``similarity`` as a [0, 1] unit.
    return [
        RankedCandidate(
            memory_id=hit.memory_id,
            score=_clamp_unit_interval(hit.rank),
            source="full_text",
        )
        for hit in hits[:cap]
    ]


def _clamp_unit_interval(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
