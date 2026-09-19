"""Deletion-store receipt helpers (extracted for CodeScene cohesion on org_deletion)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

# Store names live here; NON_ERASABLE_STORES is owned by org_deletion (tests patch it).
STORES = ("postgres", "clickhouse", "redis", "objectstore")

_RECEIPT_BY_STORE = """
SELECT status FROM ibex_core.deletion_store_receipts
WHERE job_id = CAST(:job_id AS uuid)
  AND store = :store
ORDER BY updated_at DESC
LIMIT 1
"""


def _non_erasable() -> frozenset[str]:
    from app.tasks import org_deletion as od

    return od.NON_ERASABLE_STORES


def _refuse_non_erasable(store: str) -> None:
    if store in _non_erasable():
        raise ValueError(f"store {store!r} is non-erasable")


@dataclass(frozen=True, slots=True)
class ReceiptWrite:
    job_id: str
    store: str
    status: str
    error: str | None = None


async def _latest_receipt_status(session, job_id: str, store: str) -> str | None:
    result = await session.execute(
        text(_RECEIPT_BY_STORE),
        {"job_id": job_id, "store": store},
    )
    row = result.first()
    return str(row[0]) if row is not None else None


async def receipt_verified(session, job_id: str, store: str) -> bool:
    _refuse_non_erasable(store)
    return await _latest_receipt_status(session, job_id, store) == "verified"


async def receipt_terminal(session, job_id: str, store: str) -> bool:
    """True when this store already has a terminal receipt (verified or not_applicable)."""
    _refuse_non_erasable(store)
    status = await _latest_receipt_status(session, job_id, store)
    return status in {"verified", "not_applicable"}


async def receipt_status(session, job_id: str, store: str) -> str | None:
    return await _latest_receipt_status(session, job_id, store)


async def upsert_receipt(session, receipt: ReceiptWrite) -> None:
    _refuse_non_erasable(receipt.store)
    idem = f"{receipt.job_id}:{receipt.store}:org"
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.deletion_store_receipts (
                job_id, store, scope, status, verified_absent_at, idempotency_key, error
            ) VALUES (
                CAST(:job_id AS uuid), :store, 'org', :status,
                CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
                :idem, :error
            )
            ON CONFLICT (job_id, store, idempotency_key) DO UPDATE
            SET status = EXCLUDED.status,
                verified_absent_at = EXCLUDED.verified_absent_at,
                error = EXCLUDED.error,
                updated_at = NOW()
            """
        ),
        {
            "job_id": receipt.job_id,
            "store": receipt.store,
            "status": receipt.status,
            "idem": idem,
            "error": receipt.error,
        },
    )


def parse_deployed_stores(settings: Any) -> frozenset[str]:
    raw = getattr(settings, "org_deletion_deployed_stores", None) or os.environ.get(
        "IBEX_ORG_DELETION_DEPLOYED_STORES", ""
    )
    if not str(raw).strip():
        return frozenset({"postgres"})
    allowed = frozenset(STORES)
    parsed = {s.strip().lower() for s in str(raw).split(",") if s.strip()}
    unknown = parsed - allowed
    if unknown:
        raise ValueError(f"unknown org_deletion_deployed_stores: {sorted(unknown)}")
    if "postgres" not in parsed:
        parsed.add("postgres")
    return frozenset(parsed)


def store_is_deployed(settings: Any, store: str) -> bool:
    return store in parse_deployed_stores(settings)


async def receipt_digests(session, job_id: str) -> dict[str, str]:
    result = await session.execute(
        text(
            """
            SELECT store, status, COALESCE(verified_absent_at::text, ''), COALESCE(error, '')
            FROM ibex_core.deletion_store_receipts
            WHERE job_id = CAST(:job_id AS uuid)
            ORDER BY store
            """
        ),
        {"job_id": job_id},
    )
    out: dict[str, str] = {}
    for store, status, verified, err in result.fetchall():
        raw = f"{store}|{status}|{verified}|{err}"
        out[str(store)] = hashlib.sha256(raw.encode()).hexdigest()
    return out
