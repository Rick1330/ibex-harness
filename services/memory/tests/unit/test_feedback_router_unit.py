"""Unit tests for POST /v1/memories/{id}/feedback HTTP surface."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_feedback_service
from app.exceptions import MemoryNotFoundError, ValidationError
from app.feedback.models import ApplyFeedbackResult, FeedbackKind
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.routers.memories import http_error_for_feedback

TOKEN = "test-feedback-token"
ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MEMORY = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@dataclass(frozen=True, slots=True)
class _GateCase:
    permissions: int
    agent_id: UUID | None
    body: dict
    expected_status: int
    expected_code: str


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


def _post_feedback(
    http: TestClient,
    *,
    memory_id: UUID = MEMORY,
    body: dict | None = None,
) -> object:
    return http.post(
        f"/v1/memories/{memory_id}/feedback",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=body or {"feedback": "positive"},
    )


@pytest.mark.parametrize(
    "case",
    [
        _GateCase(
            MEMORY_READ,
            AGENT,
            {"feedback": "positive"},
            403,
            "INSUFFICIENT_PERMISSIONS",
        ),
        _GateCase(
            MEMORY_WRITE,
            None,
            {"feedback": "positive"},
            400,
            "VALIDATION_ERROR",
        ),
        _GateCase(
            MEMORY_WRITE,
            AGENT,
            {"feedback": "neutral", "notes": "x" * 2001},
            400,
            "VALIDATION_ERROR",
        ),
    ],
)
def test_feedback_request_gates(case: _GateCase) -> None:
    http, mock = _client(permissions=case.permissions, agent_id=case.agent_id)
    with http:
        response = _post_feedback(http, body=case.body)
    assert response.status_code == case.expected_status
    assert response.json()["detail"]["code"] == case.expected_code
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
        response = _post_feedback(http, body={"feedback": "positive", "notes": "helped"})
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
        response = _post_feedback(http, body={"feedback": "negative"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_feedback_validation_error_maps_400() -> None:
    http, mock = _client()
    mock.apply.side_effect = ValidationError("bad", field="feedback")
    with http:
        response = _post_feedback(http, memory_id=uuid4())
    assert response.status_code == 400


def test_feedback_database_error_maps_503() -> None:
    http, mock = _client()
    mock.apply.side_effect = SQLAlchemyError("boom")
    with http:
        response = _post_feedback(http)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


def test_http_error_for_feedback_passthrough() -> None:
    err = RuntimeError("unexpected")
    with pytest.raises(RuntimeError, match="unexpected"):
        http_error_for_feedback(err)
