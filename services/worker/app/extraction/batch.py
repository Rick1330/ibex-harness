"""Session-close batch extraction orchestration (provider + memory + traces)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.extraction.clickhouse_traces import ExtractionTraceRow, insert_extraction_trace
from app.extraction.memory_writer import MemoryWriter
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from app.extraction.provider import ExtractionCall, ExtractionProvider
from app.extraction.schema import BatchExtractionResult
from app.extraction.session_store import SessionStore


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


def format_batch_user_content(turns: list[TurnPayload]) -> str:
    return "\n".join(
        f'<turn index="{item.turn_index}" role="{item.role}">\n{item.content}\n</turn>'
        for item in turns
    )


def parse_batch_result(raw_json: str) -> BatchExtractionResult:
    return BatchExtractionResult.model_validate_json(raw_json)


def select_unprocessed_turns(
    turns: list[TurnPayload], last_extracted_turn: int
) -> list[TurnPayload]:
    return [item for item in turns if item.turn_index > last_extracted_turn]


def parse_turns(raw: Any) -> list[TurnPayload]:
    if not isinstance(raw, list):
        raise TypeError("turns must be a list")
    return [TurnPayload.model_validate(item) for item in raw]


def run_batch_extraction(
    *,
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    turns: list[TurnPayload],
    provider: ExtractionProvider,
    memory_writer: MemoryWriter,
    clickhouse_dsn: str | None,
    session_store: SessionStore | None = None,
) -> BatchRunResult:
    """Extract, write memories, log usage, optionally bump last_extracted_turn."""
    pending = _filter_pending(org_id, session_id, turns, session_store)
    if isinstance(pending, BatchRunResult):
        return pending

    started = datetime.now(UTC)
    call = provider.extract(
        EXTRACTION_SYSTEM_PROMPT_BATCH,
        format_batch_user_content(pending),
    )
    completed = datetime.now(UTC)
    batch = parse_batch_result(call.raw_json)
    written = _write_memories(
        org_id=org_id,
        agent_id=agent_id,
        session_id=session_id,
        batch=batch,
        memory_writer=memory_writer,
    )
    _log_trace(
        org_id=org_id,
        agent_id=agent_id,
        session_id=session_id,
        provider_name=provider.name,
        call=call,
        started=started,
        completed=completed,
        clickhouse_dsn=clickhouse_dsn,
    )
    max_turn = max(item.turn_index for item in pending)
    if session_store is not None:
        session_store.update_last_extracted_turn(org_id, session_id, max_turn)
    return BatchRunResult(written, len(pending))


def _filter_pending(
    org_id: UUID,
    session_id: UUID,
    turns: list[TurnPayload],
    session_store: SessionStore | None,
) -> list[TurnPayload] | BatchRunResult:
    if session_store is None:
        return turns if turns else BatchRunResult(0, 0, skipped="no_unprocessed_turns")
    snapshot = session_store.load(org_id, session_id)
    if snapshot is None:
        return BatchRunResult(0, 0, skipped="session_not_found")
    if snapshot.deleted_at is not None or snapshot.status != "completed":
        return BatchRunResult(0, 0, skipped="session_not_ready")
    pending = select_unprocessed_turns(turns, snapshot.last_extracted_turn)
    if not pending:
        return BatchRunResult(0, 0, skipped="no_unprocessed_turns")
    return pending


def _write_memories(
    *,
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    batch: BatchExtractionResult,
    memory_writer: MemoryWriter,
) -> int:
    count = 0
    for turn in batch.turns:
        for memory in turn.memories:
            memory_writer.write(
                org_id=org_id,
                agent_id=agent_id,
                session_id=session_id,
                turn_index=turn.turn_index,
                memory=memory,
            )
            count += 1
    return count


def _log_trace(
    *,
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    provider_name: str,
    call: ExtractionCall,
    started: datetime,
    completed: datetime,
    clickhouse_dsn: str | None,
) -> None:
    insert_extraction_trace(
        dsn=clickhouse_dsn,
        row=ExtractionTraceRow(
            request_id=str(uuid4()),
            org_id=org_id,
            agent_id=agent_id,
            session_id=session_id,
            model=call.model,
            provider=provider_name,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            provider_ttfb_ms=call.latency_ms,
            total_latency_ms=call.latency_ms,
            status_code=200,
            is_complete=True,
            error_code="",
            requested_at=started,
            completed_at=completed,
        ),
    )
