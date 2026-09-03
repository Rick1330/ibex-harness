"""Unit tests for extraction memory HTTP writer."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.extraction.memory_writer import HttpMemoryWriter, MemoryHttpConfig, MemoryWriteRequest
from app.extraction.provider import ExtractionTransportError
from app.extraction.schema import ExtractedMemory


def _memory() -> ExtractedMemory:
    return ExtractedMemory.model_validate(
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


def _request(memory: ExtractedMemory | None = None) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        org_id=uuid4(),
        agent_id=uuid4(),
        session_id=uuid4(),
        turn_index=3,
        memory=memory or _memory(),
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

    writer = _writer(handler, token="mem-token")
    writer.write(_request())
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
