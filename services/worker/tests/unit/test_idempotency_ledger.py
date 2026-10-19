"""Facade tests for the worker idempotency ledger wiring.

The durable claim/finalize/release adapter and its concurrency semantics now
live in ``ibex_idempotency`` (see that package's ``test_ledger_unit.py``). This
module pins the worker-specific contract: the extraction-enqueue path constant
and the byte-stable request fingerprint used for dedupe.
"""

from __future__ import annotations

from ibex_idempotency import (
    IDEMPOTENCY_CONTRACT,
    ClaimOutcome,
    ClaimToken,
    PostgresIdempotencyLedger,
)

from app import idempotency_ledger as mod

_PAYLOAD = {"org_id": "o", "agent_id": "a", "session_id": "s", "turns": []}
_PAYLOAD_FINGERPRINT = "af1448b4b9f99d852db6499bdca08bc8933c774e5ad8c8b2a5bccf0e39a37383"


def test_enqueue_path_matches_proxy_contract() -> None:
    assert mod.ENQUEUE_PATH == "/internal/extraction/enqueue"
    assert mod.IDEMPOTENCY_CONTRACT == IDEMPOTENCY_CONTRACT == "request-idempotency-core.v1"


def test_fingerprint_is_deterministic_and_payload_sensitive() -> None:
    assert mod.fingerprint_enqueue(_PAYLOAD) == mod.fingerprint_enqueue(dict(_PAYLOAD))
    changed = {**_PAYLOAD, "turns": [{"turn_index": 0, "role": "user", "content": "x"}]}
    assert mod.fingerprint_enqueue(_PAYLOAD) != mod.fingerprint_enqueue(changed)


def test_fingerprint_is_byte_stable_across_versions() -> None:
    assert mod.fingerprint_enqueue(_PAYLOAD) == _PAYLOAD_FINGERPRINT


def test_facade_reexports_shared_ledger_types() -> None:
    assert mod.PostgresIdempotencyLedger is PostgresIdempotencyLedger
    assert mod.ClaimOutcome is ClaimOutcome
    assert mod.ClaimToken is ClaimToken
