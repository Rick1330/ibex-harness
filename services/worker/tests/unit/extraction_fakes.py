"""Shared fakes for extraction batch unit tests."""

from __future__ import annotations

from app.extraction.memory_writer import MemoryWriteRequest
from app.extraction.provider import ExtractionTransportError
from app.extraction.session_store import SessionSnapshot


class IdempotentSlotWriter:
    """Simulates memory Redis: first body per batch-position key wins."""

    def __init__(self, *, fail_on_nth: int | None = None) -> None:
        self.fail_on_nth = fail_on_nth
        self.attempt = 0
        self.slots: dict[tuple[str, int, int], str] = {}
        self.write_attempts: list[tuple[int, int, str]] = []

    def write(self, request: MemoryWriteRequest) -> None:
        self.attempt += 1
        if self.fail_on_nth is not None and self.attempt == self.fail_on_nth:
            raise ExtractionTransportError("memory service HTTP 503")
        key = (request.batch_fingerprint, request.turn_index, request.ordinal)
        self.write_attempts.append(
            (request.turn_index, request.ordinal, request.memory.content)
        )
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
        if self.snapshot is not None:
            self.snapshot = SessionSnapshot(
                last_extracted_turn=self.updated,
                status=self.snapshot.status,
                deleted_at=self.snapshot.deleted_at,
            )
