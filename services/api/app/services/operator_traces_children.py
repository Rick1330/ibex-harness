"""Child evidence loaders for operator run detail (spans, assembly, candidates, …)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from apierror_py import SERVICE_DEGRADED
from sqlalchemy import bindparam, column, func, select, table
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.schemas.operator_traces import (
    OperatorTraceAssemblyMetrics,
    OperatorTraceCandidate,
    OperatorTraceDirectiveSnapshot,
    OperatorTraceSpan,
    OperatorTraceToolAudit,
    UnavailableSection,
)

_TRACE_UNAVAILABLE = "Trace data is temporarily unavailable"

_EVIDENCE_SPANS = table(
    "evidence_spans",
    column("org_id"),
    column("run_id"),
    column("span_id"),
    column("parent_span_id"),
    column("operation_kind"),
    column("status"),
    column("error_code"),
    column("started_at"),
    column("ended_at"),
    schema="ibex_core",
)

_EVIDENCE_ASSEMBLY = table(
    "evidence_assembly_metrics",
    column("org_id"),
    column("run_id"),
    column("budget_calculation_ms"),
    column("directive_load_ms"),
    column("hot_memory_retrieval_ms"),
    column("cold_memory_retrieval_ms"),
    column("ranking_ms"),
    column("packing_ms"),
    column("formatting_ms"),
    column("total_ms"),
    column("candidates_evaluated"),
    schema="ibex_core",
)

_EVIDENCE_CANDIDATES = table(
    "evidence_score_candidates",
    column("org_id"),
    column("run_id"),
    column("memory_id"),
    column("retrieval_rank"),
    column("final_rank"),
    column("delta_rank"),
    column("category"),
    column("token_estimate"),
    column("exclusion"),
    column("score_schema"),
    column("composite_score"),
    schema="ibex_core",
)

_EVIDENCE_DIRECTIVES = table(
    "evidence_directive_snapshots",
    column("org_id"),
    column("run_id"),
    column("directive_version_id"),
    column("content_hash"),
    column("schema_version"),
    schema="ibex_core",
)

_EVIDENCE_TOOLS = table(
    "evidence_tool_audits",
    column("org_id"),
    column("run_id"),
    column("tool_name"),
    column("status"),
    column("error_code"),
    column("created_at"),
    schema="ibex_core",
)


async def fetch_rows(session: AsyncSession, query: Any, params: dict[str, object]) -> list[Any]:
    try:
        await session.execute(select(func.set_config("statement_timeout", "3000ms", True)))
        result = await session.execute(query, params)
        return list(result.mappings().all())
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_TRACE_UNAVAILABLE) from exc


async def load_spans(session: AsyncSession, org_id: UUID, run_id: UUID) -> list[OperatorTraceSpan]:
    sql = (
        select(
            _EVIDENCE_SPANS.c.span_id,
            _EVIDENCE_SPANS.c.parent_span_id,
            _EVIDENCE_SPANS.c.operation_kind,
            _EVIDENCE_SPANS.c.status,
            _EVIDENCE_SPANS.c.error_code,
            _EVIDENCE_SPANS.c.started_at,
            _EVIDENCE_SPANS.c.ended_at,
        )
        .where(
            _EVIDENCE_SPANS.c.org_id == bindparam("org_id"),
            _EVIDENCE_SPANS.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_SPANS.c.started_at.asc())
        .limit(500)
    )
    rows = await fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    return [
        OperatorTraceSpan(
            span_id=str(row["span_id"]),
            parent_span_id=str(row["parent_span_id"]) if row["parent_span_id"] else None,
            operation_kind=str(row["operation_kind"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
        for row in rows
    ]


async def load_assembly(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> OperatorTraceAssemblyMetrics | None:
    sql = (
        select(
            _EVIDENCE_ASSEMBLY.c.budget_calculation_ms,
            _EVIDENCE_ASSEMBLY.c.directive_load_ms,
            _EVIDENCE_ASSEMBLY.c.hot_memory_retrieval_ms,
            _EVIDENCE_ASSEMBLY.c.cold_memory_retrieval_ms,
            _EVIDENCE_ASSEMBLY.c.ranking_ms,
            _EVIDENCE_ASSEMBLY.c.packing_ms,
            _EVIDENCE_ASSEMBLY.c.formatting_ms,
            _EVIDENCE_ASSEMBLY.c.total_ms,
            _EVIDENCE_ASSEMBLY.c.candidates_evaluated,
        )
        .where(
            _EVIDENCE_ASSEMBLY.c.org_id == bindparam("org_id"),
            _EVIDENCE_ASSEMBLY.c.run_id == bindparam("run_id"),
        )
        .limit(1)
    )
    rows = await fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    if not rows:
        return None
    row = rows[0]
    return OperatorTraceAssemblyMetrics(
        budget_calculation_ms=int(row["budget_calculation_ms"]),
        directive_load_ms=int(row["directive_load_ms"]),
        hot_memory_retrieval_ms=int(row["hot_memory_retrieval_ms"]),
        cold_memory_retrieval_ms=int(row["cold_memory_retrieval_ms"]),
        ranking_ms=int(row["ranking_ms"]),
        packing_ms=int(row["packing_ms"]),
        formatting_ms=int(row["formatting_ms"]),
        total_ms=int(row["total_ms"]),
        candidates_evaluated=int(row["candidates_evaluated"]),
    )


async def load_candidates(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> tuple[list[OperatorTraceCandidate], str | None]:
    sql = (
        select(
            _EVIDENCE_CANDIDATES.c.memory_id,
            _EVIDENCE_CANDIDATES.c.retrieval_rank,
            _EVIDENCE_CANDIDATES.c.final_rank,
            _EVIDENCE_CANDIDATES.c.delta_rank,
            _EVIDENCE_CANDIDATES.c.category,
            _EVIDENCE_CANDIDATES.c.token_estimate,
            _EVIDENCE_CANDIDATES.c.exclusion,
            _EVIDENCE_CANDIDATES.c.score_schema,
            _EVIDENCE_CANDIDATES.c.composite_score,
        )
        .where(
            _EVIDENCE_CANDIDATES.c.org_id == bindparam("org_id"),
            _EVIDENCE_CANDIDATES.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_CANDIDATES.c.retrieval_rank.asc())
        .limit(500)
    )
    rows = await fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    note = None
    if any(str(row["score_schema"]) == "interim_v1" for row in rows):
        note = "Score rows use interim_v1; five-term waterfall explanation is not rendered."
    candidates = [
        OperatorTraceCandidate(
            memory_id=UUID(str(row["memory_id"])),
            retrieval_rank=int(row["retrieval_rank"]),
            final_rank=int(row["final_rank"]) if row["final_rank"] is not None else None,
            delta_rank=int(row["delta_rank"]) if row["delta_rank"] is not None else None,
            category=str(row["category"]) if row["category"] else None,
            token_estimate=int(row["token_estimate"]) if row["token_estimate"] is not None else None,
            exclusion=str(row["exclusion"]),
            score_schema=str(row["score_schema"]),
            composite_score=float(row["composite_score"]) if row["composite_score"] is not None else None,
        )
        for row in rows
    ]
    return candidates, note


async def load_directive(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> OperatorTraceDirectiveSnapshot | None:
    sql = (
        select(
            _EVIDENCE_DIRECTIVES.c.directive_version_id,
            _EVIDENCE_DIRECTIVES.c.content_hash,
            _EVIDENCE_DIRECTIVES.c.schema_version,
        )
        .where(
            _EVIDENCE_DIRECTIVES.c.org_id == bindparam("org_id"),
            _EVIDENCE_DIRECTIVES.c.run_id == bindparam("run_id"),
        )
        .limit(1)
    )
    rows = await fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    if not rows:
        return None
    row = rows[0]
    return OperatorTraceDirectiveSnapshot(
        directive_version_id=UUID(str(row["directive_version_id"])) if row["directive_version_id"] else None,
        content_hash=str(row["content_hash"]) if row["content_hash"] else None,
        schema_version=str(row["schema_version"]),
    )


async def load_tools(session: AsyncSession, org_id: UUID, run_id: UUID) -> list[OperatorTraceToolAudit]:
    sql = (
        select(
            _EVIDENCE_TOOLS.c.tool_name,
            _EVIDENCE_TOOLS.c.status,
            _EVIDENCE_TOOLS.c.error_code,
            _EVIDENCE_TOOLS.c.created_at,
        )
        .where(
            _EVIDENCE_TOOLS.c.org_id == bindparam("org_id"),
            _EVIDENCE_TOOLS.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_TOOLS.c.created_at.asc())
        .limit(200)
    )
    rows = await fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    return [
        OperatorTraceToolAudit(
            tool_name=str(row["tool_name"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            started_at=row["created_at"],
            ended_at=None,
        )
        for row in rows
    ]


RunChildren = tuple[
    list[OperatorTraceSpan],
    OperatorTraceAssemblyMetrics | None,
    list[OperatorTraceCandidate],
    str | None,
    OperatorTraceDirectiveSnapshot | None,
    list[OperatorTraceToolAudit],
]


async def load_run_children(session: AsyncSession, org_id: UUID, run_id: UUID) -> RunChildren:
    spans = await load_spans(session, org_id, run_id)
    assembly = await load_assembly(session, org_id, run_id)
    candidates, score_note = await load_candidates(session, org_id, run_id)
    directive = await load_directive(session, org_id, run_id)
    tools = await load_tools(session, org_id, run_id)
    return spans, assembly, candidates, score_note, directive, tools


def unavailable_sections(children: RunChildren) -> list[UnavailableSection]:
    spans, assembly, candidates, score_note, directive, tools = children
    sections: list[UnavailableSection] = ["content", "events"]
    if not spans:
        sections.append("spans")
    if assembly is None:
        sections.append("assembly")
    if not candidates:
        sections.extend(("candidates", "score_explanation"))
    elif score_note:
        sections.append("score_explanation")
    if directive is None:
        sections.append("directives")
    if not tools:
        sections.append("tools")
    return sections
