"""Session-close batch extraction orchestration (provider + memory + traces).

Pointer update is ordered after definitive memory writes but not in a shared
cross-service transaction (ADR-0065). Idempotency is batch-position keyed.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.extraction.clickhouse_traces import ExtractionTraceRow, insert_extraction_trace
from app.extraction.memory_writer import (
    MemoryWriter,
    MemoryWriteRequest,
    TurnContentRef,
    batch_fingerprint,
)
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from app.extraction.provider import ExtractionCall, ExtractionProvider, ExtractionTransportError
from app.extraction.schema import BatchExtractionResult
from app.extraction.session_store import SessionStore

logger = logging.getLogger(__name__)

MAX_TURNS_PER_BATCH = 50
MAX_BATCH_CONTENT_BYTES = 500_000


class TurnPayload(BaseModel):
    """Conversation turn supplied in the Celery payload (not from checkpoints)."""

    turn_index: int = Field(ge=0)
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=100_000)


@dataclass(frozen=True, slots=True)
class BatchRunResult:
    memories_written: int
    turns_processed: int
    skipped: str | None = None


@dataclass(frozen=True, slots=True)
class BatchJob:
    org_id: UUID
    agent_id: UUID
    session_id: UUID
    turns: list[TurnPayload]
    provider: ExtractionProvider
    memory_writer: MemoryWriter
    clickhouse_dsn: str | None
    session_store: SessionStore | None = None


def format_batch_user_content(turns: list[TurnPayload]) -> str:
    parts: list[str] = []
    for item in turns:
        role = html.escape(item.role, quote=True)
        content = html.escape(item.content)
        parts.append(f'<turn index="{item.turn_index}" role="{role}">\n{content}\n</turn>')
    return "\n".join(parts)


def parse_batch_result(raw_json: str) -> BatchExtractionResult:
    return BatchExtractionResult.model_validate_json(raw_json)


def select_unprocessed_turns(
    turns: list[TurnPayload], last_extracted_turn: int
) -> list[TurnPayload]:
    return [item for item in turns if item.turn_index > last_extracted_turn]


def parse_turns(raw: Any) -> list[TurnPayload]:
    items = _require_turn_list(raw)
    parsed = [TurnPayload.model_validate(item) for item in items]
    _reject_duplicate_indexes([item.turn_index for item in parsed], "turns")
    _enforce_serialized_budget(parsed)
    return parsed


def _require_turn_list(raw: Any) -> list[Any]:
    if not isinstance(raw, list):
        raise TypeError("turns must be a list")
    if len(raw) > MAX_TURNS_PER_BATCH:
        raise ValueError(f"turns must contain at most {MAX_TURNS_PER_BATCH} items")
    return raw


def _enforce_serialized_budget(parsed: list[TurnPayload]) -> None:
    serialized = format_batch_user_content(parsed)
    if len(serialized.encode("utf-8")) > MAX_BATCH_CONTENT_BYTES:
        raise ValueError("turns content exceeds UTF-8 byte cap")


def _reject_duplicate_indexes(indexes: list[int], label: str) -> None:
    if len(indexes) != len(set(indexes)):
        raise ValueError(f"duplicate turn_index in {label}")


def require_exact_turn_indexes(
    pending: list[TurnPayload], batch: BatchExtractionResult
) -> None:
    expected = [item.turn_index for item in pending]
    got = [item.turn_index for item in batch.turns]
    _reject_duplicate_indexes(expected, "pending turns")
    _reject_duplicate_indexes(got, "provider results")
    if len(expected) != len(got) or set(expected) != set(got):
        raise ValueError("provider turn_index set must match pending turns exactly")


def run_batch_extraction(job: BatchJob) -> BatchRunResult:
    """Extract, write memories, log usage, optionally bump last_extracted_turn."""
    pending = _filter_pending(job)
    if isinstance(pending, BatchRunResult):
        return pending
    started = datetime.now(UTC)
    user_content = format_batch_user_content(pending)
    if len(user_content.encode("utf-8")) > MAX_BATCH_CONTENT_BYTES:
        raise ValueError("turns content exceeds UTF-8 byte cap")
    call = job.provider.extract(
        EXTRACTION_SYSTEM_PROMPT_BATCH,
        user_content,
    )
    completed = datetime.now(UTC)
    try:
        written = _persist_parsed(job, pending, call)
    except Exception as exc:
        _log_trace(job, call, (started, completed), (False, type(exc).__name__))
        raise
    _log_trace(job, call, (started, completed), (True, ""))
    max_turn = max(item.turn_index for item in pending)
    _update_pointer_after_writes(job, max_turn)
    return BatchRunResult(written, len(pending))


def _persist_parsed(
    job: BatchJob, pending: list[TurnPayload], call: ExtractionCall
) -> int:
    batch = parse_batch_result(call.raw_json)
    require_exact_turn_indexes(pending, batch)
    return _write_memories(job, pending, batch)


def _filter_pending(job: BatchJob) -> list[TurnPayload] | BatchRunResult:
    if job.session_store is None:
        if not job.turns:
            return BatchRunResult(0, 0, skipped="no_unprocessed_turns")
        return job.turns
    snapshot = job.session_store.load(job.org_id, job.session_id)
    if snapshot is None:
        return BatchRunResult(0, 0, skipped="session_not_found")
    if snapshot.deleted_at is not None or snapshot.status != "completed":
        return BatchRunResult(0, 0, skipped="session_not_ready")
    pending = select_unprocessed_turns(job.turns, snapshot.last_extracted_turn)
    if not pending:
        return BatchRunResult(0, 0, skipped="no_unprocessed_turns")
    return pending


def _write_memories(
    job: BatchJob, pending: list[TurnPayload], batch: BatchExtractionResult
) -> int:
    fingerprint = batch_fingerprint(
        [TurnContentRef(turn_index=t.turn_index, content=t.content) for t in pending]
    )
    count = 0
    for turn in batch.turns:
        for ordinal, memory in enumerate(turn.memories):
            job.memory_writer.write(
                MemoryWriteRequest(
                    org_id=job.org_id,
                    agent_id=job.agent_id,
                    session_id=job.session_id,
                    turn_index=turn.turn_index,
                    memory=memory,
                    batch_fingerprint=fingerprint,
                    ordinal=ordinal,
                )
            )
            count += 1
    return count


def _update_pointer_after_writes(job: BatchJob, max_turn: int) -> None:
    """Advance last_extracted_turn only after all writes succeeded (ADR-0065)."""
    if job.session_store is None:
        return
    try:
        job.session_store.update_last_extracted_turn(job.org_id, job.session_id, max_turn)
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise ExtractionTransportError("session pointer update failed") from exc


def _log_trace(
    job: BatchJob,
    call: ExtractionCall,
    window: tuple[datetime, datetime],
    outcome: tuple[bool, str],
) -> None:
    started, completed = window
    is_complete, error_code = outcome
    try:
        insert_extraction_trace(
            dsn=job.clickhouse_dsn,
            row=ExtractionTraceRow(
                request_id=str(uuid4()),
                org_id=job.org_id,
                agent_id=job.agent_id,
                session_id=job.session_id,
                model=call.model,
                provider=job.provider.name,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                provider_ttfb_ms=call.latency_ms,
                total_latency_ms=call.latency_ms,
                status_code=200 if is_complete else 500,
                is_complete=is_complete,
                error_code=error_code,
                requested_at=started,
                completed_at=completed,
            ),
        )
    except Exception:  # noqa: BLE001 — never mask parse/write errors
        logger.warning("extraction_clickhouse_insert_failed", extra={"reason": "unexpected"})
