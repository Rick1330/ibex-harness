"""Unit tests for D1 operator context and Overview read contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
from authclient.permissions import OPERATOR_METADATA_READ
from pydantic import ValidationError

from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.routers.operator_overview import require_operator_metadata_session
from app.schemas.operator_overview import OperatorContextResponse, OperatorOverviewResponse
from app.services.operator_overview import get_operator_d1_read_model


def _authorization(*, permissions: int = OPERATOR_METADATA_READ) -> OperatorSessionAuthorization:
    return OperatorSessionAuthorization(
        org_id=uuid4(),
        permissions=permissions,
        session_id="session-d1-test",
        subject=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_read_model_binds_verified_org_and_returns_real_bounded_counts() -> None:
    authorization = _authorization()
    row = {
        "org_id": authorization.org_id,
        "org_name": "Example workspace",
        "org_slug": "example",
        "org_status": "active",
        "role": "admin",
        "active_users": 3,
        "agents": 7,
        "active_agents": 4,
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    context, overview = await get_operator_d1_read_model(session, authorization)

    assert context.org_id == authorization.org_id
    assert context.org_name == "Example workspace"
    assert context.role == "admin"
    assert set(context.model_dump()) == {
        "schema_version",
        "org_id",
        "role",
        "org_name",
        "org_slug",
        "org_status",
        "observed_at",
    }
    assert overview.counts.model_dump() == {
        "active_users": 3,
        "agents": 7,
        "active_agents": 4,
    }
    assert overview.completeness == "complete"
    assert context.observed_at.tzinfo == UTC
    args, kwargs = session.execute.await_args
    assert str(authorization.org_id) in repr(args) + repr(kwargs)
    assert "organizations" in str(args[0])
    assert "agents" in str(args[0])
    assert "deleted_at IS NULL" in str(args[0])


@pytest.mark.asyncio
async def test_unmapped_external_subject_has_no_inferred_database_role() -> None:
    authorization = OperatorSessionAuthorization(
        org_id=uuid4(), permissions=OPERATOR_METADATA_READ, session_id="s", subject="external-sub"
    )
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "org_id": authorization.org_id,
        "org_name": "Example workspace",
        "org_slug": "example",
        "org_status": "active",
        "role": None,
        "active_users": 0,
        "agents": 0,
        "active_agents": 0,
    }
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    context, overview = await get_operator_d1_read_model(session, authorization)

    assert context.role is None
    assert overview.counts.active_users == 0
    assert session.execute.await_args.args[1]["subject_id"] is None


@pytest.mark.asyncio
async def test_read_model_rejects_a_row_from_another_org() -> None:
    authorization = _authorization()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "org_id": uuid4(),
        "org_name": "Other tenant",
        "org_slug": "other-tenant",
        "org_status": "active",
        "role": None,
        "active_users": 1,
        "agents": 1,
        "active_agents": 1,
    }
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(ApiError) as error:
        await get_operator_d1_read_model(session, authorization)

    assert error.value.code == NOT_FOUND
    assert "Other tenant" not in str(error.value)


def test_context_and_overview_dtos_reject_extra_or_unversioned_fields() -> None:
    observed = datetime.now(UTC)
    context = {
        "schema_version": "operator.context.v1",
        "org_id": str(uuid4()),
        "role": None,
        "org_name": "Example",
        "org_slug": "example",
        "org_status": "active",
        "observed_at": observed,
    }
    OperatorContextResponse.model_validate(context)
    with pytest.raises(ValidationError):
        OperatorContextResponse.model_validate({**context, "access_token": "secret"})

    overview = {
        "schema_version": "operator.overview.v1",
        "org_id": str(uuid4()),
        "org_name": "Example",
        "org_slug": "example",
        "org_status": "active",
        "counts": {"active_users": 0, "agents": 0, "active_agents": 0},
        "observed_at": observed,
        "completeness": "complete",
    }
    OperatorOverviewResponse.model_validate(overview)
    with pytest.raises(ValidationError):
        OperatorOverviewResponse.model_validate({**overview, "estimated_cost_usd": 0})


def test_metadata_permission_is_required() -> None:
    request = MagicMock()
    request.app.state.settings = MagicMock(operator_feature_enabled=True)
    operator = _authorization(permissions=0)
    with pytest.raises(ApiError) as exc:
        require_operator_metadata_session(request, operator)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


@pytest.mark.asyncio
async def test_read_model_maps_sqlalchemy_errors_to_service_degraded() -> None:
    from apierror_py import SERVICE_DEGRADED
    from sqlalchemy.exc import OperationalError

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=OperationalError("stmt", {}, Exception("db down"))
    )
    with pytest.raises(ApiError) as error:
        await get_operator_d1_read_model(session, _authorization())
    assert error.value.code == SERVICE_DEGRADED


@pytest.mark.asyncio
async def test_read_model_rejects_missing_org_row() -> None:
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    with pytest.raises(ApiError) as error:
        await get_operator_d1_read_model(session, _authorization())
    assert error.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_read_model_maps_malformed_org_id_to_service_degraded() -> None:
    from apierror_py import SERVICE_DEGRADED

    authorization = _authorization()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "org_name": "Broken",
        "org_slug": "broken",
        "org_status": "active",
        "role": "admin",
        "active_users": 0,
        "agents": 0,
        "active_agents": 0,
        "org_id": "not-a-uuid",
    }
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    with pytest.raises(ApiError) as error:
        await get_operator_d1_read_model(session, authorization)
    assert error.value.code == SERVICE_DEGRADED


@pytest.mark.asyncio
async def test_read_model_ignores_disallowed_roles() -> None:
    authorization = _authorization()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "org_id": authorization.org_id,
        "org_name": "Example workspace",
        "org_slug": "example",
        "org_status": "active",
        "role": "superuser",
        "active_users": 1,
        "agents": 1,
        "active_agents": 1,
    }
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    context, _ = await get_operator_d1_read_model(session, authorization)
    assert context.role is None
