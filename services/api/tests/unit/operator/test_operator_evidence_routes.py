"""Mounted-route contract tests for the metadata-only operator evidence summary."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import VALIDATION_ERROR
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.schemas.operator_evidence import (
    EvidenceCapturePolicy,
    EvidenceCompletenessCounts,
    EvidenceDeliveryCounts,
    EvidenceLegalHold,
    EvidenceStatusCounts,
    OperatorEvidenceSummary,
)
from tests.unit.operator.conftest import create_operator_app

PAT = "ibex_pat_operator_evidence"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _validator(org_id: object, permissions: int = OPERATOR_METADATA_READ) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def _summary() -> OperatorEvidenceSummary:
    return OperatorEvidenceSummary(
        range="7d",
        window_start=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
        window_end=NOW,
        observed_at=NOW,
        runs_total=10,
        capture_complete_runs=8,
        completeness=EvidenceCompletenessCounts(complete=8, partial=2),
        statuses=EvidenceStatusCounts(ok=9, error=1),
        last_run_at=NOW,
        delivery=EvidenceDeliveryCounts(delivered=9, pending=1),
        oldest_unsettled_at=NOW,
        last_delivered_at=NOW,
        capture_policy=EvidenceCapturePolicy(mode="metadata_only"),
        legal_hold=EvidenceLegalHold(active=False, since=None),
    )


def test_evidence_summary_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/evidence/summary")
    assert response.status_code == 401


def test_evidence_summary_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/evidence/summary")
    assert response.status_code == 403


def test_evidence_summary_projects_the_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()
    seen: dict[str, object] = {}

    async def fake_summary(_session: object, args: object) -> OperatorEvidenceSummary:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["range"] = args.range  # type: ignore[attr-defined]
        return _summary()

    monkeypatch.setattr(
        "app.routers.operator_evidence.evidence_service.get_evidence_summary",
        fake_summary,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/summary?range=7d")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "operator.evidence.summary.v1"
    assert body["range"] == "7d"
    assert body["runs_total"] == 10
    assert body["capture_complete_runs"] == 8
    assert body["completeness"]["complete"] == 8
    assert body["statuses"]["error"] == 1
    assert body["delivery"]["pending"] == 1
    assert body["capture_policy"]["mode"] == "metadata_only"
    assert body["legal_hold"]["active"] is False
    assert seen == {"org_id": org_id, "range": "7d"}


def test_evidence_summary_defaults_to_a_24h_window(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake_summary(_session: object, args: object) -> OperatorEvidenceSummary:
        seen["range"] = args.range  # type: ignore[attr-defined]
        return _summary().model_copy(update={"range": args.range})  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "app.routers.operator_evidence.evidence_service.get_evidence_summary",
        fake_summary,
    )

    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/summary")

    assert response.status_code == 200
    assert seen["range"] == "24h"


def test_evidence_summary_rejects_an_unknown_range() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/summary?range=90d")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == VALIDATION_ERROR
