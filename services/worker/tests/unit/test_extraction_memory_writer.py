"""Unit tests for extraction memory HTTP writer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.extraction.memory_writer import (
    HttpMemoryWriter,
    MemoryHttpConfig,
    MemoryWriteRequest,
    TurnContentRef,
    batch_fingerprint,
    content_derived_idempotency_digest,
    memory_idempotency_digest,
    memory_idempotency_key,
)
from app.extraction.provider import ExtractionTransportError
from app.extraction.schema import ExtractedMemory


def _memory(*, content: str = "User prefers dark mode in the IDE") -> ExtractedMemory:
    return ExtractedMemory.model_validate(
        {
            "content": content,
            "categories": [
                {"label": "preference", "confidence": 0.9},
                {"label": "behavioral", "confidence": 0.6},
            ],
            "confidence": 0.88,
            "valid_from": datetime(2026, 9, 1, tzinfo=UTC),
            "valid_until": datetime(2026, 9, 8, tzinfo=UTC),
        }
    )


def _request(
    memory: ExtractedMemory | None = None,
    *,
    org_id=None,
    session_id=None,
    turn_index: int = 3,
    batch_fingerprint: str = "fp",
    ordinal: int = 0,
) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        org_id=org_id or uuid4(),
        agent_id=uuid4(),
        session_id=session_id or uuid4(),
        turn_index=turn_index,
        memory=memory or _memory(),
        batch_fingerprint=batch_fingerprint,
        ordinal=ordinal,
    )


def _writer(handler, *, token: str = "t") -> HttpMemoryWriter:
    return HttpMemoryWriter(
        MemoryHttpConfig(base_url="http://memory.example", token=token),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_writer_posts_labels_and_temporal_fields() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["idem"] = request.headers.get("x-idempotency-key")
        captured["json"] = request.content
        return httpx.Response(201, json={"data": {"id": str(uuid4())}})

    org_id = uuid4()
    session_id = uuid4()
    writer = _writer(handler, token="mem-token")
    writer.write(
        _request(
            org_id=org_id,
            session_id=session_id,
            batch_fingerprint="abc",
            ordinal=2,
            turn_index=5,
        )
    )
    body = json.loads(captured["json"])  # type: ignore[arg-type]
    assert captured["path"] == "/v1/memories"
    assert captured["auth"] == "Bearer mem-token"
    assert captured["idem"] == memory_idempotency_key(
        org_id=org_id,
        session_id=session_id,
        batch_fp="abc",
        turn_index=5,
        ordinal=2,
    )
    assert "org_id" not in body
    assert body["confidence"] == 0.88
    assert body["labels"][0]["label"] == "preference"
    assert "valid_from" in body
    assert "valid_until" in body


def test_batch_position_key_stable_when_llm_wording_differs() -> None:
    """Regression: content-derived keys diverge; batch-position keys do not."""
    org_id = uuid4()
    session_id = uuid4()
    turns = [
        TurnContentRef(turn_index=0, content="hello durable turn content"),
        TurnContentRef(turn_index=1, content="second durable turn content"),
    ]
    batch_fp = batch_fingerprint(turns)
    wording_a = "User prefers dark mode"
    wording_b = "The user likes dark theme"
    old_a = content_derived_idempotency_digest(
        org_id=org_id, session_id=session_id, turn_index=0, content=wording_a
    )
    old_b = content_derived_idempotency_digest(
        org_id=org_id, session_id=session_id, turn_index=0, content=wording_b
    )
    assert old_a != old_b
    new_a = memory_idempotency_digest(
        org_id=org_id,
        session_id=session_id,
        batch_fp=batch_fp,
        turn_index=0,
        ordinal=0,
    )
    new_b = memory_idempotency_digest(
        org_id=org_id,
        session_id=session_id,
        batch_fp=batch_fp,
        turn_index=0,
        ordinal=0,
    )
    assert new_a == new_b


def test_writer_treats_idempotency_conflict_as_success() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": {
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "Idempotency key reused with different request",
                }
            },
        )

    _writer(handler).write(_request())


def test_writer_treats_duplicate_content_as_success() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": {
                    "code": "DUPLICATE_CONTENT",
                    "message": "A memory with identical content already exists",
                    "existing_memory_id": str(uuid4()),
                }
            },
        )

    _writer(handler).write(_request())


def test_writer_retries_idempotency_in_progress() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": {
                    "code": "IDEMPOTENCY_IN_PROGRESS",
                    "message": "Request with this idempotency key is in progress",
                }
            },
        )

    with pytest.raises(ExtractionTransportError, match="IDEMPOTENCY_IN_PROGRESS"):
        _writer(handler).write(_request())


def test_writer_unknown_409_is_hard_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"code": "OTHER", "message": "nope"}})

    with pytest.raises(ValueError, match="409"):
        _writer(handler).write(_request())


def test_writer_rejects_empty_base_url() -> None:
    config = MemoryHttpConfig(base_url="  ", token="t")
    with pytest.raises(ValueError, match="memory_base_url"):
        HttpMemoryWriter(config)


def test_writer_rejects_empty_token() -> None:
    config = MemoryHttpConfig(base_url="http://memory.example", token="")
    with pytest.raises(ValueError, match="memory_api_token"):
        HttpMemoryWriter(config)


def _status_503(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="no")


def _status_400(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(400, text="bad")


def _timeout(_request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow")


def _connect_error(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


@pytest.mark.parametrize(
    ("handler", "exc_type", "match"),
    [
        (_status_503, ExtractionTransportError, None),
        (_status_400, ValueError, "400"),
        (_timeout, ExtractionTransportError, "timeout"),
        (_connect_error, ExtractionTransportError, "transport"),
    ],
)
def test_writer_error_paths(
    handler, exc_type: type[Exception], match: str | None
) -> None:
    writer = _writer(handler)
    request = _request()
    with pytest.raises(exc_type, match=match):
        writer.write(request)


def test_writer_close_owned_client() -> None:
    writer = HttpMemoryWriter(MemoryHttpConfig(base_url="http://memory.example", token="t"))
    writer.close()
    writer.close()
