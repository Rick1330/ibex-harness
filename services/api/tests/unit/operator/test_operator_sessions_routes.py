"""Mounted-route contract tests for the metadata-only operator session projection."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, VALIDATION_ERROR
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.errors import ApiError
from app.pagination import CursorPage, PaginationMeta
from app.schemas.operator_sessions import OperatorSession, OperatorSessionDetail
from tests.unit.operator.conftest import create_operator_app
from tests.unit.operator.session_fixtures import (
    evidence_record,
    session_detail_record,
    session_record,
    turn_record,
)

PAT = "ibex_pat_operator_sessions"


def _validator(
    org_id: object, permissions: int = OPERATOR_METADATA_READ
) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def test_operator_session_list_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/sessions")
    assert response.status_code == 401


def test_operator_session_list_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/sessions")
    assert response.status_code == 403


def test_operator_session_list_projects_and_forwards_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    session = session_record()
    seen: dict[str, object] = {}

    async def fake_list(_session: object, args: object) -> CursorPage[OperatorSession]:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["agent_id"] = args.filters.agent_id  # type: ignore[attr-defined]
        seen["status"] = args.filters.status  # type: ignore[attr-defined]
        return CursorPage[OperatorSession](
            data=[session], pagination=PaginationMeta(has_more=False)
        )

    monkeypatch.setattr(
        "app.routers.operator_sessions.session_service.list_operator_sessions",
        fake_list,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(
            f"/v1/operator/sessions?agent_id={session.agent_id}&status=active&limit=10"
        )

    assert response.status_code == 200
    assert seen == {
        "org_id": org_id,
        "agent_id": session.agent_id,
        "status": "active",
    }
    body = response.json()
    row = body["data"][0]
    assert row["id"] == str(session.id)
    assert row["turn_count"] == 2
    assert "org_id" not in row
    assert "messages_hash" not in row
    assert "deleted_at" not in row


def test_operator_session_detail_projects_turns_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    evidence = evidence_record()
    detail = session_detail_record(turns=[turn_record(trace=evidence)])

    async def fake_get(
        _session: object, requested_org: object, session_id: object
    ) -> OperatorSessionDetail:
        assert requested_org == org_id
        assert session_id == detail.id
        return detail

    monkeypatch.setattr(
        "app.routers.operator_sessions.session_service.get_operator_session",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/sessions/{detail.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(detail.id)
    assert body["turns"][0]["trace"]["trace_id"] == evidence.trace_id
    assert body["turns"][0]["trace"]["status"] == "ok"
    assert body["turns_truncated"] is False
    assert "messages_hash" not in body


def test_operator_session_detail_returns_not_found_for_another_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()

    async def fake_get(
        _session: object, _org: object, _session_id: object
    ) -> OperatorSessionDetail:
        raise ApiError(code=NOT_FOUND, message="Session not found")

    monkeypatch.setattr(
        "app.routers.operator_sessions.session_service.get_operator_session",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/sessions/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == NOT_FOUND


def test_operator_session_list_rejects_an_oversized_cursor() -> None:
    # AGENTS.md §5.2 requires a length bound on every string input; a direct
    # caller must be capped here, not only in the Console.
    with create_operator_app(validator=_validator(uuid4())) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/sessions", params={"cursor": "c" * 2049})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == VALIDATION_ERROR


def test_operator_session_detail_accepts_the_proxy_model_name_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # services/proxy validation.MaxModelNameLength is 256 and the proxy stores
    # the model unchanged, so a longer saved name must not turn a read into a 500.
    org_id = uuid4()
    model = "m" * 256
    detail = session_detail_record(
        model=model, turns=[turn_record(model=model)]
    )

    async def fake_get(
        _session: object, _org: object, _session_id: object
    ) -> OperatorSessionDetail:
        return detail

    monkeypatch.setattr(
        "app.routers.operator_sessions.session_service.get_operator_session",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/sessions/{detail.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == model
    assert body["turns"][0]["model"] == model
