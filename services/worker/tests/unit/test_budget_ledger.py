"""Unit tests for the worker budget reservation ledger (GAP-006).

DB-backed behavior lives in tests/integration/test_budget_ledger_postgres.py;
here the async sessions are faked so the core logic is covered without a DSN.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import budget_ledger as mod
from app.budget_ledger import (
    BudgetAdmissionDeniedError,
    BudgetClaim,
    BudgetLedgerClaimClosedError,
    BudgetLedgerError,
    BudgetLedgerUnavailableError,
    PostgresBudgetLedger,
    _Card,
    _decode_card,
    _estimate_cost,
    _PriceRow,
    budget_reservation_key,
    estimate_prompt_tokens,
    fingerprint_extraction_call,
)


class _Result:
    def __init__(
        self,
        row: dict | None = None,
        *,
        scalar: object | None = None,
        rowcount: int = 1,
        all_rows: list | None = None,
    ) -> None:
        self._row = row
        self._scalar = scalar
        self._rowcount = rowcount
        self._all_rows = all_rows or []

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict | None:
        return self._row

    def one(self) -> dict:
        assert self._row is not None
        return self._row

    def scalar_one(self) -> object | None:
        return self._scalar

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def fetchall(self) -> list:
        return self._all_rows


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[object, object]] = []

    async def execute(self, statement: object, params: object = None) -> _Result:
        self.calls.append((statement, params))
        return self.results.pop(0)


class _FailingSession:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def execute(self, statement: object, params: object = None) -> _Result:
        del statement, params
        raise self.error


@pytest.fixture
def org_session(monkeypatch: pytest.MonkeyPatch):
    sessions: list[object] = []

    def install(session: object) -> None:
        sessions.append(session)

        @asynccontextmanager
        async def context(_factory, _org):
            yield session

        monkeypatch.setattr(mod, "session_as_service_org", context)

    return install, sessions


@pytest.fixture
def service_session(monkeypatch: pytest.MonkeyPatch):
    sessions: list[object] = []

    def install(session: object) -> None:
        sessions.append(session)

        @asynccontextmanager
        async def context(_factory):
            yield session

        monkeypatch.setattr(mod, "session_as_service_account", context)

    return install, sessions


_CARD_JSON = json.dumps(
    [
        {
            "provider": "openai",
            "model_pattern": "gpt-4o*",
            "input_cents_per_1k": 10,
            "output_cents_per_1k": 30,
        }
    ]
)


def _period_row(*, cap_cents: int = 10_000, spent_cents: int = 0) -> _Result:
    return _Result(
        {"id": uuid4(), "cap_cents": cap_cents, "spent_cents_cached": spent_cents}
    )


def _card_row() -> _Result:
    return _Result({"version": "3", "prices": _CARD_JSON})


def _claim_kwargs() -> dict:
    return {
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "key": "extraction:00000000-0000-0000-0000-000000000001:3",
        "request_hash": "a" * 64,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "input_tokens": 100,
        "output_tokens": 200,
    }


def _claim_token(**overrides) -> BudgetClaim:
    base = {
        "claim_id": uuid4(),
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "key": "extraction:key",
        "request_hash": "a" * 64,
        "period_id": uuid4(),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "version": 1,
    }
    base.update(overrides)
    return BudgetClaim(**base)


def test_reservation_key_and_fingerprint_stability() -> None:
    session_id = uuid4()
    assert (
        budget_reservation_key(session_id=session_id, first_turn_index=7)
        == f"extraction:{session_id}:7"
    )
    first = fingerprint_extraction_call(
        provider="openai", model="gpt-4o-mini", system_prompt="sys", user_content="body"
    )
    second = fingerprint_extraction_call(
        provider="openai", model="gpt-4o-mini", system_prompt="sys", user_content="body"
    )
    third = fingerprint_extraction_call(
        provider="openai", model="gpt-4o-mini", system_prompt="sys", user_content="body2"
    )
    assert first == second
    assert first != third
    assert len(first) == 64 and first.islower()


def test_token_heuristic_counts_unicode_code_points() -> None:
    input_tokens, output_tokens = estimate_prompt_tokens(
        system_prompt="one two", user_content="\u00e9" * 20
    )
    assert output_tokens == mod.DEFAULT_OUTPUT_TOKENS
    # max(code points, utf-8 bytes / 4) is code points for any valid UTF-8 text.
    assert input_tokens == 7 + mod.TOKENS_PER_MESSAGE + 20 + mod.TOKENS_PER_MESSAGE
    empty_tokens, _ = estimate_prompt_tokens(system_prompt="", user_content="")
    assert empty_tokens == 2 * mod.TOKENS_PER_MESSAGE


def test_decode_card_rejects_non_list_payload() -> None:
    with pytest.raises(BudgetLedgerError):
        _decode_card({"not": "a list"})
    with pytest.raises(BudgetLedgerError):
        _decode_card([1, 2, 3])


def test_estimate_cost_ceils_per_component_and_requires_version() -> None:
    card = _Card(
        version="3",
        prices=(_PriceRow("openai", "gpt-4o*", 10, 30),),
    )
    assert _estimate_cost(card, "OpenAI", "gpt-4o-mini", 100, 200) == 7
    assert _estimate_cost(card, "openai", "gpt-4o-mini", 0, 0) == 0
    assert _estimate_cost(card, "openai", "gpt-4o-mini", 1, 0) == 1
    assert _estimate_cost(card, "openai", "claude-3", 1, 1) is None
    assert _estimate_cost(_Card(version="", prices=card.prices), "openai", "x", 1, 1) is None
    assert _estimate_cost(card, "openai", "gpt-4o-mini", -1, 1) is None
    negative = _Card(version="3", prices=(_PriceRow("openai", "gpt-4o*", -1, 30),))
    assert _estimate_cost(negative, "openai", "gpt-4o-mini", 1, 1) is None


@pytest.mark.asyncio
async def test_claim_returns_none_without_hard_cap(org_session) -> None:
    install, _ = org_session
    session = _Session(_Result(), _Result(None))
    install(session)
    ledger = mod._AsyncBudgetLedger(object())
    assert await ledger.claim(**_claim_kwargs()) is None
    assert len(session.calls) == 2  # advisory lock + period lookup


@pytest.mark.asyncio
async def test_claim_denied_without_rate_card(org_session) -> None:
    install, _ = org_session
    install(_Session(_Result(), _period_row(), _Result({"version": "", "prices": []})))
    ledger = mod._AsyncBudgetLedger(object())
    with pytest.raises(BudgetAdmissionDeniedError) as err:
        await ledger.claim(**_claim_kwargs())
    assert err.value.kind == "no_rate_card"


@pytest.mark.asyncio
async def test_claim_fresh_owned_and_exceeded(org_session) -> None:
    install, _ = org_session
    kwargs = _claim_kwargs()
    claim_id = uuid4()
    install(
        _Session(
            _Result(),
            _period_row(),
            _card_row(),
            _Result(None),
            _Result(None, scalar=0),
            _Result({"id": claim_id, "version": 1}),
        )
    )
    ledger = mod._AsyncBudgetLedger(object(), lease_seconds=30)
    claim = await ledger.claim(**kwargs)
    assert claim is not None
    assert claim.claim_id == claim_id
    assert claim.version == 1
    assert claim.key == kwargs["key"]

    install(
        _Session(
            _Result(),
            _period_row(cap_cents=10, spent_cents=10),
            _card_row(),
            _Result(None),
            _Result(None, scalar=0),
        )
    )
    with pytest.raises(BudgetAdmissionDeniedError) as err:
        await ledger.claim(**kwargs)
    assert err.value.kind == "exceeded"


@pytest.mark.asyncio
async def test_claim_existing_conflict_and_in_progress(org_session) -> None:
    install, _ = org_session
    kwargs = _claim_kwargs()
    install(
        _Session(
            _Result(),
            _period_row(),
            _card_row(),
            _Result(
                {
                    "id": uuid4(),
                    "request_hash": "b" * 64,
                    "state": "claimed",
                    "lease_active": True,
                    "retry_after": 42,
                    "version": 1,
                }
            ),
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    with pytest.raises(BudgetAdmissionDeniedError) as conflict:
        await ledger.claim(**kwargs)
    assert conflict.value.kind == "conflict"

    install(
        _Session(
            _Result(),
            _period_row(),
            _card_row(),
            _Result(
                {
                    "id": uuid4(),
                    "request_hash": kwargs["request_hash"],
                    "state": "claimed",
                    "lease_active": True,
                    "retry_after": 42,
                    "version": 1,
                }
            ),
        )
    )
    with pytest.raises(BudgetAdmissionDeniedError) as in_progress:
        await ledger.claim(**kwargs)
    assert in_progress.value.kind == "in_progress"
    assert in_progress.value.retry_after == 42


@pytest.mark.asyncio
async def test_claim_expired_lease_reclaims_with_cap_check(org_session) -> None:
    install, _ = org_session
    kwargs = _claim_kwargs()
    row = {
        "id": uuid4(),
        "request_hash": kwargs["request_hash"],
        "state": "claimed",
        "lease_active": False,
        "retry_after": 1,
        "version": 4,
    }
    install(
        _Session(
            _Result(),
            _period_row(),
            _card_row(),
            _Result(row),
            _Result(None, scalar=0),
            _Result({"id": row["id"], "version": 5}),
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    claim = await ledger.claim(**kwargs)
    assert claim is not None and claim.version == 5

    install(
        _Session(
            _Result(),
            _period_row(cap_cents=6, spent_cents=0),
            _card_row(),
            _Result(row),
            _Result(None, scalar=0),
            _Result(rowcount=1),
        )
    )
    with pytest.raises(BudgetAdmissionDeniedError) as err:
        await ledger.claim(**kwargs)
    assert err.value.kind == "exceeded"


@pytest.mark.asyncio
async def test_claim_wraps_sqlalchemy_errors(org_session) -> None:
    install, _ = org_session
    install(_FailingSession(SQLAlchemyError("down")))
    ledger = mod._AsyncBudgetLedger(object())
    with pytest.raises(BudgetLedgerUnavailableError):
        await ledger.claim(**_claim_kwargs())


@pytest.mark.asyncio
async def test_claim_rejects_invalid_key(org_session) -> None:
    ledger = mod._AsyncBudgetLedger(object())
    for key, request_hash in (("", "hash"), ("x" * 257, "hash"), ("key", "")):
        with pytest.raises(BudgetLedgerError, match="invalid"):
            await ledger.claim(**_claim_kwargs() | {"key": key, "request_hash": request_hash})


@pytest.mark.asyncio
async def test_finalize_measured_complete(org_session) -> None:
    install, _ = org_session
    claim = _claim_token()
    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "claimed",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": None,
                    "finalized_completeness": None,
                    "version": claim.version,
                }
            ),
            _card_row(),
            _Result(rowcount=1),
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    completeness = await ledger.finalize(claim, input_tokens=100, output_tokens=200)
    assert completeness == mod.COMPLETENESS_COMPLETE


@pytest.mark.asyncio
async def test_finalize_falls_back_to_estimate_and_replays(org_session) -> None:
    install, _ = org_session
    claim = _claim_token()
    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "claimed",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": None,
                    "finalized_completeness": None,
                    "version": claim.version,
                }
            ),
            _card_row(),
            _Result(rowcount=1),
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    assert (
        await ledger.finalize(claim, input_tokens=0, output_tokens=0)
        == mod.COMPLETENESS_ESTIMATED
    )

    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "finalized",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": 5,
                    "finalized_completeness": mod.COMPLETENESS_ESTIMATED,
                    "version": claim.version + 1,
                }
            ),
            _card_row(),
        )
    )
    assert (
        await ledger.finalize(claim, input_tokens=0, output_tokens=0)
        == mod.COMPLETENESS_ESTIMATED
    )

    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "finalized",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": 9,
                    "finalized_completeness": mod.COMPLETENESS_COMPLETE,
                    "version": claim.version + 1,
                }
            ),
            _card_row(),
        )
    )
    with pytest.raises(BudgetLedgerClaimClosedError):
        await ledger.finalize(claim, input_tokens=0, output_tokens=0)


@pytest.mark.asyncio
async def test_finalize_closed_on_stale_version_or_missing_row(org_session) -> None:
    install, _ = org_session
    claim = _claim_token()
    install(_Session(_Result(None)))
    ledger = mod._AsyncBudgetLedger(object())
    with pytest.raises(BudgetLedgerClaimClosedError):
        await ledger.finalize(claim, input_tokens=1, output_tokens=1)

    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "claimed",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": None,
                    "finalized_completeness": None,
                    "version": claim.version + 5,
                }
            ),
            _card_row(),
        )
    )
    with pytest.raises(BudgetLedgerClaimClosedError):
        await ledger.finalize(claim, input_tokens=1, output_tokens=1)


@pytest.mark.asyncio
async def test_release_idempotent_and_closed(org_session) -> None:
    install, _ = org_session
    claim = _claim_token()
    release_row = {
        "id": claim.claim_id,
        "state": "released",
        "amount_estimated_cents": 5,
        "amount_final_cents": None,
        "finalized_completeness": None,
        "version": claim.version + 1,
    }
    install(_Session(_Result(release_row)))
    ledger = mod._AsyncBudgetLedger(object())
    await ledger.release(claim)

    install(_Session(_Result(release_row | {"state": "finalized"})))
    with pytest.raises(BudgetLedgerClaimClosedError):
        await ledger.release(claim)

    install(_Session(_Result(None)))
    with pytest.raises(BudgetLedgerClaimClosedError):
        await ledger.release(claim)


@pytest.mark.asyncio
async def test_release_transitions_claimed_row(org_session) -> None:
    install, _ = org_session
    claim = _claim_token()
    install(
        _Session(
            _Result(
                {
                    "id": claim.claim_id,
                    "state": "claimed",
                    "amount_estimated_cents": 5,
                    "amount_final_cents": None,
                    "finalized_completeness": None,
                    "version": claim.version,
                }
            ),
            _Result(rowcount=1),
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    await ledger.release(claim)


@pytest.mark.asyncio
async def test_expire_stale_service_account_and_validation(service_session) -> None:
    install, _ = service_session
    install(_Session(_Result(all_rows=[uuid4(), uuid4()])))
    ledger = mod._AsyncBudgetLedger(object())
    assert await ledger.expire_stale(grace_seconds=3600, batch_limit=500) == 2

    with pytest.raises(BudgetLedgerError):
        await ledger.expire_stale(grace_seconds=-1, batch_limit=500)
    with pytest.raises(BudgetLedgerError):
        await ledger.expire_stale(grace_seconds=1, batch_limit=0)

    install(_FailingSession(SQLAlchemyError("down")))
    with pytest.raises(BudgetLedgerUnavailableError):
        await ledger.expire_stale(grace_seconds=1, batch_limit=1)


@pytest.mark.asyncio
async def test_ping_probes_service_account_privileges(service_session) -> None:
    install, _ = service_session
    install(
        _Session(
            _Result(
                {
                    "table_exists": True,
                    "can_select": True,
                    "can_insert": True,
                    "can_update": True,
                }
            )
        )
    )
    ledger = mod._AsyncBudgetLedger(object())
    await ledger.ping()

    install(
        _Session(
            _Result(
                {
                    "table_exists": False,
                    "can_select": False,
                    "can_insert": False,
                    "can_update": False,
                }
            )
        )
    )
    with pytest.raises(BudgetLedgerError, match="not ready"):
        await ledger.ping()


class _StubCore:
    def __init__(self) -> None:
        self.claim_result: object = None
        self.finalize_result = mod.COMPLETENESS_COMPLETE
        self.expired = 3
        self.calls: list[str] = []

    async def ping(self) -> None:
        self.calls.append("ping")

    async def claim(self, **kwargs: object) -> object:
        self.calls.append("claim")
        return self.claim_result

    async def finalize(self, claim: BudgetClaim, **kwargs: object) -> str:
        self.calls.append("finalize")
        return self.finalize_result

    async def release(self, claim: BudgetClaim) -> None:
        self.calls.append("release")

    async def expire_stale(self, **kwargs: object) -> int:
        self.calls.append("expire_stale")
        return self.expired


def test_sync_facade_delegates_to_core() -> None:
    facade = PostgresBudgetLedger(object())  # type: ignore[arg-type]
    stub = _StubCore()
    facade._core = stub  # type: ignore[assignment]
    claim = _claim_token()
    stub.claim_result = claim

    facade.ping()
    assert facade.claim(**_claim_kwargs()) is claim
    assert facade.finalize(claim, input_tokens=1, output_tokens=1) == (
        mod.COMPLETENESS_COMPLETE
    )
    facade.release(claim)
    assert facade.expire_stale(grace_seconds=1, batch_limit=10) == 3
    assert stub.calls == ["ping", "claim", "finalize", "release", "expire_stale"]


def test_claim_token_carries_provider_model() -> None:
    claim = _claim_token()
    assert isinstance(claim.org_id, UUID)
    assert claim.provider == "openai"
    assert claim.version == 1
