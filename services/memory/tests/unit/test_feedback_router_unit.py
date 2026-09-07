"""Unit tests for POST /v1/memories/{id}/feedback HTTP surface."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_feedback_service
from app.exceptions import MemoryNotFoundError, ValidationError
from app.feedback.models import ApplyFeedbackResult, FeedbackKind
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE

TOKEN = "test-feedback-token"
ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MEMORY = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _client(
    *, permissions: int = MEMORY_WRITE, agent_id: UUID | None = AGENT
) -> tuple[TestClient, AsyncMock]:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=permissions, agent_id=agent_id)}
    )
    app = create_app(settings=settings, validator=validator)
    mock = AsyncMock()
    app.dependency_overrides[get_feedback_service] = lambda: mock
    return TestClient(app), mock


def test_feedback_requires_memory_write() -> None:
    http, mock = _client(permissions=MEMORY_READ)
    with http:
        response = http.post(
            f"/v1/memories/{MEMORY}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "positive"},
        )
    assert response.status_code == 403
    mock.apply.assert_not_called()


def test_feedback_requires_agent_scoped_token() -> None:
    http, mock = _client(agent_id=None)
    with http:
        response = http.post(
            f"/v1/memories/{MEMORY}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "positive"},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    mock.apply.assert_not_called()


def test_feedback_happy_path() -> None:
    http, mock = _client()
    mock.apply.return_value = ApplyFeedbackResult(
        memory_id=MEMORY,
        feedback=FeedbackKind.POSITIVE,
        new_usefulness_score=0.67,
        total_positive_feedback=1,
        total_negative_feedback=0,
        memory_agent_id=AGENT,
    )
    with http:
        response = http.post(
            f"/v1/memories/{MEMORY}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "positive", "notes": "helped"},
        )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["memory_id"] == str(MEMORY)
    assert body["feedback"] == "positive"
    assert body["new_usefulness_score"] == pytest.approx(0.67)
    assert body["total_positive_feedback"] == 1
    mock.apply.assert_awaited_once()


def test_feedback_not_found_maps_404() -> None:
    http, mock = _client()
    mock.apply.side_effect = MemoryNotFoundError()
    with http:
        response = http.post(
            f"/v1/memories/{MEMORY}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "negative"},
        )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_feedback_rejects_oversized_notes() -> None:
    http, mock = _client()
    with http:
        response = http.post(
            f"/v1/memories/{MEMORY}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "neutral", "notes": "x" * 2001},
        )
    assert response.status_code == 400
    mock.apply.assert_not_called()


def test_feedback_validation_error_maps_400() -> None:
    http, mock = _client()
    mock.apply.side_effect = ValidationError("bad", field="feedback")
    with http:
        response = http.post(
            f"/v1/memories/{uuid4()}/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"feedback": "positive"},
        )
    assert response.status_code == 400
