"""Durable budget reservation ledger adapter for worker extraction (GAP-006).

Mirrors ``packages/budgetledger`` (Go) semantics: a claim is written before a
provider call only when the organization has an active ``hard_cap`` budget
period, finalized with measured usage (or the frozen estimate when the provider
reports no usage), and released when the provider call never happened.

Prices are matched once at claim time and stored on the row; settlement uses
those stored rates so publishing a new rate card cannot change (or break the
replay of) an in-flight charge.

Known limitation (documented, follow-up): extraction usage is not exported to
``ibex.usage_facts`` yet, so completed extraction spend is not reflected in
``spent_cents_cached``. Worker holds bound concurrent in-flight spend against
the cap; the durable rows keep the audit record for the eventual export.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.budget_pricing import (
    BYTES_PER_TOKEN,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_ESTIMATED,
    DEFAULT_OUTPUT_TOKENS,
    TOKENS_PER_MESSAGE,
    _Card,
    _estimate_cost,
    _match_price,
    _PriceRow,
    budget_reservation_key,
    cost_from_rates,
    estimate_prompt_tokens,
    fingerprint_extraction_call,
)
from app.db import session_as_service_account, session_as_service_org
from app.extraction.session_store import _run_coro

BUDGET_LEDGER_LEASE_SECONDS = 900.0
_CLAIM_CLOSED_MSG = "claim is no longer owned"

__all__ = [
    "BUDGET_LEDGER_LEASE_SECONDS",
    "BYTES_PER_TOKEN",
    "COMPLETENESS_COMPLETE",
    "COMPLETENESS_ESTIMATED",
    "DEFAULT_OUTPUT_TOKENS",
    "TOKENS_PER_MESSAGE",
    "BudgetAdmissionDeniedError",
    "BudgetClaim",
    "BudgetClaimRequest",
    "BudgetLedger",
    "BudgetLedgerClaimClosedError",
    "BudgetLedgerError",
    "BudgetLedgerUnavailableError",
    "PostgresBudgetLedger",
    "budget_reservation_key",
    "estimate_prompt_tokens",
    "fingerprint_extraction_call",
]


class BudgetLedgerError(RuntimeError):
    """Permanent admission or settlement failure (fail closed, no retry)."""


class BudgetLedgerUnavailableError(BudgetLedgerError):
    """Transient database failure while talking to the ledger (safe to retry)."""


class BudgetLedgerClaimClosedError(BudgetLedgerError):
    """A stale owner attempted to finalize or release a claim."""


class BudgetAdmissionDeniedError(BudgetLedgerError):
    """Admission refused: exceeded cap, competing owner, or unusable rate card."""

    def __init__(self, kind: str, *, retry_after: int | None = None) -> None:
        super().__init__(f"budget admission denied: {kind}")
        self.kind = kind
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class BudgetClaimRequest:
    """Inputs for one admission attempt (extraction call fingerprint + estimate)."""

    org_id: UUID
    agent_id: UUID
    key: str
    request_hash: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class BudgetClaim:
    claim_id: UUID
    org_id: UUID
    agent_id: UUID
    key: str
    request_hash: str
    period_id: UUID
    provider: str
    model: str
    version: int


@dataclass(frozen=True, slots=True)
class _Admission:
    request: BudgetClaimRequest
    period_id: UUID
    cap_cents: int
    spent_cents: int
    estimated_cents: int
    price_input_cents_per_1k: int
    price_output_cents_per_1k: int
    lease: timedelta


@dataclass(frozen=True, slots=True)
class _RowRef:
    id: UUID
    version: int
    org_id: UUID
    agent_id: UUID
    key: str


class BudgetLedger(Protocol):
    """Synchronous ledger facade used by the extraction batch orchestration."""

    def claim(self, request: BudgetClaimRequest) -> BudgetClaim | None: ...

    def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str: ...

    def release(self, claim: BudgetClaim) -> None: ...


_ADVISORY_LOCK_SQL = """
    SELECT pg_advisory_xact_lock(
        hashtext('budget-reservation:' || CAST(:org_id AS text))
    )
