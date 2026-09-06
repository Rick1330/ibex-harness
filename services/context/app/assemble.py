"""AssembleContext orchestration (milestone 3.5.C.6 / ADR-0071).

Wires budget → retrieve → score → pack → format with L0–L2 degradation
classification from ``BranchOutcome``. Does not own the gRPC transport — see
``app.server``. L3 (proxy fail-open on DEADLINE_EXCEEDED) is outside this module.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.budget import BudgetCalculator, Message, TokenBudget
from app.capability_catalog import CapabilityCatalog, default_catalog
from app.config import ContextSettings
from app.formatter import ContextFormatter, FormatRequest, FormattedContext
from app.packer import BUCKET_SIZE, ContextPacker, PackedMemories, ScoredMemory
from app.pipeline import _dedupe_hits
from app.retrieval import ParallelRetriever, RetrievalRequest, RetrievalResult
from app.scoring import score_hits

logger = logging.getLogger(__name__)

DegradationLevel = Literal["L0", "L1", "L2"]


@dataclass(frozen=True, slots=True)
class AssemblyOptions:
    """In-process options mirroring proto AssemblyOptions (subset used by C.6)."""

    skip_cold_memories: bool = False
    skip_hot_memories: bool = False
    max_memories: int = 0


@dataclass(frozen=True, slots=True)
class AssemblyMetricsSnapshot:
    """Stage timings mapped to proto AssemblyMetrics field names."""

    budget_calculation_ms: int
    directive_load_ms: int
    hot_memory_retrieval_ms: int
    cold_memory_retrieval_ms: int
    ranking_ms: int
    packing_ms: int
    formatting_ms: int
    total_ms: int
    candidates_evaluated: int


@dataclass(frozen=True, slots=True)
class MemoryUsedRecord:
    """Packed memory metadata for AssembleContextResponse.memories_used."""

    memory_id: str
    composite_score: float
    relevance_score: float
    recency_score: float
    usefulness_score: float
    rank: int
    category: str


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    """Domain result of one AssembleContext orchestration."""

    formatted: FormattedContext
    packed: PackedMemories
    budget: TokenBudget
    retrieval: RetrievalResult
    metrics: AssemblyMetricsSnapshot
    degradation_level: DegradationLevel
    memories_used: tuple[MemoryUsedRecord, ...]
    tokens_used: int


@dataclass(frozen=True, slots=True)
class AssembleRequest:
    """Domain inputs for ``assemble_context`` (avoids proto dependency)."""

    org_id: UUID
    agent_id: UUID
    query: str
    model: str
    recent_messages: Sequence[Message]
    options: AssemblyOptions = AssemblyOptions()
    tool_schemas: Sequence[str] = ()


class ContextAssembler:
    """Budget → retrieve → pack → format with degradation classification."""

    def __init__(
        self,
        *,
        settings: ContextSettings,
        retriever: ParallelRetriever,
        formatter: ContextFormatter | None = None,
        budget: BudgetCalculator | None = None,
        catalog: CapabilityCatalog | None = None,
    ) -> None:
        self._settings = settings
        self._retriever = retriever
        self._catalog = catalog or default_catalog()
        self._budget = budget or BudgetCalculator(self._catalog)
        self._formatter = formatter or ContextFormatter(
            nonce_bytes=settings.formatter_nonce_bytes,
        )

    async def assemble(self, request: AssembleRequest) -> AssemblyResult:
        """Run the full assembly pipeline and classify L0–L2."""
        started = time.perf_counter()
        messages = list(request.recent_messages)

        retrieval_req = RetrievalRequest(
            org_id=request.org_id,
            agent_id=request.agent_id,
            query=request.query,
            model=request.model,
            recent_messages=messages,
        )
        retrieval = await self._retriever.retrieve(retrieval_req)
        retrieval = _apply_skip_options(retrieval, request.options)

        level, intentional_skip = _classify_degradation(retrieval, request.options)
        if level != "L0":
            logger.info(
                "context_assembly_degraded level=%s intentional_skip=%s "
                "org_id=%s agent_id=%s hot=%s cold=%s directive=%s",
                level,
                intentional_skip,
                request.org_id,
                request.agent_id,
                retrieval.hot_outcome.status,
                retrieval.cold_outcome.status,
                retrieval.directive_outcome.status,
            )

        directive_text = (
            retrieval.directive.content if retrieval.directive is not None else ""
        )
        t_budget = time.perf_counter()
        budget = self._budget.calculate(request.model, messages, directive_text)
        budget_ms = _elapsed_ms(t_budget)

        policy = self._catalog.family_policy(
            self._catalog.for_model(request.model).tokenizer_family,
        )
        packer = ContextPacker(
            policy,
            bucket_size=BUCKET_SIZE,
            dp_cell_ceiling=self._settings.packer_dp_cell_ceiling,
            max_consecutive_skips=self._settings.packer_max_consecutive_skips,
        )

        t_rank = time.perf_counter()
        if level == "L2":
            scored: list[ScoredMemory] = []
        else:
            merged = _dedupe_hits(retrieval.hot_memories + retrieval.cold_memories)
            scored = score_hits(merged)
            if request.options.max_memories > 0:
                scored = scored[: request.options.max_memories]
        ranking_ms = _elapsed_ms(t_rank)

        t_pack = time.perf_counter()
        packed = packer.pack(scored, budget.usable_budget)
        packing_ms = _elapsed_ms(t_pack)

        t_fmt = time.perf_counter()
        formatted = self._formatter.format(
            FormatRequest(
                directive=retrieval.directive,
                recent_messages=messages,
                packed=packed,
                tool_schemas=request.tool_schemas,
            )
        )
        formatting_ms = _elapsed_ms(t_fmt)

        total_ms = _elapsed_ms(started)
        metrics = AssemblyMetricsSnapshot(
            budget_calculation_ms=budget_ms,
            directive_load_ms=_outcome_ms(retrieval.directive_outcome.latency_ms),
            hot_memory_retrieval_ms=_outcome_ms(retrieval.hot_outcome.latency_ms),
            cold_memory_retrieval_ms=_outcome_ms(retrieval.cold_outcome.latency_ms),
            ranking_ms=ranking_ms,
            packing_ms=packing_ms,
            formatting_ms=formatting_ms,
            total_ms=total_ms,
            candidates_evaluated=packed.candidates_evaluated,
        )
        logger.debug(
            "context_assembly_timings level=%s budget_ms=%s ranking_ms=%s "
            "packing_ms=%s formatting_ms=%s total_ms=%s candidates=%s",
            level,
            metrics.budget_calculation_ms,
            metrics.ranking_ms,
            metrics.packing_ms,
            metrics.formatting_ms,
            metrics.total_ms,
            metrics.candidates_evaluated,
        )

        memories_used = tuple(_memory_used(item) for item in packed.memories)
        tokens_used = (
            budget.directive_tokens + budget.messages_tokens + packed.total_tokens
        )
        return AssemblyResult(
            formatted=formatted,
            packed=packed,
            budget=budget,
            retrieval=retrieval,
            metrics=metrics,
            degradation_level=level,
            memories_used=memories_used,
            tokens_used=tokens_used,
        )


def _apply_skip_options(
    retrieval: RetrievalResult,
    options: AssemblyOptions,
) -> RetrievalResult:
    hot = [] if options.skip_hot_memories else retrieval.hot_memories
    cold = [] if options.skip_cold_memories else retrieval.cold_memories
    if hot is retrieval.hot_memories and cold is retrieval.cold_memories:
        return retrieval
    return RetrievalResult(
        directive=retrieval.directive,
        directive_outcome=retrieval.directive_outcome,
        hot_memories=hot,
        hot_outcome=retrieval.hot_outcome,
        cold_memories=cold,
        cold_outcome=retrieval.cold_outcome,
        recent_messages=retrieval.recent_messages,
        history_tokens=retrieval.history_tokens,
        sources_available=retrieval.sources_available,
    )


def _classify_degradation(
    retrieval: RetrievalResult,
    options: AssemblyOptions,
) -> tuple[DegradationLevel, bool]:
    """Return (level, intentional_skip).

    Intentional skips via AssemblyOptions are L1/L2-shaped but logged as
    intentional rather than dependency failure.
    """
    hot_ok = (
        options.skip_hot_memories or retrieval.hot_outcome.status == "success"
    )
    cold_ok = (
        options.skip_cold_memories or retrieval.cold_outcome.status == "success"
    )
    intentional = options.skip_hot_memories or options.skip_cold_memories

    if hot_ok and cold_ok:
        # Both success, or skipped sides treated as satisfied.
        if (
            options.skip_cold_memories
            and not options.skip_hot_memories
            and retrieval.hot_outcome.status == "success"
        ):
            return "L1", True
        if options.skip_hot_memories and options.skip_cold_memories:
            return "L2", True
        if options.skip_hot_memories and retrieval.cold_outcome.status == "success":
            return "L1", True
        return "L0", False

    if not hot_ok and not cold_ok:
        return "L2", intentional

    # One memory source usable → L1 (cold-degraded or hot-degraded).
    return "L1", intentional


def _memory_used(item: ScoredMemory) -> MemoryUsedRecord:
    # Interim packer score only; wire does not yet expose recency/usefulness.
    return MemoryUsedRecord(
        memory_id=item.memory_id,
        composite_score=float(item.composite_score),
        relevance_score=float(item.hit.similarity),
        recency_score=0.0,
        usefulness_score=0.0,
        rank=int(item.hit.rank),
        category=item.category,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000.0))


def _outcome_ms(latency_ms: float) -> int:
    return max(0, round(latency_ms))
