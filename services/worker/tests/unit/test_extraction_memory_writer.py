"""Unit tests for extraction memory HTTP writer."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.extraction.memory_writer import HttpMemoryWriter
from app.extraction.provider import ExtractionTransportError
from app.extraction.schema import ExtractedMemory


def test_writer_posts_labels_and_temporal_fields() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["idem"] = request.headers.get("x-idempotency-key")
        captured["json"] = request.content
        return httpx.Response(201, json={"data": {"id": str(uuid4())}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    writer = HttpMemoryWriter(
        base_url="http://memory.example",
        token="mem-token",
        client=client,
    )
    memory = ExtractedMemory.model_validate(
        {
            "content": "User prefers dark mode in the IDE",
            "categories": [
                {"label": "preference", "confidence": 0.9},
                {"label": "behavioral", "confidence": 0.6},
            ],
            "confidence": 0.88,
            "valid_from": datetime(2026, 9, 1, tzinfo=UTC),
            "valid_until": datetime(2026, 9, 8, tzinfo=UTC),
        }
    )
    org = uuid4()
    writer.write(
        org_id=org,
        agent_id=uuid4(),
        session_id=uuid4(),
        turn_index=3,
        memory=memory,
    )
    import json

    body = json.loads(captured["json"])  # type: ignore[arg-type]
    assert captured["path"] == "/v1/memories"
    assert captured["auth"] == "Bearer mem-token"
    assert captured["idem"]
    assert "org_id" not in body
    assert body["confidence"] == 0.88
    assert body["labels"][0]["label"] == "preference"
    assert "valid_from" in body
    assert "valid_until" in body


def test_writer_retries_on_503() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="no")

    writer = HttpMemoryWriter(
        base_url="http://memory.example",
        token="t",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    memory = ExtractedMemory.model_validate(
        {
            "content": "User prefers dark mode in the IDE",
            "categories": [{"label": "preference", "confidence": 0.9}],
            "confidence": 0.9,
        }
    )
    with pytest.raises(ExtractionTransportError):
        writer.write(
            org_id=uuid4(),
            agent_id=uuid4(),
            session_id=uuid4(),
            turn_index=0,
            memory=memory,
        )
