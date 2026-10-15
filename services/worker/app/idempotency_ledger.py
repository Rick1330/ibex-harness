"""PostgreSQL request-idempotency ledger adapter for worker HTTP mutations."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_as_service_org

LEDGER_LEASE_SECONDS = 120.0


class LedgerError(RuntimeError):
    """Raised when the durable ledger cannot admit or persist a mutation."""


class LedgerConflictError(LedgerError):
    """Raised when a stale owner attempts to finalize or release a claim."""


@dataclass(frozen=True, slots=True)
class ClaimToken:
    claim_id: UUID
    org_id: UUID
    agent_id: UUID
    key: str
    request_hash: str
    version: int


@dataclass(frozen=True, slots=True)
class ClaimOutcome:
    kind: str
    claim: ClaimToken | None = None
    status: int | None = None
    response: bytes | None = None
    retry_after: int | None = None


def fingerprint_enqueue(payload: dict[str, Any]) -> str:
    """Hash the complete normalized enqueue request, including every turn body."""
    canonical = json.dumps(
        {
            "contract": "request-idempotency-core.v1",
            "method": "POST",
            "path": "/internal/extraction/enqueue",
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class PostgresIdempotencyLedger:
    """Async adapter for the existing tenant-scoped ledger table."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_seconds: float = LEDGER_LEASE_SECONDS,
    ) -> None:
        self._factory = session_factory
        self._lease_seconds = max(1.0, lease_seconds)

    async def claim(
        self, *, org_id: UUID, agent_id: UUID, key: str, request_hash: str
    ) -> ClaimOutcome:
        if not key or len(key) > 256 or not request_hash:
            raise LedgerError("invalid idempotency claim")
        lease = self._lease_interval()
        async with session_as_service_org(self._factory, str(org_id)) as session:
            inserted = (
                (
                    await session.execute(
                        text(
                            """
                        INSERT INTO ibex_core.idempotency_ledger
                          (organization_id, agent_id, dedupe_key, request_hash,
                           state, lease_expires_at)
                        VALUES (:org_id, :agent_id, :key, :request_hash,
                                'claimed', NOW() + CAST(:lease AS interval))
                        ON CONFLICT (organization_id, agent_id, dedupe_key) DO NOTHING
                        RETURNING id, request_hash, state, status_code,
                                  response_payload, lease_expires_at, version
                        """
                        ),
                        {
                            "org_id": org_id,
                            "agent_id": agent_id,
                            "key": key,
                            "request_hash": request_hash,
                            "lease": lease,
                        },
                    )
                )
                .mappings()
                .first()
            )
            fresh = inserted is not None
            row = inserted
            if row is None:
                row = (
                    (
                        await session.execute(
                            text(
                                """
                            SELECT id, request_hash, state, status_code,
                                   response_payload, lease_expires_at, version
                            FROM ibex_core.idempotency_ledger
                            WHERE organization_id=:org_id
                              AND agent_id=:agent_id
                              AND dedupe_key=:key
                            FOR UPDATE
                            """
                            ),
                            {"org_id": org_id, "agent_id": agent_id, "key": key},
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise LedgerError("idempotency ledger row disappeared")
            outcome = await self._resolve_row(
                row,
                fresh=fresh,
                org_id=org_id,
                agent_id=agent_id,
                key=key,
                request_hash=request_hash,
                lease=lease,
                session=session,
            )
            return outcome

    async def _resolve_row(
        self,
        row: Any,
        *,
        fresh: bool,
        org_id: UUID,
        agent_id: UUID,
        key: str,
        request_hash: str,
        lease: str,
        session: AsyncSession,
    ) -> ClaimOutcome:
        claim = ClaimToken(
            claim_id=row["id"],
            org_id=org_id,
            agent_id=agent_id,
            key=key,
            request_hash=row["request_hash"],
            version=int(row["version"]),
        )
        if row["request_hash"] != request_hash:
            return ClaimOutcome(kind="conflict", claim=claim)
        if fresh:
            return ClaimOutcome(kind="owned", claim=claim)
        if row["state"] == "finalized":
            return ClaimOutcome(
                kind="replay",
                claim=claim,
                status=int(row["status_code"]),
                response=bytes(row["response_payload"]),
            )
        expires = row["lease_expires_at"]
        if row["state"] != "claimed" or expires is None:
            raise LedgerError(f"unsupported ledger state {row['state']!r}")
        remaining = expires.timestamp() - time.time()
        if remaining > 0:
            return ClaimOutcome(
                kind="in_progress", claim=claim, retry_after=max(1, int(remaining) + 1)
            )
        reclaimed = await session.execute(
            text(
                """
                    UPDATE ibex_core.idempotency_ledger
                    SET lease_expires_at=NOW()+CAST(:lease AS interval),
                        version=version+1, updated_at=NOW()
                    WHERE id=:id AND organization_id=:org_id AND agent_id=:agent_id
                      AND dedupe_key=:key AND request_hash=:request_hash
                      AND state='claimed' AND lease_expires_at <= NOW()
                    RETURNING version
                    """
            ),
            {
                "lease": lease,
                "id": row["id"],
                "org_id": org_id,
                "agent_id": agent_id,
                "key": key,
                "request_hash": request_hash,
            },
        )
        row = reclaimed.mappings().first()
        if row is None:
            return ClaimOutcome(kind="in_progress", claim=claim, retry_after=1)
        return ClaimOutcome(
            kind="owned",
            claim=ClaimToken(
                claim_id=claim.claim_id,
                org_id=claim.org_id,
                agent_id=claim.agent_id,
                key=claim.key,
                request_hash=claim.request_hash,
                version=int(row["version"]),
            ),
        )

    async def finalize(self, claim: ClaimToken, *, status: int, response: bytes) -> None:
        async with session_as_service_org(self._factory, str(claim.org_id)) as session:
            result = await session.execute(
                text(
                    """
                    UPDATE ibex_core.idempotency_ledger
                    SET state='finalized', status_code=:status, response_payload=:response,
                        lease_expires_at=NULL, version=version+1, updated_at=NOW()
                    WHERE id=:id AND organization_id=:org_id AND agent_id=:agent_id
                      AND dedupe_key=:key AND request_hash=:request_hash
                      AND version=:version AND state='claimed'
                    """
                ),
                _claim_params(claim) | {"status": status, "response": response},
            )
            if result.rowcount != 1:
                raise LedgerConflictError("claim is no longer owned")

    async def release(self, claim: ClaimToken) -> None:
        async with session_as_service_org(self._factory, str(claim.org_id)) as session:
            result = await session.execute(
                text(
                    """
                    DELETE FROM ibex_core.idempotency_ledger
                    WHERE id=:id AND organization_id=:org_id AND agent_id=:agent_id
                      AND dedupe_key=:key AND request_hash=:request_hash
                      AND version=:version AND state='claimed'
                    """
                ),
                _claim_params(claim),
            )
            if result.rowcount != 1:
                raise LedgerConflictError("claim is no longer owned")

    def _lease_interval(self) -> str:
        return f"{self._lease_seconds:.6f} seconds"


def _claim_params(claim: ClaimToken) -> dict[str, Any]:
    return {
        "id": claim.claim_id,
        "org_id": claim.org_id,
        "agent_id": claim.agent_id,
        "key": claim.key,
        "request_hash": claim.request_hash,
        "version": claim.version,
    }
