"""Budget admission wiring tests for the extraction batch (GAP-006)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.budget_ledger import (
    BudgetAdmissionDeniedError,
    BudgetClaim,
    BudgetLedgerError,
    BudgetLedgerUnavailableError,
    budget_reservation_key,
    estimate_prompt_tokens,
    fingerprint_extraction_call,
)
from app.extraction.batch import (
    format_batch_user_content,
    run_batch_extraction,
)
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from app.extraction.provider import ExtractionCall, ExtractionTransportError
from tests.unit.extraction_fakes import (
    FakeProvider,
    JobParts,
    RecordingWriter,
    completed_store,
    make_job,
    sample_turns,
)


class FakeBudgetLedger:
    def __init__(
        self,
        *,
        claim_result: BudgetClaim | None = None,
        claim_error: Exception | None = None,
        finalize_error: Exception | None = None,
        release_error: Exception | None = None,
    ) -> None:
        self.claim_result = claim_result
        self.claim_error = claim_error
        self.finalize_error = finalize_error
        self.release_error = release_error
        self.claim_calls: list[dict[str, Any]] = []
        self.finalize_calls: list[tuple[BudgetClaim, int, int]] = []
        self.released: list[BudgetClaim] = []

    def claim(self, **kwargs: Any) -> BudgetClaim | None:
        self.claim_calls.append(kwargs)
        if self.claim_error is not None:
            raise self.claim_error
        return self.claim_result

    def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str:
        if self.finalize_error is not None:
            raise self.finalize_error
        self.finalize_calls.append((claim, input_tokens, output_tokens))
        return "complete"

    def release(self, claim: BudgetClaim) -> None:
        if self.release_error is not None:
            raise self.release_error
        self.released.append(claim)


class FailingProvider(FakeProvider):
    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        del system_prompt, user_content
        raise ExtractionTransportError("provider down")


def _claim_token(*, org_id: UUID, agent_id: UUID, key: str, request_hash: str) -> BudgetClaim:
    return BudgetClaim(
        claim_id=uuid4(),
        org_id=org_id,
        agent_id=agent_id,
        key=key,
        request_hash=request_hash,
        period_id=uuid4(),
        provider="openai",
        model="gpt-4o-mini",
        version=1,
    )


def _expected_hash(turns: list) -> str:
    return fingerprint_extraction_call(
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=EXTRACTION_SYSTEM_PROMPT_BATCH,
        user_content=format_batch_user_content(turns),
    )


def test_no_ledger_wired_skips_admission() -> None:
    provider = FakeProvider()
    job = make_job(JobParts(provider=provider))
    result = run_batch_extraction(job)
    assert result.skipped is None
    assert provider.calls == 1


def test_no_hard_cap_claim_none_still_extracts() -> None:
    ledger = FakeBudgetLedger(claim_result=None)
    job = make_job(JobParts(budget_ledger=ledger))
    result = run_batch_extraction(job)
    assert result.skipped is None
    assert len(ledger.claim_calls) == 1
    assert ledger.finalize_calls == []
    assert ledger.released == []


def test_owned_claim_settles_with_measured_usage() -> None:
    turns = sample_turns(3)
    session_id = uuid4()
    key = budget_reservation_key(session_id=session_id, first_turn_index=0)
    expected_hash = _expected_hash(turns)
    ledger = FakeBudgetLedger(
        claim_result=_claim_token(
            org_id=uuid4(), agent_id=uuid4(), key=key, request_hash=expected_hash
        )
    )
    job = make_job(
        JobParts(
            turns=turns,
            provider=FakeProvider(),
            session_id=session_id,
            writer=RecordingWriter(),
            budget_ledger=ledger,
        )
    )
    result = run_batch_extraction(job)
    assert result.skipped is None
    (claim_call,) = ledger.claim_calls
    assert claim_call["org_id"] == job.org_id
    assert claim_call["agent_id"] == job.agent_id
    assert claim_call["key"] == key
    assert claim_call["request_hash"] == expected_hash
    assert claim_call["provider"] == "openai"
    assert claim_call["model"] == "gpt-4o-mini"
    expected_tokens = estimate_prompt_tokens(
        system_prompt=EXTRACTION_SYSTEM_PROMPT_BATCH,
        user_content=format_batch_user_content(turns),
    )
    assert (
        claim_call["input_tokens"],
        claim_call["output_tokens"],
    ) == expected_tokens
    assert len(ledger.finalize_calls) == 1
    _, input_tokens, output_tokens = ledger.finalize_calls[0]
    assert (input_tokens, output_tokens) == (12, 34)
    assert ledger.released == []


def test_transport_failure_releases_claim() -> None:
    ledger = FakeBudgetLedger(
        claim_result=_claim_token(
            org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="h" * 64
        )
    )
    job = make_job(JobParts(provider=FailingProvider(), budget_ledger=ledger))
    with pytest.raises(ExtractionTransportError, match="provider down"):
        run_batch_extraction(job)
    assert len(ledger.released) == 1
    assert ledger.finalize_calls == []


def test_denied_admission_blocks_provider_call() -> None:
    provider = FakeProvider()
    ledger = FakeBudgetLedger(claim_error=BudgetAdmissionDeniedError("exceeded"))
    job = make_job(JobParts(provider=provider, budget_ledger=ledger))
    with pytest.raises(BudgetAdmissionDeniedError):
        run_batch_extraction(job)
    assert provider.calls == 0
    assert ledger.released == []


def test_unavailable_ledger_is_retryable() -> None:
    provider = FakeProvider()
    ledger = FakeBudgetLedger(
        claim_error=BudgetLedgerUnavailableError("database down")
    )
    job = make_job(JobParts(provider=provider, budget_ledger=ledger))
    with pytest.raises(ExtractionTransportError, match="budget admission unavailable"):
        run_batch_extraction(job)
    assert provider.calls == 0


def test_settle_failure_does_not_lose_extraction() -> None:
    ledger = FakeBudgetLedger(
        claim_result=_claim_token(
            org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="h" * 64
        ),
        finalize_error=BudgetLedgerError("settle failed"),
    )
    writer = RecordingWriter()
    job = make_job(JobParts(budget_ledger=ledger, writer=writer))
    result = run_batch_extraction(job)
    assert result.skipped is None
    assert result.memories_written == 1
    assert ledger.finalize_calls == []


def test_release_failure_keeps_original_transport_error() -> None:
    ledger = FakeBudgetLedger(
        claim_result=_claim_token(
            org_id=uuid4(), agent_id=uuid4(), key="k", request_hash="h" * 64
        ),
        release_error=BudgetLedgerError("release failed"),
    )
    job = make_job(JobParts(provider=FailingProvider(), budget_ledger=ledger))
    with pytest.raises(ExtractionTransportError, match="provider down"):
        run_batch_extraction(job)
    assert ledger.released == []


def test_skipped_batch_never_claims() -> None:
    ledger = FakeBudgetLedger()
    job = make_job(
        JobParts(
            turns=[],
            budget_ledger=ledger,
            session_store=completed_store(last_extracted_turn=99),
        )
    )
    result = run_batch_extraction(job)
    assert result.skipped == "no_unprocessed_turns"
    assert ledger.claim_calls == []
