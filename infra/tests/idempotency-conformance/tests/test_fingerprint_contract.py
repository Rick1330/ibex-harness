"""Published conformance vector for the request-idempotency-core.v1 fingerprint.

The exact canonical bytes are frozen here so any change to the JSON
canonicalization (key order, separators, ASCII escaping, method casing) is a
deliberate, reviewed contract change rather than silent drift.
"""

from __future__ import annotations

from ibex_idempotency import (
    IDEMPOTENCY_CONTRACT,
    canonical_request_bytes,
    fingerprint_request,
)

_PAYLOAD = {
    "org_id": "00000000-0000-0000-0000-000000000001",
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "session_id": "00000000-0000-0000-0000-000000000003",
    "turns": [{"turn_index": 0, "role": "user", "content": "café"}],
}

_CANONICAL_UTF8 = (
    '{"contract":"request-idempotency-core.v1","method":"POST",'
    '"path":"/v1/memories","payload":{"agent_id":"00000000-0000-0000-0000-000000000002",'
    '"org_id":"00000000-0000-0000-0000-000000000001",'
    '"session_id":"00000000-0000-0000-0000-000000000003",'
    '"turns":[{"content":"café","role":"user","turn_index":0}]}}'
)


def test_canonical_bytes_vector() -> None:
    actual = canonical_request_bytes(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/v1/memories",
        payload=_PAYLOAD,
    )
    assert actual.decode("utf-8") == _CANONICAL_UTF8


def test_fingerprint_matches_vector_and_is_stable() -> None:
    assert fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/v1/memories",
        payload=_PAYLOAD,
    ) == fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/v1/memories",
        payload={k: _PAYLOAD[k] for k in reversed(list(_PAYLOAD))},
    )
