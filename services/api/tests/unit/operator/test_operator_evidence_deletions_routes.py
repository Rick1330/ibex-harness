"""Mounted-route contract tests for the metadata-only deletion evidence read."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import VALIDATION_ERROR
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.schemas.operator_evidence_deletions import (
    AuditChainSummary,
    ErasureJob,
    ErasureStatusCounts,
    OperatorEvidenceDeletions,
    StoreReceipt,
    TombstoneEventCounts,
    TombstoneSummary,
)
from tests.unit.operator.conftest import create_operator_app

PAT = "ibex_pat_operator_deletions"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _validator(org_id: object, permissions: int = OPERATOR_METADATA_READ) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def _summary() -> OperatorEvidenceDeletions:
    return OperatorEvidenceDeletions(
        range="7d",
        window_start=NOW - timedelta(days=7),
        window_end=NOW,
        observed_at=NOW,
        tombstones=TombstoneSummary(
            events=TombstoneEventCounts(forgotten=3, expired=1, purged=1),
            pending=2,
            oldest_pending_at=NOW - timedelta(hours=1),
            last_event_at=NOW,
            tombstoned_memories=9,
        ),
        erasures=ErasureStatusCounts(succeeded=1, hold_blocked=1),
        jobs=[
            ErasureJob(
                id=str(uuid4()),
                status="hold_blocked",
                created_at=NOW,
                finished_at=None,
                receipts=[
                    StoreReceipt(store="postgres", status="verified", verified_absent_at=NOW),
                    StoreReceipt(store="redis", status="pending", verified_absent_at=None),
                ],
            )
        ],
        jobs_truncated=False,
        audit=AuditChainSummary(
            entries=4,
            first_seq=1,
            last_seq=4,
            continuity_ok=True,
            broken_at_seq=None,
            last_row_hash="a" * 64,
        ),
    )


def test_deletion_evidence_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/evidence/deletions")
    assert response.status_code == 401


def test_deletion_evidence_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/evidence/deletions")
    assert response.status_code == 403


def test_deletion_evidence_projects_the_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()
    seen: dict[str, object] = {}

    async def fake_summary(_session: object, args: object) -> OperatorEvidenceDeletions:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["range"] = args.range  # type: ignore[attr-defined]
        return _summary()

    monkeypatch.setattr(
        "app.routers.operator_evidence_deletions.deletion_service.get_evidence_deletions",
        fake_summary,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/deletions?range=7d")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "operator.evidence.deletions.v1"
    assert body["tombstones"]["events"]["forgotten"] == 3
    assert body["tombstones"]["tombstoned_memories"] == 9
    assert body["erasures"]["hold_blocked"] == 1
    assert body["jobs"][0]["receipts"][1] == {
        "store": "redis",
        "status": "pending",
        "verified_absent_at": None,
    }
    assert body["audit"]["continuity_ok"] is True
    # Payload and hold reason are not part of the contract at all.
    assert "payload" not in body["audit"]
    assert "reason" not in body["erasures"]
    assert seen == {"org_id": org_id, "range": "7d"}


def test_deletion_evidence_defaults_to_a_24h_window(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake_summary(_session: object, args: object) -> OperatorEvidenceDeletions:
        seen["range"] = args.range  # type: ignore[attr-defined]
        return _summary().model_copy(update={"range": args.range})  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "app.routers.operator_evidence_deletions.deletion_service.get_evidence_deletions",
        fake_summary,
    )

    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/deletions")

    assert response.status_code == 200
    assert seen["range"] == "24h"


def test_deletion_evidence_rejects_an_unknown_range() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/evidence/deletions?range=90d")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == VALIDATION_ERROR
