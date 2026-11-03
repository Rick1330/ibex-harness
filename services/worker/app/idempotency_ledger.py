"""Worker idempotency ledger facade.

The durable claim/finalize/release adapter now lives in the shared
``ibex_idempotency`` package (the Python counterpart of the Go ledger). This
module binds it to the worker's extraction-enqueue contract and re-exports the
shared types so existing worker imports keep working.
"""

from __future__ import annotations

from typing import Any

from ibex_idempotency import (
    IDEMPOTENCY_CONTRACT,
    LEDGER_LEASE_SECONDS,
    ClaimOutcome,
    ClaimToken,
    LedgerConflictError,
    LedgerError,
    LedgerValidationError,
    PostgresIdempotencyLedger,
    fingerprint_request,
)

ENQUEUE_PATH = "/internal/extraction/enqueue"


def fingerprint_enqueue(payload: dict[str, Any]) -> str:
    """Hash the complete normalized enqueue request, including every turn body."""
    return fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path=ENQUEUE_PATH,
        payload=payload,
    )


__all__ = [
    "ENQUEUE_PATH",
    "IDEMPOTENCY_CONTRACT",
    "LEDGER_LEASE_SECONDS",
    "ClaimOutcome",
    "ClaimToken",
    "LedgerConflictError",
    "LedgerError",
    "LedgerValidationError",
    "PostgresIdempotencyLedger",
    "fingerprint_enqueue",
]
