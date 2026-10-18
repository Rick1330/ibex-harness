"""Durable budget reservation ledger adapter for worker extraction (GAP-006).

Mirrors ``packages/budgetledger`` (Go) semantics: a claim is written before a
provider call only when the organization has an active ``hard_cap`` budget
period, finalized with measured usage (or the frozen estimate when the provider
reports no usage), and released when the provider call never happened.

Known limitation (documented, follow-up): extraction usage is not exported to
``ibex.usage_facts`` yet, so completed extraction spend is not reflected in
``spent_cents_cached``. Worker holds bound concurrent in-flight spend against
the cap; the durable rows keep the audit record for the eventual export.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_as_service_account, session_as_service_org
from app.extraction.session_store import _run_coro

BUDGET_LEDGER_LEASE_SECONDS = 900.0
DEFAULT_OUTPUT_TOKENS = 4096
TOKENS_PER_MESSAGE = 4
BYTES_PER_TOKEN = 4
COMPLETENESS_COMPLETE = "complete"
COMPLETENESS_ESTIMATED = "estimated"


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


class BudgetLedger(Protocol):
    """Synchronous ledger facade used by the extraction batch orchestration."""

    def claim(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> BudgetClaim | None: ...

    def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str: ...

    def release(self, claim: BudgetClaim) -> None: ...


def budget_reservation_key(*, session_id: UUID, first_turn_index: int) -> str:
    """Deterministic reservation key for one extraction unit of a session."""
    return f"extraction:{session_id}:{first_turn_index}"


def fingerprint_extraction_call(
    *, provider: str, model: str, system_prompt: str, user_content: str
) -> str:
    """Stable sha256 over the extraction call inputs (conflict detection)."""
    canonical = json.dumps(
        {
            "contract": "budget-reservation.v1",
            "operation": "extraction",
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "user_content": user_content,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def estimate_prompt_tokens(*, system_prompt: str, user_content: str) -> tuple[int, int]:
    """Heuristic (input, output) token estimate; provider max output is unknown."""
    input_tokens = (
        _heuristic_tokens(system_prompt)
        + TOKENS_PER_MESSAGE
        + _heuristic_tokens(user_content)
        + TOKENS_PER_MESSAGE
    )
    return input_tokens, DEFAULT_OUTPUT_TOKENS


def _heuristic_tokens(content: str) -> int:
    if not content:
        return 0
    return max(len(content), len(content.encode("utf-8")) // BYTES_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class _PriceRow:
    provider: str
    model_pattern: str
    input_cents_per_1k: int
    output_cents_per_1k: int


@dataclass(frozen=True, slots=True)
class _Card:
    version: str
    prices: tuple[_PriceRow, ...]


def _decode_card(prices_json: Any) -> tuple[_PriceRow, ...]:
    if prices_json is None:
        return ()
    if isinstance(prices_json, (str, bytes)):
        prices_json = json.loads(prices_json)
    if not isinstance(prices_json, list):
        raise BudgetLedgerError("rate card prices payload is not a list")
    rows: list[_PriceRow] = []
    for raw in prices_json:
        if not isinstance(raw, dict):
            raise BudgetLedgerError("rate card price row is not an object")
        rows.append(
            _PriceRow(
                provider=str(raw.get("provider") or ""),
                model_pattern=str(raw.get("model_pattern") or ""),
                input_cents_per_1k=int(raw.get("input_cents_per_1k") or 0),
                output_cents_per_1k=int(raw.get("output_cents_per_1k") or 0),
            )
        )
    return tuple(rows)


def _match_price(prices: tuple[_PriceRow, ...], provider: str, model: str) -> _PriceRow | None:
    """First row whose provider equals (case-insensitive) and pattern globs.

    Uses ``fnmatch`` (shell-style) as the close Python equivalent of Go
    ``path.Match``; model IDs do not contain separators in practice.
    """
    prov = provider.strip().lower()
    mod = model.strip()
    for row in prices:
        if row.provider.strip().lower() != prov:
            continue
        pattern = row.model_pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatchcase(mod, pattern):
            return row
    return None


def _estimate_cost(
    card: _Card, provider: str, model: str, input_tokens: int, output_tokens: int
) -> int | None:
    """Cost cents with per-component ceiling, mirroring billing.EstimateCost."""
    if not card.version:
        return None
    row = _match_price(card.prices, provider, model)
    if row is None:
        return None
    if input_tokens < 0 or output_tokens < 0:
        return None
    if row.input_cents_per_1k < 0 or row.output_cents_per_1k < 0:
        return None
    return _ceil_mul_div_1k(input_tokens, row.input_cents_per_1k) + _ceil_mul_div_1k(
        output_tokens, row.output_cents_per_1k
    )


def _ceil_mul_div_1k(tokens: int, cents_per_1k: int) -> int:
    if tokens == 0 or cents_per_1k == 0:
        return 0
    return (tokens * cents_per_1k + 999) // 1000


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

    async def claim(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> BudgetClaim | None:
        _validate_claim(key, request_hash)
        lease = timedelta(seconds=self._lease_seconds)
        try:
            async with session_as_service_org(self._factory, str(org_id)) as session:
                await session.execute(
                    text(
                        """
                        SELECT pg_advisory_xact_lock(
                            hashtext('budget-reservation:' || CAST(:org_id AS text))
                        )
                        """
                    ),
                    {"org_id": str(org_id)},
                )
                period = await self._load_active_period(session, org_id)
                if period is None:
                    return None
                card = await self._load_card(session, org_id)
                estimated = _estimate_cost(card, provider, model, input_tokens, output_tokens)
                if estimated is None:
                    raise BudgetAdmissionDeniedError("no_rate_card")
                return await self._claim_row(
                    session,
                    org_id=org_id,
                    agent_id=agent_id,
                    key=key,
                    request_hash=request_hash,
                    provider=provider,
                    model=model,
                    period_id=period["id"],
                    cap_cents=int(period["cap_cents"]),
                    spent_cents=int(period["spent_cents_cached"]),
                    estimated_cents=estimated,
                    lease=lease,
                )
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger claim failed") from exc

    async def _load_active_period(self, session: AsyncSession, org_id: UUID) -> Any:
        result = await session.execute(
            text(
                """
                SELECT id, cap_cents, spent_cents_cached
                FROM ibex_billing.budget_periods
                WHERE org_id = :org_id
                  AND period_start <= NOW()
                  AND period_end > NOW()
                  AND enforcement_mode = 'hard_cap'
                ORDER BY period_start DESC
                LIMIT 1
                """
            ),
            {"org_id": org_id},
        )
        return result.mappings().first()

    async def _load_card(self, session: AsyncSession, org_id: UUID) -> _Card:
        result = await session.execute(
            text(
                """
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
            ),
            {"org_id": org_id},
        )
        row = result.mappings().first()
        if row is None:
            return _Card(version="", prices=())
        return _Card(version=str(row["version"]), prices=_decode_card(row["prices"]))

    async def _claim_row(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        period_id: UUID,
        cap_cents: int,
        spent_cents: int,
        estimated_cents: int,
        lease: timedelta,
    ) -> BudgetClaim:
        result = await session.execute(
            text(
                """
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
            ),
            {"org_id": org_id, "agent_id": agent_id, "key": key},
        )
        row = result.mappings().first()
        if row is None:
            return await self._insert_row(
                session,
                org_id=org_id,
                agent_id=agent_id,
                key=key,
                request_hash=request_hash,
                provider=provider,
                model=model,
                period_id=period_id,
                cap_cents=cap_cents,
                spent_cents=spent_cents,
                estimated_cents=estimated_cents,
                lease=lease,
            )
        if row["request_hash"] != request_hash:
            raise BudgetAdmissionDeniedError("conflict")
        if row["state"] == "claimed" and row["lease_active"]:
            raise BudgetAdmissionDeniedError("in_progress", retry_after=int(row["retry_after"]))
        holds = await self._active_holds(
            session,
            org_id=org_id,
            period_id=period_id,
            exclude_id=row["id"],
        )
        if spent_cents + holds + estimated_cents > cap_cents:
            await self._expire_stale_row(
                session, row=row, org_id=org_id, agent_id=agent_id, key=key
            )
            raise BudgetAdmissionDeniedError("exceeded")
        return await self._reset_row(
            session,
            row=row,
            org_id=org_id,
            agent_id=agent_id,
            key=key,
            request_hash=request_hash,
            provider=provider,
            model=model,
            period_id=period_id,
            estimated_cents=estimated_cents,
            lease=lease,
        )

    async def _insert_row(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        period_id: UUID,
        cap_cents: int,
        spent_cents: int,
        estimated_cents: int,
        lease: timedelta,
    ) -> BudgetClaim:
        holds = await self._active_holds(
            session, org_id=org_id, period_id=period_id, exclude_id=None
        )
        if spent_cents + holds + estimated_cents > cap_cents:
            raise BudgetAdmissionDeniedError("exceeded")
        result = await session.execute(
            text(
                """
                INSERT INTO ibex_core.budget_reservations
                    (organization_id, agent_id, budget_period_id, reservation_key,
                     request_hash, state, amount_estimated_cents, lease_expires_at)
                VALUES (:org_id, :agent_id, :period_id, :key, :request_hash,
                        'claimed', :estimated_cents, NOW() + CAST(:lease AS interval))
                ON CONFLICT (organization_id, agent_id, reservation_key) DO NOTHING
                RETURNING id, version
                """
            ),
            {
                "org_id": org_id,
                "agent_id": agent_id,
                "period_id": period_id,
                "key": key,
                "request_hash": request_hash,
                "estimated_cents": estimated_cents,
                "lease": lease,
            },
        )
        inserted = result.mappings().first()
        if inserted is None:
            raise BudgetAdmissionDeniedError("in_progress", retry_after=1)
        return _claim_from_row(
            inserted,
            org_id=org_id,
            agent_id=agent_id,
            key=key,
            request_hash=request_hash,
            provider=provider,
            model=model,
            period_id=period_id,
        )

    async def _reset_row(
        self,
        session: AsyncSession,
        *,
        row: Any,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        period_id: UUID,
        estimated_cents: int,
        lease: timedelta,
    ) -> BudgetClaim:
        result = await session.execute(
            text(
                """
                UPDATE ibex_core.budget_reservations
                SET state = 'claimed',
                    budget_period_id = :period_id,
                    request_hash = :request_hash,
                    amount_estimated_cents = :estimated_cents,
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
            ),
            {
                "id": row["id"],
                "org_id": org_id,
                "agent_id": agent_id,
                "key": key,
                "version": int(row["version"]),
                "period_id": period_id,
                "request_hash": request_hash,
                "estimated_cents": estimated_cents,
                "lease": lease,
            },
        )
        updated = result.mappings().first()
        if updated is None:
            raise BudgetLedgerError("budgetledger: reset reservation failed")
        return _claim_from_row(
            updated,
            org_id=org_id,
            agent_id=agent_id,
            key=key,
            request_hash=request_hash,
            provider=provider,
            model=model,
            period_id=period_id,
        )

    async def _expire_stale_row(
        self, session: AsyncSession, *, row: Any, org_id: UUID, agent_id: UUID, key: str
    ) -> None:
        if row["state"] != "claimed":
            return
        await session.execute(
            text(
                """
                UPDATE ibex_core.budget_reservations
                SET state = 'expired', lease_expires_at = NULL,
                    version = version + 1, updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
                  AND reservation_key = :key AND state = 'claimed' AND version = :version
                """
            ),
            {
                "id": row["id"],
                "org_id": org_id,
                "agent_id": agent_id,
                "key": key,
                "version": int(row["version"]),
            },
        )

    async def _active_holds(
        self, session: AsyncSession, *, org_id: UUID, period_id: UUID, exclude_id: Any
    ) -> int:
        result = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(amount_estimated_cents), 0) AS active_holds
                FROM ibex_core.budget_reservations
                WHERE organization_id = :org_id AND budget_period_id = :period_id
                  AND state = 'claimed' AND lease_expires_at > NOW()
                  AND id IS DISTINCT FROM CAST(:exclude_id AS uuid)
                """
            ),
            {"org_id": org_id, "period_id": period_id, "exclude_id": exclude_id},
        )
        return int(result.scalar_one())

    async def finalize(self, claim: BudgetClaim, *, input_tokens: int, output_tokens: int) -> str:
        try:
            async with session_as_service_org(self._factory, str(claim.org_id)) as session:
                row = await self._load_claim_row(session, claim)
                if row is None:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
                card = await self._load_card(session, claim.org_id)
                amount, completeness = self._settle_amount(
                    card, claim, row["amount_estimated_cents"], input_tokens, output_tokens
                )
                if row["state"] == "finalized":
                    if (
                        int(row["amount_final_cents"]) == amount
                        and row["finalized_completeness"] == completeness
                    ):
                        return completeness
                    raise BudgetLedgerClaimClosedError(
                        "claim already finalized with a different outcome"
                    )
                if row["state"] != "claimed" or int(row["version"]) != claim.version:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
                result = await session.execute(
                    text(
                        """
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
                    ),
                    _claim_params(claim) | {"amount": amount, "completeness": completeness},
                )
                if result.rowcount != 1:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
                return completeness
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger finalize failed") from exc

    def _settle_amount(
        self,
        card: _Card,
        claim: BudgetClaim,
        stored_estimate: int,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[int, str]:
        if input_tokens + output_tokens > 0:
            measured = _estimate_cost(
                card, claim.provider, claim.model, input_tokens, output_tokens
            )
            if measured is not None:
                return measured, COMPLETENESS_COMPLETE
        return int(stored_estimate), COMPLETENESS_ESTIMATED

    async def release(self, claim: BudgetClaim) -> None:
        try:
            async with session_as_service_org(self._factory, str(claim.org_id)) as session:
                row = await self._load_claim_row(session, claim)
                if row is None:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
                if row["state"] == "released":
                    return
                if row["state"] != "claimed" or int(row["version"]) != claim.version:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
                result = await session.execute(
                    text(
                        """
                        UPDATE ibex_core.budget_reservations
                        SET state = 'released', lease_expires_at = NULL,
                            version = version + 1, updated_at = NOW()
                        WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
                          AND reservation_key = :key AND request_hash = :request_hash
                          AND version = :version AND state = 'claimed'
                        RETURNING id
                        """
                    ),
                    _claim_params(claim),
                )
                if result.rowcount != 1:
                    raise BudgetLedgerClaimClosedError("claim is no longer owned")
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger release failed") from exc

    async def _load_claim_row(self, session: AsyncSession, claim: BudgetClaim) -> Any:
        result = await session.execute(
            text(
                """
                SELECT id, state, amount_estimated_cents, amount_final_cents,
                       finalized_completeness, version
                FROM ibex_core.budget_reservations
                WHERE id = :id AND organization_id = :org_id AND agent_id = :agent_id
                  AND reservation_key = :key
                FOR UPDATE
                """
            ),
            {
                "id": claim.claim_id,
                "org_id": claim.org_id,
                "agent_id": claim.agent_id,
                "key": claim.key,
            },
        )
        return result.mappings().first()

    async def expire_stale(self, *, grace_seconds: int, batch_limit: int) -> int:
        if grace_seconds < 0:
            raise BudgetLedgerError("invalid reaper grace")
        if batch_limit <= 0:
            raise BudgetLedgerError("invalid reaper batch limit")
        try:
            async with session_as_service_account(self._factory) as session:
                result = await session.execute(
                    text(
                        """
                        WITH stale AS (
                            SELECT id
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
                        WHERE r.id = stale.id AND r.state = 'claimed'
                        RETURNING r.id
                        """
                    ),
                    {"grace": timedelta(seconds=grace_seconds), "batch_limit": batch_limit},
                )
                return len(result.fetchall())
        except BudgetLedgerError:
            raise
        except SQLAlchemyError as exc:
            raise BudgetLedgerUnavailableError("budget ledger sweep failed") from exc


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

    def claim(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> BudgetClaim | None:
        return _run_coro(  # type: ignore[return-value]
            self._core.claim(
                org_id=org_id,
                agent_id=agent_id,
                key=key,
                request_hash=request_hash,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
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


def _validate_claim(key: str, request_hash: str) -> None:
    if not key or len(key) > 256 or not request_hash:
        raise BudgetLedgerError("invalid budget claim")


def _claim_from_row(
    row: Any,
    *,
    org_id: UUID,
    agent_id: UUID,
    key: str,
    request_hash: str,
    provider: str,
    model: str,
    period_id: UUID,
) -> BudgetClaim:
    return BudgetClaim(
        claim_id=row["id"],
        org_id=org_id,
        agent_id=agent_id,
        key=key,
        request_hash=request_hash,
        period_id=period_id,
        provider=provider,
        model=model,
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