"""

_LOAD_PERIOD_SQL = """
    SELECT id, cap_cents, spent_cents_cached
    FROM ibex_billing.budget_periods
    WHERE org_id = :org_id
      AND period_start <= NOW()
      AND period_end > NOW()
      AND enforcement_mode = 'hard_cap'
    ORDER BY period_start DESC
    LIMIT 1
"""

_LOAD_CARD_SQL = """
    WITH current_card AS (
        SELECT id
        FROM ibex_billing.rate_cards
        WHERE org_id = :org_id AND status = 'published'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    )
    SELECT v.version, v.prices
    FROM ibex_billing.rate_card_versions v
    JOIN current_card c ON c.id = v.rate_card_id
    WHERE v.org_id = :org_id
    ORDER BY v.published_at DESC, v.id DESC
    LIMIT 1
"""

_LOCK_ROW_SQL = """
    SELECT id, request_hash, state,
           lease_expires_at > NOW() AS lease_active,
           GREATEST(
               1,
               CEIL(EXTRACT(EPOCH FROM (lease_expires_at - NOW())))
           )::int AS retry_after,
           version
    FROM ibex_core.budget_reservations
    WHERE organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key
    FOR UPDATE
"""

_INSERT_SQL = """
    INSERT INTO ibex_core.budget_reservations
        (organization_id, agent_id, budget_period_id, reservation_key,
         request_hash, state, amount_estimated_cents,
         price_input_cents_per_1k, price_output_cents_per_1k, lease_expires_at)
    VALUES (:org_id, :agent_id, :period_id, :key, :request_hash,
            'claimed', :estimated_cents,
            :price_input_cents_per_1k, :price_output_cents_per_1k,
            NOW() + CAST(:lease AS interval))
    ON CONFLICT (organization_id, agent_id, reservation_key) DO NOTHING
    RETURNING id, version
"""

_RESET_SQL = """
    UPDATE ibex_core.budget_reservations
    SET state = 'claimed',
        budget_period_id = :period_id,
        request_hash = :request_hash,
        amount_estimated_cents = :estimated_cents,
        price_input_cents_per_1k = :price_input_cents_per_1k,
        price_output_cents_per_1k = :price_output_cents_per_1k,
        amount_final_cents = NULL,
        finalized_completeness = NULL,
        lease_expires_at = NOW() + CAST(:lease AS interval),
        version = version + 1,
        updated_at = NOW()
    WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key AND version = :version
      AND (state <> 'claimed' OR lease_expires_at <= NOW())
    RETURNING id, version
"""

_EXPIRE_ROW_SQL = """
    UPDATE ibex_core.budget_reservations
    SET state = 'expired', lease_expires_at = NULL,
        version = version + 1, updated_at = NOW()
    WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key AND state = 'claimed' AND version = :version
"""

_ACTIVE_HOLDS_SQL = """
    SELECT COALESCE(SUM(amount_estimated_cents), 0) AS active_holds
    FROM ibex_core.budget_reservations
    WHERE organization_id = :org_id AND budget_period_id = :period_id
      AND state = 'claimed' AND lease_expires_at > NOW()
      AND id IS DISTINCT FROM CAST(:exclude_id AS uuid)
"""

_LOAD_CLAIM_SQL = """
    SELECT id, state, amount_estimated_cents, amount_final_cents,
           finalized_completeness, version,
           price_input_cents_per_1k, price_output_cents_per_1k
    FROM ibex_core.budget_reservations
    WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key
    FOR UPDATE
"""

_FINALIZE_SQL = """
    UPDATE ibex_core.budget_reservations
    SET state = 'finalized',
        amount_final_cents = :amount,
        finalized_completeness = :completeness,
        lease_expires_at = NULL,
        version = version + 1,
        updated_at = NOW()
    WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key AND request_hash = :request_hash
      AND version = :version AND state = 'claimed'
    RETURNING id
