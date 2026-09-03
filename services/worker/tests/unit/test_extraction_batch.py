"""Unit tests for batched session extraction mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.celery_app import celery_app
from app.extraction.batch import (
    TurnPayload,
    format_batch_user_content,
    parse_turns,
    run_batch_extraction,
    select_unprocessed_turns,
)
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from app.extraction.provider import ExtractionCall, ExtractionTransportError
from app.extraction.schema import BatchExtractionResult, ExtractedMemory
from app.extraction.session_store import SessionSnapshot
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.extraction import extract_session_memories


class _FakeProvider:
    def __init__(self, n: int) -> None:
        self.n = n
        self.last_user = ""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> tuple[str, ...]:
        return ("gpt-4o-mini",)

    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        self.last_user = user_content
        assert "turns" in system_prompt.lower() or "turn_index" in system_prompt
        turns = [
            {
                "turn_index": i,
                "memories": [
                    {
                        "content": f"Durable preference recorded from turn {i:02d}",
                        "categories": [{"label": "preference", "confidence": 0.9}],
                        "confidence": 0.91,
                    }
                ],
            }
            for i in range(self.n)
        ]
        return ExtractionCall(
            raw_json=json.dumps({"turns": turns}),
            model="gpt-4o-mini",
            input_tokens=12,
            output_tokens=34,
            latency_ms=8,
        )


class _RecordingWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[int, str]] = []

    def write(self, *, org_id, agent_id, session_id, turn_index, memory) -> None:
        del org_id, agent_id, session_id
        self.writes.append((turn_index, memory.content))


class _SessionStore:
    def __init__(self, snapshot: SessionSnapshot | None) -> None:
        self.snapshot = snapshot
        self.updated: int | None = None

    def load(self, org_id, session_id) -> SessionSnapshot | None:
        del org_id, session_id
        return self.snapshot

    def update_last_extracted_turn(self, org_id, session_id, last_extracted_turn: int) -> None:
        del org_id, session_id
        self.updated = last_extracted_turn


def _turns(n: int) -> list[TurnPayload]:
    return [
        TurnPayload(turn_index=i, role="user", content=f"turn body {i} durable")
        for i in range(n)
    ]


@pytest.mark.parametrize("size", [1, 10, 50])
def test_batch_sizes_map_turn_indexes(size: int) -> None:
    provider = _FakeProvider(size)
    writer = _RecordingWriter()
    org_id, agent_id, session_id = uuid4(), uuid4(), uuid4()
    result = run_batch_extraction(
        org_id=org_id,
        agent_id=agent_id,
        session_id=session_id,
        turns=_turns(size),
        provider=provider,
        memory_writer=writer,
        clickhouse_dsn=None,
    )
    assert result.skipped is None
    assert result.turns_processed == size
    assert result.memories_written == size
    indexes = [idx for idx, _ in writer.writes]
    assert indexes == list(range(size))
    for i in range(size):
        assert f"index=\"{i}\"" in provider.last_user


def test_skips_turns_at_or_below_last_extracted_turn() -> None:
    provider = _FakeProvider(2)
    writer = _RecordingWriter()
    store = _SessionStore(
        SessionSnapshot(last_extracted_turn=7, status="completed", deleted_at=None)
    )
    turns = [
        TurnPayload(turn_index=7, role="user", content="already extracted turn xx"),
        TurnPayload(turn_index=8, role="user", content="new turn eight content"),
        TurnPayload(turn_index=9, role="user", content="new turn nine content"),
    ]
    # Provider returns turn_index 0,1 — mapping uses model output indexes.
    result = run_batch_extraction(
        org_id=uuid4(),
        agent_id=uuid4(),
        session_id=uuid4(),
        turns=turns,
        provider=provider,
        memory_writer=writer,
        clickhouse_dsn=None,
        session_store=store,
    )
    assert result.turns_processed == 2
    assert store.updated == 9
    assert "index=\"8\"" in provider.last_user
    assert "index=\"7\"" not in provider.last_user


def test_incomplete_session_skipped() -> None:
    writer = _RecordingWriter()
    store = _SessionStore(
        SessionSnapshot(last_extracted_turn=0, status="active", deleted_at=None)
    )
    result = run_batch_extraction(
        org_id=uuid4(),
        agent_id=uuid4(),
        session_id=uuid4(),
        turns=_turns(1),
        provider=_FakeProvider(1),
        memory_writer=writer,
        clickhouse_dsn=None,
        session_store=store,
    )
    assert result.skipped == "session_not_ready"
    assert writer.writes == []


def test_duplicate_turn_index_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate turn_index"):
        BatchExtractionResult.model_validate(
            {
                "turns": [
                    {"turn_index": 1, "memories": []},
                    {"turn_index": 1, "memories": []},
                ]
            }
        )


def test_select_unprocessed() -> None:
    turns = _turns(5)
    pending = select_unprocessed_turns(turns, 2)
    assert [t.turn_index for t in pending] == [3, 4]


def test_parse_turns_requires_list() -> None:
    with pytest.raises(TypeError, match="list"):
        parse_turns({"turn_index": 0})


def test_format_includes_role_tags() -> None:
    text = format_batch_user_content(_turns(1))
    assert 'role="user"' in text


def test_batch_prompt_suffix_present() -> None:
    assert '"turns"' in EXTRACTION_SYSTEM_PROMPT_BATCH
    assert "turn_index" in EXTRACTION_SYSTEM_PROMPT_BATCH


def test_extract_task_routing_and_retry() -> None:
    task = celery_app.tasks[TASK_EXTRACT_SESSION_MEMORIES]
    assert task.queue == "extraction"
    assert task.soft_time_limit == 120
    assert task.time_limit == 180
    assert ExtractionTransportError in task.autoretry_for
    assert task.max_retries == 3


def test_extract_task_requires_org_id() -> None:
    with pytest.raises(ValueError, match="org_id is required"):
        extract_session_memories.run(
            agent_id=str(uuid4()),
            session_id=str(uuid4()),
            turns=[{"turn_index": 0, "role": "user", "content": "hello world xx"}],
        )


def test_extract_task_runs_with_injected_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    from app.extraction.batch import BatchRunResult

    class _Settings:
        memory_base_url = "http://memory.example"
        memory_api_token = SecretStr("tok")
        database_url = None
        clickhouse_dsn = None

    monkeypatch.setattr("app.tasks.extraction.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.tasks.extraction.load_active_extraction_provider", lambda: object())
    monkeypatch.setattr("app.tasks.extraction.HttpMemoryWriter", lambda **_k: object())
    monkeypatch.setattr(
        "app.tasks.extraction.run_batch_extraction",
        lambda **_k: BatchRunResult(2, 1),
    )
    payload = extract_session_memories.run(
        org_id=str(uuid4()),
        agent_id=str(uuid4()),
        session_id=str(uuid4()),
        turns=[{"turn_index": 0, "role": "user", "content": "hello world xx"}],
    )
    assert payload == {
        "status": "ok",
        "memories_written": 2,
        "turns_processed": 1,
        "skipped": None,
    }


def test_extracted_memory_confidence_is_forwarded() -> None:
    mem = ExtractedMemory.model_validate(
        {
            "content": "User prefers dark mode in the IDE",
            "categories": [{"label": "preference", "confidence": 0.4}],
            "confidence": 0.4,
            "valid_from": datetime(2026, 9, 1, tzinfo=UTC),
        }
    )
    assert mem.confidence == 0.4
