"""Canonical request fingerprinting for the shared idempotency ledger.

The ledger binds a claim to a ``request_hash`` so that a key reused with a
different request body is rejected as a conflict instead of silently replaying
an unrelated response. To make the hash stable across runtimes and processes,
the payload is serialized with sorted keys, compact separators, and no ASCII
escaping before hashing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The single canonicalization contract shared by all ledger callers.
IDEMPOTENCY_CONTRACT = "request-idempotency-core.v1"


def canonical_request_bytes(
    *,
    contract: str,
    method: str,
    path: str,
    payload: Any,
) -> bytes:
    """Return the canonical UTF-8 byte form of a request for hashing."""
    canonical = json.dumps(
        {
            "contract": contract,
            "method": method.upper(),
            "path": path,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return canonical.encode("utf-8")


def fingerprint_request(
    *,
    contract: str,
    method: str,
    path: str,
    payload: Any,
) -> str:
    """Return the lowercase hex SHA-256 fingerprint of a normalized request."""
    return hashlib.sha256(
        canonical_request_bytes(contract=contract, method=method, path=path, payload=payload)
    ).hexdigest()


__all__ = [
    "IDEMPOTENCY_CONTRACT",
    "canonical_request_bytes",
    "fingerprint_request",
]
