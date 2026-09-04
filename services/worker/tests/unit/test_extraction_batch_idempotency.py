"""Idempotency and per-turn pointer crash windows for batch extraction."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.extraction.batch import run_batch_extraction
from app.extraction.provider import ExtractionTransportError
from app.extraction.session_store import SessionSnapshot
from tests.unit.extraction_fakes import (
    FakeProvider,
    FakeSessionStore,
    IdempotentSlotWriter,
    JobParts,
    completed_store,
    make_job,
    sample_turns,
    slot_by_turn,
)


def test_mid_batch_write_failure_advances_only_completed_turns() -> None:
    """Writer fails mid-batch; pointer reflects only fully completed turns; retry safe."""
    provider = FakeProvider()
    writer = IdempotentSlotWriter(fail_on_nth=3)
    store = completed_store()
    job = make_job(
        JobParts(
            turns=sample_turns(5),
            provider=provider,
            writer=writer,
            session_store=store,
        )
    )
    with pytest.raises(ExtractionTransportError, match="503"):
        run_batch_extraction(job)
    assert provider.calls == 1
    assert store.updated == 1
    assert store.update_history == [0, 1]
    assert len(writer.slots) == 2

    writer.fail_on_nth = None
    result = run_batch_extraction(job)
    assert result.memories_written == 3
    assert result.turns_processed == 3
    assert provider.calls == 2
    assert store.updated == 4
    assert len(writer.slots) == 5
    assert all(
        slot_by_turn(writer, turn).endswith(f"turn {turn:02d}") for turn in range(5)
    )


def test_extract_twice_in_succession_is_noop() -> None:
    provider = FakeProvider()
    writer = IdempotentSlotWriter()
    store = completed_store()
    job = make_job(
        JobParts(
            turns=sample_turns(2),
            provider=provider,
            writer=writer,
            session_store=store,
        )
    )
    first = run_batch_extraction(job)
    slots_after_first = dict(writer.slots)
    pointer_after_first = store.updated
    second = run_batch_extraction(job)
    assert first.memories_written == 2
    assert second.skipped == "no_unprocessed_turns"
    assert second.memories_written == 0
    assert provider.calls == 1
    assert writer.slots == slots_after_first
    assert store.updated == pointer_after_first == 1


def test_crash_after_writes_before_pointer_retry_is_idempotent() -> None:
    """Pointer failure after turn 0 → retry re-extracts pending turns without dup slots."""
    provider = FakeProvider(wording_suffixes=[" wording-a", " wording-b"])
    writer = IdempotentSlotWriter()
    store = FakeSessionStore(
        SessionSnapshot(last_extracted_turn=-1, status="completed", deleted_at=None),
        fail_updates=1,
    )
    job = make_job(
        JobParts(
            turns=sample_turns(3),
            provider=provider,
            writer=writer,
            session_store=store,
        )
    )
    with pytest.raises(ExtractionTransportError, match="session pointer update failed"):
        run_batch_extraction(job)
    assert provider.calls == 1
    assert store.updated is None
    assert len(writer.slots) == 1
    first_content = slot_by_turn(writer, 0)

    result = run_batch_extraction(job)
    assert result.skipped is None
    assert provider.calls == 2
    assert store.updated == 2
    assert len(writer.slots) == 3
    assert slot_by_turn(writer, 0) == first_content
    assert slot_by_turn(writer, 0).endswith("wording-a")
    assert slot_by_turn(writer, 1).endswith("wording-b")
    assert slot_by_turn(writer, 2).endswith("wording-b")


def test_pointer_update_oserror_maps_to_transport_error() -> None:
    store = FakeSessionStore(
        SessionSnapshot(last_extracted_turn=-1, status="completed", deleted_at=None),
        fail_updates=1,
    )
    job = make_job(JobParts(turns=sample_turns(1), session_store=store))
    with pytest.raises(ExtractionTransportError, match="session pointer update failed"):
        run_batch_extraction(job)
    assert store.updated is None
    assert store.update_attempts == 1


def test_idempotent_slots_are_scoped_by_org_and_session() -> None:
    """Same turn+ordinal from different orgs must not collide in the fake writer."""
    writer = IdempotentSlotWriter()
    org_a, org_b = uuid4(), uuid4()
    session_a, session_b = uuid4(), uuid4()
    turns = sample_turns(1)
    run_batch_extraction(
        make_job(
            JobParts(
                turns=turns,
                writer=writer,
                org_id=org_a,
                session_id=session_a,
                session_store=completed_store(),
            )
        )
    )
    run_batch_extraction(
        make_job(
            JobParts(
                turns=turns,
                writer=writer,
                org_id=org_b,
                session_id=session_b,
                session_store=completed_store(),
            )
        )
    )
    assert len(writer.slots) == 2
    keys = set(writer.slots)
    assert (org_a, session_a, 0, 0) in keys
    assert (org_b, session_b, 0, 0) in keys