"""

_RELEASE_SQL = """
    UPDATE ibex_core.budget_reservations
    SET state = 'released', lease_expires_at = NULL,
        version = version + 1, updated_at = NOW()
    WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
      AND reservation_key = :key AND request_hash = :request_hash
      AND version = :version AND state = 'claimed'
    RETURNING id
"""

_EXPIRE_STALE_SQL = """
    WITH stale AS (
        SELECT id, version
        FROM ibex_core.budget_reservations
        WHERE state = 'claimed'
          AND lease_expires_at <= NOW() - CAST(:grace AS interval)
        ORDER BY lease_expires_at
        LIMIT :batch_limit
    )
    UPDATE ibex_core.budget_reservations r
    SET state = 'expired', lease_expires_at = NULL,
        version = r.version + 1, updated_at = NOW()
    FROM stale
    WHERE r.id = stale.id
      AND r.state = 'claimed'
      AND r.version = stale.version
      AND r.lease_expires_at <= NOW() - CAST(:grace AS interval)
    RETURNING r.id
"""


def _decode_card(prices_json: Any) -> tuple[_PriceRow, ...]:
    if prices_json is None:
        return ()
    if isinstance(prices_json, (str, bytes)):
        prices_json = json.loads(prices_json)
    if not isinstance(prices_json, list):
        raise BudgetLedgerError("rate card prices payload is not a list")
    rows: list[_PriceRow] = []
    for raw in prices_json:
        rows.append(_decode_price_row(raw))
    return tuple(rows)


def _decode_price_row(raw: Any) -> _PriceRow:
    if not isinstance(raw, dict):
        raise BudgetLedgerError("rate card price row is not an object")
    return _PriceRow(
        provider=str(raw.get("provider") or ""),
        model_pattern=str(raw.get("model_pattern") or ""),
        input_cents_per_1k=int(raw.get("input_cents_per_1k") or 0),
        output_cents_per_1k=int(raw.get("output_cents_per_1k") or 0),
    )


def _claim_closed() -> BudgetLedgerClaimClosedError:
    return BudgetLedgerClaimClosedError(_CLAIM_CLOSED_MSG)


def _validate_claim(request: BudgetClaimRequest) -> None:
    if not request.key or len(request.key) > 256:
        raise BudgetLedgerError("invalid budget claim")
    if not request.request_hash:
        raise BudgetLedgerError("invalid budget claim")


def _ensure_reusable(row: Any, request: BudgetClaimRequest) -> None:
    if row["request_hash"] != request.request_hash:
        raise BudgetAdmissionDeniedError("conflict")
    if row["state"] == "claimed" and row["lease_active"]:
        raise BudgetAdmissionDeniedError("in_progress", retry_after=int(row["retry_after"]))


def _stale_ref(row: Any, admission: _Admission) -> _RowRef:
    request = admission.request
    return _RowRef(
        id=row["id"],
        version=int(row["version"]),
        org_id=request.org_id,
        agent_id=request.agent_id,
        key=request.key,
    )


def _claim_from_row(row: Any, admission: _Admission) -> BudgetClaim:
    request = admission.request
    return BudgetClaim(
        claim_id=row["id"],
        org_id=request.org_id,
        agent_id=request.agent_id,
        key=request.key,
        request_hash=request.request_hash,
        period_id=admission.period_id,
        provider=request.provider,
        model=request.model,
        version=int(row["version"]),
    )


def _claim_params(claim: BudgetClaim) -> dict[str, Any]:
    return {
        "id": claim.claim_id,
        "org_id": claim.org_id,
        "agent_id": claim.agent_id,
        "key": claim.key,
        "request_hash": claim.request_hash,
        "version": claim.version,
    }


class _AsyncBudgetLedger:
    """Async core; the public facade wraps it with ``_run_coro`` (Celery)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_seconds: float = BUDGET_LEDGER_LEASE_SECONDS,
    ) -> None:
        self._factory = session_factory
        self._lease_seconds = max(1.0, lease_seconds)

    async def ping(self) -> None:
        async with session_as_service_account(self._factory) as session:
            result = await session.execute(
                text(
                    """
                    SELECT to_regclass('ibex_core.budget_reservations') IS NOT NULL AS table_exists,
                           has_table_privilege(current_user, 'ibex_core.budget_reservations', 'SELECT') AS can_select,
                           has_table_privilege(current_user, 'ibex_core.budget_reservations', 'INSERT') AS can_insert,
                           has_table_privilege(current_user, 'ibex_core.budget_reservations', 'UPDATE') AS can_update
                    """
                )  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            )
            probe = result.mappings().one()
            if not all(probe.values()):
                raise BudgetLedgerError("budget reservation ledger is not ready")

    async def claim(self, request: BudgetClaimRequest) -> BudgetClaim | None:
        _validate_claim(request)
        try:
            async with session_as_service_org(self._factory, str(request.org_id)) as session:
                await session.execute(text(_ADVISORY_LOCK_SQL), {"org_id": str(request.org_id)})
                period = await self._load_active_period(session, request.org_id)
                if period is None:
                    return None
                admission = await self._build_admission(session, request, period)
                return await self._claim_row(session, admission)
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger claim failed") from exc

    async def _build_admission(
        self, session: AsyncSession, request: BudgetClaimRequest, period: Any
    ) -> _Admission:
        card = await self._load_card(session, request.org_id)
        price = _match_price(card.prices, request.provider, request.model)
        estimated = _estimate_cost(
            card, request.provider, request.model, request.input_tokens, request.output_tokens
        )
        if price is None or estimated is None:
            raise BudgetAdmissionDeniedError("no_rate_card")
        return _Admission(
            request=request,
            period_id=period["id"],
            cap_cents=int(period["cap_cents"]),
            spent_cents=int(period["spent_cents_cached"]),
            estimated_cents=estimated,
            price_input_cents_per_1k=price.input_cents_per_1k,
            price_output_cents_per_1k=price.output_cents_per_1k,
            lease=timedelta(seconds=self._lease_seconds),
        )

    async def _load_active_period(self, session: AsyncSession, org_id: UUID) -> Any:
        result = await session.execute(text(_LOAD_PERIOD_SQL), {"org_id": org_id})
        return result.mappings().first()

    async def _load_card(self, session: AsyncSession, org_id: UUID) -> _Card:
        result = await session.execute(text(_LOAD_CARD_SQL), {"org_id": org_id})
        row = result.mappings().first()
        if row is None:
            return _Card(version="", prices=())
        return _Card(version=str(row["version"]), prices=_decode_card(row["prices"]))

    async def _claim_row(self, session: AsyncSession, admission: _Admission) -> BudgetClaim:
        row = await self._lock_row(session, admission)
        if row is None:
            return await self._insert_row(session, admission)
        _ensure_reusable(row, admission.request)
        holds = await self._active_holds(
            session,
            org_id=admission.request.org_id,
            period_id=admission.period_id,
            exclude_id=row["id"],
        )
        if admission.spent_cents + holds + admission.estimated_cents > admission.cap_cents:
            if row["state"] == "claimed":
                await self._expire_stale_row(session, _stale_ref(row, admission))
            raise BudgetAdmissionDeniedError("exceeded")
        return await self._reset_row(session, row=row, admission=admission)

    async def _lock_row(self, session: AsyncSession, admission: _Admission) -> Any:
        request = admission.request
        result = await session.execute(
            text(_LOCK_ROW_SQL),
            {"org_id": request.org_id, "agent_id": request.agent_id, "key": request.key},
        )
        return result.mappings().first()

    async def _insert_row(self, session: AsyncSession, admission: _Admission) -> BudgetClaim:
        request = admission.request
        holds = await self._active_holds(
            session, org_id=request.org_id, period_id=admission.period_id, exclude_id=None
        )
        if admission.spent_cents + holds + admission.estimated_cents > admission.cap_cents:
            raise BudgetAdmissionDeniedError("exceeded")
        result = await session.execute(
            text(_INSERT_SQL),
            {
                "org_id": request.org_id,
                "agent_id": request.agent_id,
                "period_id": admission.period_id,
                "key": request.key,
                "request_hash": request.request_hash,
                "estimated_cents": admission.estimated_cents,
                "price_input_cents_per_1k": admission.price_input_cents_per_1k,
                "price_output_cents_per_1k": admission.price_output_cents_per_1k,
                "lease": admission.lease,
            },
        )
        inserted = result.mappings().first()
        if inserted is None:
            raise BudgetAdmissionDeniedError("in_progress", retry_after=1)
        return _claim_from_row(inserted, admission)

    async def _reset_row(
        self, session: AsyncSession, *, row: Any, admission: _Admission
    ) -> BudgetClaim:
        request = admission.request
        result = await session.execute(
            text(_RESET_SQL),
            {
                "id": row["id"],
                "org_id": request.org_id,
                "agent_id": request.agent_id,
                "key": request.key,
                "version": int(row["version"]),
                "period_id": admission.period_id,
                "request_hash": request.request_hash,
                "estimated_cents": admission.estimated_cents,
                "price_input_cents_per_1k": admission.price_input_cents_per_1k,
                "price_output_cents_per_1k": admission.price_output_cents_per_1k,
                "lease": admission.lease,
            },
        )
        updated = result.mappings().first()
        if updated is None:
            raise BudgetLedgerError("budgetledger: reset reservation failed")
        return _claim_from_row(updated, admission)

    async def _expire_stale_row(self, session: AsyncSession, ref: _RowRef) -> None:
        await session.execute(
            text(_EXPIRE_ROW_SQL),
            {
                "id": ref.id,
                "org_id": ref.org_id,
                "agent_id": ref.agent_id,
                "key": ref.key,
                "version": ref.version,
            },
        )

    async def _active_holds(
        self, session: AsyncSession, *, org_id: UUID, period_id: UUID, exclude_id: Any
    ) -> int:
        result = await session.execute(
            text(_ACTIVE_HOLDS_SQL),
            {"org_id": org_id, "period_id": period_id, "exclude_id": exclude_id},
        )
        return int(result.scalar_one())

    async def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str:
        try:
            async with session_as_service_org(self._factory, str(claim.org_id)) as session:
                row = await self._load_claim_row(session, claim)
                if row is None:
                    raise _claim_closed()
                amount, completeness = self._settle_amount(
                    row, input_tokens=input_tokens, output_tokens=output_tokens
                )
                if row["state"] == "finalized":
                    return _replay_finalized(row, claim, amount=amount, completeness=completeness)
                if row["state"] != "claimed" or int(row["version"]) != claim.version:
                    raise _claim_closed()
                await _write_finalized(session, claim, amount=amount, completeness=completeness)
                return completeness
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger finalize failed") from exc

    def _settle_amount(
        self, row: Any, *, input_tokens: int, output_tokens: int
    ) -> tuple[int, str]:
        rates = _stored_rates(row)
        if rates is not None and input_tokens + output_tokens > 0:
            measured = cost_from_rates(
                input_cents_per_1k=rates[0],
                output_cents_per_1k=rates[1],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            if measured is not None:
                return measured, COMPLETENESS_COMPLETE
        return int(row["amount_estimated_cents"]), COMPLETENESS_ESTIMATED

    async def release(self, claim: BudgetClaim) -> None:
        try:
            async with session_as_service_org(self._factory, str(claim.org_id)) as session:
                row = await self._load_claim_row(session, claim)
                if row is None:
                    raise _claim_closed()
                if row["state"] == "released":
                    _verify_release_replay(row, claim)
                    return
                if row["state"] != "claimed" or int(row["version"]) != claim.version:
                    raise _claim_closed()
                await _write_released(session, claim)
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger release failed") from exc

    async def _load_claim_row(self, session: AsyncSession, claim: BudgetClaim) -> Any:
        result = await session.execute(
            text(_LOAD_CLAIM_SQL),
            {
                "id": claim.claim_id,
                "org_id": claim.org_id,
                "agent_id": claim.agent_id,
                "key": claim.key,
            },
        )
        return result.mappings().first()

    async def expire_stale(self, *, grace_seconds: int, batch_limit: int) -> int:
        _validate_sweep(grace_seconds, batch_limit)
        try:
            async with session_as_service_account(self._factory) as session:
                result = await session.execute(
                    text(_EXPIRE_STALE_SQL),
                    {"grace": timedelta(seconds=grace_seconds), "batch_limit": batch_limit},
                )
                return len(result.fetchall())
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger sweep failed") from exc


def _stored_rates(row: Any) -> tuple[int, int] | None:
    input_cents = row["price_input_cents_per_1k"]
    output_cents = row["price_output_cents_per_1k"]
    if input_cents is None or output_cents is None:
        return None
    return int(input_cents), int(output_cents)


def _validate_sweep(grace_seconds: int, batch_limit: int) -> None:
    if grace_seconds < 0:
        raise BudgetLedgerError("invalid reaper grace")
    if batch_limit <= 0:
        raise BudgetLedgerError("invalid reaper batch limit")


def _replay_finalized(row: Any, claim: BudgetClaim, *, amount: int, completeness: str) -> str:
    version_ok = int(row["version"]) == claim.version + 1
    amount_ok = int(row["amount_final_cents"]) == amount
    if version_ok and amount_ok and row["finalized_completeness"] == completeness:
        return completeness
    raise _claim_closed()


def _verify_release_replay(row: Any, claim: BudgetClaim) -> None:
    if int(row["version"]) != claim.version + 1:
        raise _claim_closed()


async def _write_finalized(
    session: AsyncSession, claim: BudgetClaim, *, amount: int, completeness: str
) -> None:
    result = await session.execute(
        text(_FINALIZE_SQL),
        _claim_params(claim) | {"amount": amount, "completeness": completeness},
    )
    if result.rowcount != 1:
        raise _claim_closed()


async def _write_released(session: AsyncSession, claim: BudgetClaim) -> None:
    result = await session.execute(text(_RELEASE_SQL), _claim_params(claim))
    if result.rowcount != 1:
        raise _claim_closed()


class PostgresBudgetLedger:
    """Sync facade over the async core (mirrors PostgresSessionStore)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_seconds: float = BUDGET_LEDGER_LEASE_SECONDS,
    ) -> None:
        self._core = _AsyncBudgetLedger(session_factory, lease_seconds=lease_seconds)

    def ping(self) -> None:
        _run_coro(self._core.ping())

    def claim(self, request: BudgetClaimRequest) -> BudgetClaim | None:
        return _run_coro(  # type: ignore[return-value]
            self._core.claim(request)
        )

    def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str:
        return _run_coro(  # type: ignore[return-value]
            self._core.finalize(claim, input_tokens=input_tokens, output_tokens=output_tokens)
        )

    def release(self, claim: BudgetClaim) -> None:
        _run_coro(self._core.release(claim))  # type: ignore[func-returns-value]

    def expire_stale(self, *, grace_seconds: int, batch_limit: int = 500) -> int:
        return _run_coro(  # type: ignore[return-value]
            self._core.expire_stale(grace_seconds=grace_seconds, batch_limit=batch_limit)
        )
