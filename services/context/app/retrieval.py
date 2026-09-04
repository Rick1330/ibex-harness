"""Parallel retrieval orchestration (milestone 3.5.C.2).

Three concurrent branches — not four
=====================================
The milestone MDX originally sketched a fourth ``history_task`` that would
read conversation text from the session-checkpoint store. That branch is
**not implemented** and must not be reintroduced:

1. ``AssembleContextRequest.recent_messages`` already carries history
   (packages/proto/.../context.proto) — zero I/O.
2. ``ibex_core.checkpoints`` stores ``messages_hash`` only, not message text
   (infra/migrations/postgres/000010_create_sessions.up.sql).
3. ``packages/session.Store`` exposes GetOrCreate / AppendCheckpoint /
   Complete / AbandonIdle — no history-read API.

``recent_messages`` are token-counted into ``history_tokens`` via
``BudgetCalculator`` (3.5.C.1). Cold search embeds **server-side** inside
``POST /v1/memories/search``; this orchestrator must not call the embedder
itself (would double-pay latency inside the ~45ms budget).

Forward mapping for 3.5.C.6 (gRPC AssembleContextResponse)
==========================================================
- ``history_tokens`` → ``AssembleContextResponse.history_tokens``
- ``hot_memories`` + ``cold_memories`` → ``memories_used`` / ``memory_tokens``
- branch ``latency_ms`` → ``AssemblyMetrics`` fields
- ``sources_available`` → future sources_used / metrics flag
- ``directive.content`` → directive injection + ``directive_tokens``

Do not modify context.proto in this milestone.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.budget import BudgetCalculator, Message
from app.clients.directive import (
    DirectiveLookup,
    DirectiveLookupError,
    DirectivePayload,
    EmptyDirectiveLookup,
)
from app.clients.memory import (
    MemoryHitPayload,
    MemoryHttpClient,
    MemoryHttpError,
    MemoryHttpTimeout,
)
from app.config import ContextSettings

BranchStatus = Literal["success", "timeout", "error"]
SourceName = Literal["directive", "hot", "cold"]


@dataclass(frozen=True, slots=True)
class BranchOutcome:
    status: BranchStatus
    latency_ms: float
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedDirective:
    content: str
    injection_mode: str
    version_id: str | None


@dataclass(frozen=True, slots=True)
class MemoryHit:
    memory_id: str
    org_id: str
    agent_id: str
    content: str
    category: str
    confidence: float
    similarity: float
    rank: int
    source: str


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    org_id: UUID
    agent_id: UUID
    query: str
    model: str
    recent_messages: Sequence[Message]
    hot_limit: int = 20
    cold_limit: int = 10
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    directive: ResolvedDirective | None
    directive_outcome: BranchOutcome
    hot_memories: list[MemoryHit]
    hot_outcome: BranchOutcome
    cold_memories: list[MemoryHit]
    cold_outcome: BranchOutcome
    recent_messages: list[Message]
    history_tokens: int
    sources_available: frozenset[str]


@dataclass(frozen=True, slots=True)
class _BranchResult:
    name: SourceName
    outcome: BranchOutcome
    directive: ResolvedDirective | None = None
    memories: tuple[MemoryHit, ...] = ()


class ParallelRetriever:
    """Fan out directive + hot + cold under per-branch and outer timeouts."""

    def __init__(
        self,
        *,
        settings: ContextSettings,
        memory: MemoryHttpClient,
        directive: DirectiveLookup | None = None,
        budget: BudgetCalculator | None = None,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._directive: DirectiveLookup = directive or EmptyDirectiveLookup()
        self._budget = budget or BudgetCalculator()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        messages = list(request.recent_messages)
        # Count history before I/O so a total outer timeout still yields tokens.
        history_tokens = self._budget.calculate(
            request.model,
            messages,
            directive="",
        ).messages_tokens

        branch_results = await self._gather_branches(request)
        return _merge_results(branch_results, messages=messages, history_tokens=history_tokens)

    async def _gather_branches(
        self,
        request: RetrievalRequest,
    ) -> tuple[_BranchResult, _BranchResult, _BranchResult]:
        """Run three branches; on outer deadline keep finished work, cancel the rest."""
        named = (
            ("directive", asyncio.create_task(self._directive_branch(request))),
            ("hot", asyncio.create_task(self._hot_branch(request))),
            ("cold", asyncio.create_task(self._cold_branch(request))),
        )
        tasks = {task: name for name, task in named}
        outer_s = self._settings.timeout_ms / 1000.0
        done, pending = await asyncio.wait(tasks.keys(), timeout=outer_s)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        results: dict[str, _BranchResult] = {}
        for task in done:
            name = tasks[task]
            try:
                results[name] = _coerce_branch(name, task.result())  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                results[name] = _BranchResult(
                    name=name,  # type: ignore[arg-type]
                    outcome=BranchOutcome("error", 0.0, type(exc).__name__),
                )
        for task in pending:
            name = tasks[task]
            results[name] = _BranchResult(
                name=name,  # type: ignore[arg-type]
                outcome=BranchOutcome(
                    "timeout",
                    self._settings.timeout_ms,
                    "outer_deadline",
                ),
            )
        return (results["directive"], results["hot"], results["cold"])

    async def _directive_branch(self, request: RetrievalRequest) -> _BranchResult:
        timeout_s = self._settings.directive_timeout_ms / 1000.0
        started = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                self._directive.lookup(request.org_id, request.agent_id),
                timeout=timeout_s,
            )
        except TimeoutError:
            return _BranchResult(
                name="directive",
                outcome=BranchOutcome(
                    "timeout",
                    (time.perf_counter() - started) * 1000.0,
                    "directive_timeout",
                ),
            )
        except DirectiveLookupError as exc:
            return _BranchResult(
                name="directive",
                outcome=BranchOutcome(
                    "error",
                    (time.perf_counter() - started) * 1000.0,
                    str(exc),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — fail-open
            return _BranchResult(
                name="directive",
                outcome=BranchOutcome(
                    "error",
                    (time.perf_counter() - started) * 1000.0,
                    type(exc).__name__,
                ),
            )
        elapsed = (time.perf_counter() - started) * 1000.0
        resolved = _directive_from_payload(payload)
        # Empty content is a successful lookup (agent has no directive).
        return _BranchResult(
            name="directive",
            outcome=BranchOutcome("success", elapsed),
            directive=resolved if resolved.content else None,
        )

    async def _hot_branch(self, request: RetrievalRequest) -> _BranchResult:
        timeout_s = self._settings.hot_timeout_ms / 1000.0
        started = time.perf_counter()
        try:
            hits = await asyncio.wait_for(
                self._memory.get_hot_memories(
                    agent_id=request.agent_id,
                    limit=request.hot_limit,
                    min_confidence=request.min_confidence,
                    timeout_seconds=timeout_s,
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            return _timeout_memories("hot", started, "hot_timeout")
        except MemoryHttpTimeout:
            return _timeout_memories("hot", started, "hot_http_timeout")
        except MemoryHttpError as exc:
            return _error_memories("hot", started, str(exc))
        except Exception as exc:  # noqa: BLE001 — fail-open
            return _error_memories("hot", started, type(exc).__name__)
        return _success_memories("hot", started, hits)

    async def _cold_branch(self, request: RetrievalRequest) -> _BranchResult:
        timeout_s = self._settings.cold_timeout_ms / 1000.0
        started = time.perf_counter()
        try:
            hits = await asyncio.wait_for(
                self._memory.search_memories(
                    agent_id=request.agent_id,
                    query=request.query,
                    limit=request.cold_limit,
                    min_confidence=request.min_confidence,
                    timeout_seconds=timeout_s,
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            return _timeout_memories("cold", started, "cold_timeout")
        except MemoryHttpTimeout:
            return _timeout_memories("cold", started, "cold_http_timeout")
        except MemoryHttpError as exc:
            return _error_memories("cold", started, str(exc))
        except Exception as exc:  # noqa: BLE001 — fail-open
            return _error_memories("cold", started, type(exc).__name__)
        return _success_memories("cold", started, hits)


def _directive_from_payload(payload: DirectivePayload) -> ResolvedDirective:
    return ResolvedDirective(
        content=payload.content,
        injection_mode=payload.injection_mode,
        version_id=payload.version_id,
    )


def _hit_from_payload(payload: MemoryHitPayload) -> MemoryHit:
    return MemoryHit(
        memory_id=payload.memory_id,
        org_id=payload.org_id,
        agent_id=payload.agent_id,
        content=payload.content,
        category=payload.category,
        confidence=payload.confidence,
        similarity=payload.similarity,
        rank=payload.rank,
        source=payload.source,
    )


def _success_memories(
    name: SourceName,
    started: float,
    hits: list[MemoryHitPayload],
) -> _BranchResult:
    return _BranchResult(
        name=name,
        outcome=BranchOutcome("success", (time.perf_counter() - started) * 1000.0),
        memories=tuple(_hit_from_payload(h) for h in hits),
    )


def _timeout_memories(name: SourceName, started: float, detail: str) -> _BranchResult:
    return _BranchResult(
        name=name,
        outcome=BranchOutcome("timeout", (time.perf_counter() - started) * 1000.0, detail),
    )


def _error_memories(name: SourceName, started: float, detail: str) -> _BranchResult:
    return _BranchResult(
        name=name,
        outcome=BranchOutcome("error", (time.perf_counter() - started) * 1000.0, detail),
    )


def _coerce_branch(name: SourceName, value: object) -> _BranchResult:
    if isinstance(value, _BranchResult):
        return value
    if isinstance(value, BaseException):
        return _BranchResult(
            name=name,
            outcome=BranchOutcome("error", 0.0, type(value).__name__),
        )
    return _BranchResult(
        name=name,
        outcome=BranchOutcome("error", 0.0, "unexpected_branch_result"),
    )


def _merge_results(
    branches: tuple[_BranchResult, _BranchResult, _BranchResult],
    *,
    messages: list[Message],
    history_tokens: int,
) -> RetrievalResult:
    by_name = {b.name: b for b in branches}
    directive_b = by_name["directive"]
    hot_b = by_name["hot"]
    cold_b = by_name["cold"]
    sources: set[str] = set()
    if directive_b.outcome.status == "success":
        sources.add("directive")
    if hot_b.outcome.status == "success":
        sources.add("hot")
    if cold_b.outcome.status == "success":
        sources.add("cold")
    return RetrievalResult(
        directive=directive_b.directive,
        directive_outcome=directive_b.outcome,
        hot_memories=list(hot_b.memories),
        hot_outcome=hot_b.outcome,
        cold_memories=list(cold_b.memories),
        cold_outcome=cold_b.outcome,
        recent_messages=messages,
        history_tokens=history_tokens,
        sources_available=frozenset(sources),
    )
