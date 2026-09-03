"""Shared fakes and job builders for extraction batch unit tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.extraction.batch import BatchJob, TurnPayload
from app.extraction.memory_writer import MemoryWriteRequest
from app.extraction.provider import ExtractionCall, ExtractionTransportError
from app.extraction.session_store import SessionSnapshot

# Matches production identity key fields (org/session/turn/ordinal).
SlotKey = tuple[UUID, UUID, int, int]


class IdempotentSlotWriter:
    """Simulates memory Redis: first body per identity key wins."""

    def __init__(self, *, fail_on_nth: int | None = None) -> None:
        self.fail_on_nth = fail_on_nth
        self.attempt = 0
        self.slots: dict[SlotKey, str] = {}
        self.write_attempts: list[tuple[SlotKey, str]] = []
        self.requests: list[MemoryWriteRequest] = []

    def write(self, request: MemoryWriteRequest) -> None:
        self.attempt += 1
        self.requests.append(request)
        if self.fail_on_nth is not None and self.attempt == self.fail_on_nth:
            raise ExtractionTransportError("memory service HTTP 503")
        key = (request.org_id, request.session_id, request.turn_index, request.ordinal)
        self.write_attempts.append((key, request.memory.content))
        if key not in self.slots:
            self.slots[key] = request.memory.content


class FakeSessionStore:
    def __init__(
        self,
        snapshot: SessionSnapshot | None,
        *,
        fail_updates: int = 0,
    ) -> None:
        self.snapshot = snapshot
        self.updated: int | None = None
        self._fail_updates = fail_updates
        self.update_attempts = 0
        self.update_history: list[int] = []

    def load(self, org_id, session_id) -> SessionSnapshot | None:
        del org_id, session_id
        if self.updated is not None and self.snapshot is not None:
            return SessionSnapshot(
                last_extracted_turn=self.updated,
                status=self.snapshot.status,
                deleted_at=self.snapshot.deleted_at,
            )
        return self.snapshot

    def update_last_extracted_turn(self, org_id, session_id, last_extracted_turn: int) -> None:
        del org_id, session_id
        self.update_attempts += 1
        if self._fail_updates > 0:
            self._fail_updates -= 1
            raise OSError("simulated crash before pointer commit")
        current = self.updated
        if current is None and self.snapshot is not None:
            current = self.snapshot.last_extracted_turn
        elif current is None:
            current = -1
        self.updated = max(last_extracted_turn, current)
        self.update_history.append(self.updated)
        if self.snapshot is not None:
            self.snapshot = SessionSnapshot(
                last_extracted_turn=self.updated,
                status=self.snapshot.status,
                deleted_at=self.snapshot.deleted_at,
            )


class FakeProvider:
    def __init__(
        self,
        *,
        override_indexes: list[int] | None = None,
        raw_json: str | None = None,
        wording_suffixes: list[str] | None = None,
    ) -> None:
        self.override_indexes = override_indexes
        self.raw_json = raw_json
        self.wording_suffixes = wording_suffixes or [""]
        self.last_user = ""
        self.calls = 0

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> tuple[str, ...]:
        return ("gpt-4o-mini",)

    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        self.calls += 1
        self.last_user = user_content
        assert "turns" in system_prompt.lower() or "turn_index" in system_prompt
        body = self.raw_json if self.raw_json is not None else self._build_body(user_content)
        return ExtractionCall(
            raw_json=body,
            model="gpt-4o-mini",
            input_tokens=12,
            output_tokens=34,
            latency_ms=8,
        )

    def _build_body(self, user_content: str) -> str:
        indexes = self.override_indexes
        if indexes is None:
            indexes = [int(m) for m in re.findall(r'index="(\d+)"', user_content)]
        suffix_idx = min(self.calls - 1, len(self.wording_suffixes) - 1)
        suffix = self.wording_suffixes[suffix_idx]
        turns = [
            {
                "turn_index": i,
                "memories": [
                    {
                        "content": (
                            f"Durable preference recorded from turn {i:02d}{suffix}"
                        ),
                        "categories": [{"label": "preference", "confidence": 0.9}],
                        "confidence": 0.91,
                    }
                ],
            }
            for i in indexes
        ]
        return json.dumps({"turns": turns})


class RecordingWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[int, str]] = []
        self.requests: list[MemoryWriteRequest] = []

    def write(self, request: MemoryWriteRequest) -> None:
        self.requests.append(request)
        self.writes.append((request.turn_index, request.memory.content))


@dataclass
class JobParts:
    turns: list[TurnPayload] | None = None
    provider: object | None = None
    writer: object | None = None
    session_store: FakeSessionStore | None = None
    clickhouse_dsn: str | None = None
    org_id: UUID | None = None
    session_id: UUID | None = None


def completed_store(*, last_extracted_turn: int = -1) -> FakeSessionStore:
    return FakeSessionStore(
        SessionSnapshot(
            last_extracted_turn=last_extracted_turn,
            status="completed",
            deleted_at=None,
        )
    )


def sample_turns(n: int) -> list[TurnPayload]:
    return [
        TurnPayload(turn_index=i, role="user", content=f"turn body {i} durable")
        for i in range(n)
    ]


def slot_by_turn(writer: IdempotentSlotWriter, turn_index: int, ordinal: int = 0) -> str:
    matches = [
        content
        for (_org, _session, turn, ord_), content in writer.slots.items()
        if turn == turn_index and ord_ == ordinal
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one slot for turn={turn_index} ordinal={ordinal}")
    return matches[0]


def make_job(parts: JobParts | None = None) -> BatchJob:
    cfg = parts or JobParts()
    return BatchJob(
        org_id=cfg.org_id or uuid4(),
        agent_id=uuid4(),
        session_id=cfg.session_id or uuid4(),
        turns=cfg.turns if cfg.turns is not None else sample_turns(1),
        provider=cfg.provider or FakeProvider(),  # type: ignore[arg-type]
        memory_writer=cfg.writer or RecordingWriter(),  # type: ignore[arg-type]
        clickhouse_dsn=cfg.clickhouse_dsn,
        session_store=cfg.session_store or completed_store(),
    )
