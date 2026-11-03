"""Unit tests for canonical request fingerprinting."""

from __future__ import annotations

import hashlib
import json

from ibex_idempotency import (
    IDEMPOTENCY_CONTRACT,
    canonical_request_bytes,
    fingerprint_request,
)


def test_fingerprint_is_deterministic_and_lowercase_hex() -> None:
    digest = fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/v1/memories",
        payload={"b": 2, "a": 1},
    )
    assert len(digest) == 64
    assert digest == digest.lower()
    assert (
        fingerprint_request(
            contract=IDEMPOTENCY_CONTRACT,
            method="POST",
            path="/v1/memories",
            payload={"b": 2, "a": 1},
        )
        == digest
    )


def test_fingerprint_is_key_order_independent() -> None:
    assert fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT, method="POST", path="/p", payload={"a": 1, "b": 2}
    ) == fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT, method="POST", path="/p", payload={"b": 2, "a": 1}
    )


def test_fingerprint_is_method_case_insensitive() -> None:
    assert fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT, method="post", path="/p", payload={}
    ) == fingerprint_request(contract=IDEMPOTENCY_CONTRACT, method="POST", path="/p", payload={})


def test_fingerprint_changes_with_payload() -> None:
    a = fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT, method="POST", path="/p", payload={"a": 1}
    )
    b = fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT, method="POST", path="/p", payload={"a": 2}
    )
    assert a != b


def test_canonical_bytes_matches_request_idempotency_core_v1() -> None:
    # Regression lock: the worker adapter historically hashed this exact shape.
    payload = {"org": "o", "turns": [{"role": "user", "content": "hi"}]}
    expected = json.dumps(
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
    actual = canonical_request_bytes(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/internal/extraction/enqueue",
        payload=payload,
    )
    assert actual == expected
    assert hashlib.sha256(actual).hexdigest() == fingerprint_request(
        contract=IDEMPOTENCY_CONTRACT,
        method="POST",
        path="/internal/extraction/enqueue",
        payload=payload,
    )
