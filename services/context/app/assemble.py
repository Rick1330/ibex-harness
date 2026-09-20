"""AssembleContext orchestration (milestone 3.5.C.6 / ADR-0071).

Wires retrieve → budget → score → pack → format with L0–L2 degradation
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

from app.budget import (
    MIN_VIABLE_MEMORY_BUDGET,
    BudgetCalculator,
    Message,
    TokenBudget,
    estimate_wrapped_memory_tokens,
)
from app.capability_catalog import CapabilityCatalog, TokenizerFamilyPolicy, default_catalog
from app.config import ContextSettings
from app.estimate import estimate_tokens
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
    exclusion: str = "included"
    similarity: float = 0.0
    confidence: float = 0.0
    token_estimate: int = 0


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
    request_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    score_schema: str = "interim_v1"


@dataclass(frozen=True, slots=True)
class AssembleRequest:
    """Domain inputs for ``assemble_context`` (avoids proto dependency)."""

    org_id: UUID
    agent_id: UUID
    query: str
    model: str
    recent_messages: Sequence[Message]
    session_id: str = ""
    directive_version_id: str = ""
    request_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    # When > 0, caps TokenBudget.usable_budget (proto available_tokens).
    available_tokens: int = 0
    options: AssemblyOptions = AssemblyOptions()
    tool_schemas: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class _AssemblerDeps:
    """Optional injectable collaborators for ``ContextAssembler``."""

    formatter: ContextFormatter | None = None
    budget: BudgetCalculator | None = None
    catalog: CapabilityCatalog | None = None


@dataclass(frozen=True, slots=True)
class _PackFormatInput:
    """Inputs for post-retrieval budget → pack → format."""

    request: AssembleRequest
    messages: list[Message]
    retrieval: RetrievalResult
    level: DegradationLevel
    started: float


@dataclass(frozen=True, slots=True)
class _AssemblyBuildInput:
    """Bundled fields for ``_build_assembly_result`` (CodeScene arity)."""

    request: AssembleRequest
    retrieval: RetrievalResult
    level: DegradationLevel
    budget: TokenBudget
    scored: list[ScoredMemory]
    packed: PackedMemories
    formatted: FormattedContext
    stages: _StageTimings
    policy: TokenizerFamilyPolicy


class ContextAssembler:
    """Retrieve → budget → score → pack → format with degradation classification."""

    def __init__(
        self,
        *,
        settings: ContextSettings,
        retriever: ParallelRetriever,
        deps: _AssemblerDeps | None = None,
    ) -> None:
        resolved = deps or _AssemblerDeps()
        self._settings = settings
        self._retriever = retriever
        self._catalog = resolved.catalog or default_catalog()
        self._budget = resolved.budget or BudgetCalculator(self._catalog)
        self._formatter = resolved.formatter or ContextFormatter(
            nonce_bytes=settings.formatter_nonce_bytes,
        )

    async def assemble(self, request: AssembleRequest) -> AssemblyResult:
        """Run the full assembly pipeline and classify L0–L2."""
        started = time.perf_counter()
        messages = list(request.recent_messages)
        retrieval = await self._retrieve(request, messages)
        level, intentional_skip = _classify_degradation(retrieval, request.options)
        _log_degradation(level, intentional_skip, request, retrieval)
        return self._pack_and_format(
            _PackFormatInput(
                request=request,
                messages=messages,
                retrieval=retrieval,
                level=level,
                started=started,
            )
        )

    def _pack_and_format(self, inp: _PackFormatInput) -> AssemblyResult:
        """Budget → score → pack → format after retrieval / degradation classify."""
        request = inp.request
        retrieval = inp.retrieval
        directive_text = (
            retrieval.directive.content if retrieval.directive is not None else ""
        )
        t_budget = time.perf_counter()
        budget = self._budget.calculate(
            request.model,
            inp.messages,
            directive_text,
            tool_schemas=request.tool_schemas,
        )
        budget = _apply_available_tokens(budget, request.available_tokens)
        budget_ms = _elapsed_ms(t_budget)

        scored, ranking_ms = _score_candidates(retrieval, request.options, inp.level)
        policy = self._catalog.family_policy(
            self._catalog.for_model(request.model).tokenizer_family,
        )
        # Packer estimates raw content; reserve wrap/escape delta so post-format
        # prompt stays within the same usable ceiling (F4-028).
        wrap_reserve = _memory_wrap_reserve(scored, budget.usable_budget, policy)
        pack_budget = max(0, budget.usable_budget - wrap_reserve)
        t_pack = time.perf_counter()
        packed = self._make_packer(request.model).pack(scored, pack_budget)
        packing_ms = _elapsed_ms(t_pack)

        t_fmt = time.perf_counter()
        formatted = self._formatter.format(
            FormatRequest(
                directive=retrieval.directive,
                recent_messages=inp.messages,
                packed=packed,
                tool_schemas=request.tool_schemas,
            )
        )
        stages = _StageTimings(
            budget_ms=budget_ms,
            ranking_ms=ranking_ms,
            packing_ms=packing_ms,
            formatting_ms=_elapsed_ms(t_fmt),
            total_ms=_elapsed_ms(inp.started),
        )
        return _build_assembly_result(
            _AssemblyBuildInput(
                request=request,
                retrieval=retrieval,
                level=inp.level,
                budget=budget,
                scored=scored,
                packed=packed,
                formatted=formatted,
                stages=stages,
                policy=policy,
            )
        )

    async def _retrieve(
        self,
        request: AssembleRequest,
        messages: list[Message],
    ) -> RetrievalResult:
        retrieval_req = RetrievalRequest(
            org_id=request.org_id,
            agent_id=request.agent_id,
            query=request.query,
            model=request.model,
            recent_messages=messages,
        )
        retrieval = await self._retriever.retrieve(retrieval_req)
        return _apply_skip_options(retrieval, request.options)

    def _make_packer(self, model: str) -> ContextPacker:
        policy = self._catalog.family_policy(
            self._catalog.for_model(model).tokenizer_family,
        )
        return ContextPacker(
            policy,
            bucket_size=BUCKET_SIZE,
            dp_cell_ceiling=self._settings.packer_dp_cell_ceiling,
            max_consecutive_skips=self._settings.packer_max_consecutive_skips,
        )


def _score_candidates(
    retrieval: RetrievalResult,
    options: AssemblyOptions,
    level: DegradationLevel,
) -> tuple[list[ScoredMemory], int]:
    t_rank = time.perf_counter()
    if level == "L2":
        scored: list[ScoredMemory] = []
    else:
        merged = _dedupe_hits(retrieval.hot_memories + retrieval.cold_memories)
        scored = score_hits(merged)
        if options.max_memories > 0:
            scored = scored[: options.max_memories]
    return scored, _elapsed_ms(t_rank)


@dataclass(frozen=True, slots=True)
class _StageTimings:
    budget_ms: int
    ranking_ms: int
    packing_ms: int
    formatting_ms: int
    total_ms: int


def _build_assembly_result(inp: _AssemblyBuildInput) -> AssemblyResult:
    metrics = _build_metrics(
        inp.retrieval,
        inp.stages,
        candidates_evaluated=inp.packed.candidates_evaluated,
    )
    logger.debug(
        "context_assembly_timings level=%s budget_ms=%s ranking_ms=%s "
        "packing_ms=%s formatting_ms=%s total_ms=%s candidates=%s",
        inp.level,
        metrics.budget_calculation_ms,
        metrics.ranking_ms,
        metrics.packing_ms,
        metrics.formatting_ms,
        metrics.total_ms,
        metrics.candidates_evaluated,
    )
    budget = inp.budget
    packed = inp.packed
    request = inp.request
    return AssemblyResult(
        formatted=inp.formatted,
        packed=packed,
        budget=budget,
        retrieval=inp.retrieval,
        metrics=metrics,
        degradation_level=inp.level,
        memories_used=_memories_used(inp.scored, packed, inp.policy),
        tokens_used=(
            budget.directive_tokens + budget.messages_tokens + packed.total_tokens
        ),
        request_id=request.request_id,
        trace_id=request.trace_id,
        span_id=request.span_id,
    )


def _build_metrics(
    retrieval: RetrievalResult,
    stages: _StageTimings,
    *,
    candidates_evaluated: int,
) -> AssemblyMetricsSnapshot:
    return AssemblyMetricsSnapshot(
        budget_calculation_ms=stages.budget_ms,
        directive_load_ms=_outcome_ms(retrieval.directive_outcome.latency_ms),
        hot_memory_retrieval_ms=_outcome_ms(retrieval.hot_outcome.latency_ms),
        cold_memory_retrieval_ms=_outcome_ms(retrieval.cold_outcome.latency_ms),
        ranking_ms=stages.ranking_ms,
        packing_ms=stages.packing_ms,
        formatting_ms=stages.formatting_ms,
        total_ms=stages.total_ms,
        candidates_evaluated=candidates_evaluated,
    )


def _log_degradation(
    level: DegradationLevel,
    intentional_skip: bool,
    request: AssembleRequest,
    retrieval: RetrievalResult,
) -> None:
    if level == "L0":
        return
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


def _source_usable(*, skipped: bool, status: str) -> bool:
    """True when the branch produced memories (skip does not count as usable)."""
    return (not skipped) and status == "success"


def _classify_degradation(
    retrieval: RetrievalResult,
    options: AssemblyOptions,
) -> tuple[DegradationLevel, bool]:
    """Return (level, intentional_skip).

    Usable = non-skipped branch with ``success``. Intentional skips are flagged
    separately for logs; they never inflate L0 when the other side is empty.
    """
    hot_usable = _source_usable(
        skipped=options.skip_hot_memories,
        status=retrieval.hot_outcome.status,
    )
    cold_usable = _source_usable(
        skipped=options.skip_cold_memories,
        status=retrieval.cold_outcome.status,
    )
    intentional = options.skip_hot_memories or options.skip_cold_memories

    if hot_usable and cold_usable:
        return "L0", False
    if not hot_usable and not cold_usable:
        return "L2", intentional
    return "L1", intentional


def _memories_used(
    scored: list[ScoredMemory],
    packed: PackedMemories,
    policy: TokenizerFamilyPolicy,
) -> tuple[MemoryUsedRecord, ...]:
    """Emit every scored candidate with pack inclusion / budget / unexamined exclusion."""
    included = {item.memory_id for item in packed.memories}
    budget_excluded = packed.budget_excluded_ids
    estimates = packed.token_estimates
    records: list[MemoryUsedRecord] = []
    for item in scored:
        if item.memory_id in included:
            exclusion = "included"
        elif item.memory_id in budget_excluded:
            exclusion = "budget"
        else:
            # Proto MemoryUsed.exclusion: included|budget|filter|truncated|failed|unknown
            exclusion = "filter"
        # Reuse packer estimates on the assemble hot path; avoid a second
        # estimate_tokens pass when the packer already counted this candidate.
        if item.memory_id in estimates:
            token_estimate = estimates[item.memory_id]
        else:
            token_estimate, _ = estimate_tokens(item.content, policy)
        records.append(_memory_used(item, exclusion=exclusion, token_estimate=token_estimate))
    return tuple(records)


def _memory_wrap_reserve(
    scored: Sequence[ScoredMemory],
    usable_budget: int,
    policy: TokenizerFamilyPolicy,
) -> int:
    """Sum (wrapped - raw) deltas for a greedy content fit under ``usable_budget``.

    Packer charges raw content only; formatter adds tags/escaping. Reserving the
    wrap delta for memories that would fit on content alone keeps post-format
    size within the pre-tool usable ceiling without changing knapsack math.
    """
    if usable_budget <= 0 or not scored:
        return 0
    order = sorted(scored, key=lambda m: (-m.composite_score, m.memory_id))
    used_raw = 0
    reserve = 0
    for item in order:
        raw, _ = estimate_tokens(item.content, policy)
        if raw <= 0:
            continue
        if raw > usable_budget - used_raw:
            continue
        wrapped, _ = estimate_wrapped_memory_tokens(
            content=item.content,
            memory_id=item.memory_id,
            category=item.category,
            policy=policy,
        )
        reserve += max(0, int(wrapped) - int(raw))
        used_raw += int(raw)
    return reserve


def _apply_available_tokens(budget: TokenBudget, available_tokens: int) -> TokenBudget:
    """When available_tokens > 0, cap usable_budget to the caller-requested ceiling."""
    if available_tokens <= 0 or available_tokens >= budget.usable_budget:
        return budget
    return TokenBudget(
        context_window=budget.context_window,
        response_reserve=budget.response_reserve,
        safety_buffer=budget.safety_buffer,
        usable_budget=available_tokens,
        directive_tokens=budget.directive_tokens,
        messages_tokens=budget.messages_tokens,
        is_constrained=available_tokens < MIN_VIABLE_MEMORY_BUDGET,
        estimate_kind=budget.estimate_kind,
        tool_schemas_tokens=budget.tool_schemas_tokens,
        formatter_overhead_tokens=budget.formatter_overhead_tokens,
    )


def _memory_used(
    item: ScoredMemory,
    *,
    exclusion: str,
    token_estimate: int,
) -> MemoryUsedRecord:
    # Interim packer score only; wire does not yet expose recency/usefulness.
    return MemoryUsedRecord(
        memory_id=item.memory_id,
        composite_score=float(item.composite_score),
        relevance_score=float(item.hit.similarity),
        recency_score=0.0,
        usefulness_score=0.0,
        rank=int(item.hit.rank),
        category=item.category,
        exclusion=exclusion,
        similarity=float(item.hit.similarity),
        confidence=float(item.hit.confidence),
        token_estimate=token_estimate,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000.0))


def _outcome_ms(latency_ms: float) -> int:
    return max(0, round(latency_ms))
