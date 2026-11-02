"""Mounted-route contract tests for the metadata-only operator directive reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, VALIDATION_ERROR
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.errors import ApiError
from app.pagination import PaginationMeta
from app.schemas.operator_directives import (
    OperatorDirectiveDetail,
    OperatorDirectivePage,
    OperatorDirectiveSummary,
    OperatorDirectiveUsage,
    OperatorDirectiveVersion,
)
from tests.unit.operator.conftest import create_operator_app

PAT = "ibex_pat_operator_directives"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _validator(org_id: object, permissions: int = OPERATOR_METADATA_READ) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def _summary() -> OperatorDirectiveSummary:
    return OperatorDirectiveSummary(
        id=uuid4(),
        agent_id=uuid4(),
        agent_name="Support triage",
        agent_slug="support-triage",
        is_active=True,
        injection_mode="system_first",
        active_version_num=4,
        version_count=6,
        last_version_at=NOW - timedelta(days=1),
        updated_at=NOW,
    )


def _detail() -> OperatorDirectiveDetail:
    summary = _summary()
    return OperatorDirectiveDetail(
        **summary.model_dump(),
        versions=[
            OperatorDirectiveVersion(
                version_num=4,
                content_digest="0123456789ab",
                content_bytes=2048,
                created_by=None,
                created_at=NOW - timedelta(days=1),
                is_live=True,
            )
        ],
        versions_truncated=False,
        usage=[
            OperatorDirectiveUsage(
                version_num=4, sessions=12, last_session_at=NOW - timedelta(hours=1)
            )
        ],
        usage_range="7d",
        usage_window_start=NOW - timedelta(days=7),
        observed_at=NOW,
    )


def test_directive_list_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/directives")
    assert response.status_code == 401


def test_directive_list_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/directives")
    assert response.status_code == 403


def test_directive_list_projects_and_forwards_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()
    agent_id = uuid4()
    seen: dict[str, object] = {}

    async def fake_list(_session: object, args: object) -> OperatorDirectivePage:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["state"] = args.state  # type: ignore[attr-defined]
        seen["agent_id"] = args.agent_id  # type: ignore[attr-defined]
        return OperatorDirectivePage(
            data=[_summary()], pagination=PaginationMeta(has_more=False), observed_at=NOW
        )

    monkeypatch.setattr(
        "app.routers.operator_directives.directive_service.list_operator_directives",
        fake_list,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(
            f"/v1/operator/directives?state=active&agent_id={agent_id}&limit=10"
        )

    assert response.status_code == 200
    assert seen == {"org_id": org_id, "state": "active", "agent_id": agent_id}
    body = response.json()
    row = body["data"][0]
    assert row["active_version_num"] == 4
    assert row["version_count"] == 6
    assert "content" not in row
    assert "org_id" not in row


def test_directive_detail_projects_versions_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()
    directive = _detail()
    seen: dict[str, object] = {}

    async def fake_get(_session: object, args: object) -> OperatorDirectiveDetail:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["directive_id"] = args.directive_id  # type: ignore[attr-defined]
        seen["range"] = args.usage_range  # type: ignore[attr-defined]
        return directive.model_copy(update={"usage_range": args.usage_range})  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "app.routers.operator_directives.directive_service.get_operator_directive",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/directives/{directive.id}?range=30d")

    assert response.status_code == 200
    body = response.json()
    assert body["versions"][0]["is_live"] is True
    assert body["versions"][0]["content_digest"] == "0123456789ab"
    assert body["usage"][0]["sessions"] == 12
    assert body["usage_range"] == "30d"
    assert seen == {"org_id": org_id, "directive_id": directive.id, "range": "30d"}


def test_directive_detail_returns_not_found_for_another_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(_session: object, _args: object) -> OperatorDirectiveDetail:
        raise ApiError(code=NOT_FOUND, message="Directive not found")

    monkeypatch.setattr(
        "app.routers.operator_directives.directive_service.get_operator_directive",
        fake_get,
    )

    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/directives/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == NOT_FOUND


def test_directive_routes_reject_unknown_filters() -> None:
    org_id = uuid4()
    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        bad_state = client.get("/v1/operator/directives?state=draining")
        bad_range = client.get(f"/v1/operator/directives/{uuid4()}?range=90d")

    assert bad_state.status_code == 400
    assert bad_state.json()["error"]["code"] == VALIDATION_ERROR
    assert bad_range.status_code == 400
    assert bad_range.json()["error"]["code"] == VALIDATION_ERROR
