"""Authenticated, read-only D1 operator context and Overview routes."""

from __future__ import annotations

from typing import Annotated

from authclient.permissions import OPERATOR_METADATA_READ
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import assert_operator_permission
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization, require_operator_session
from app.schemas.operator_overview import OperatorContextResponse, OperatorOverviewResponse
from app.services.operator_overview import get_operator_d1_read_model

router = APIRouter(prefix="/v1/operator", tags=["operator-overview"])
OperatorSession = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


def require_operator_metadata_session(
    request: Request,
    operator: OperatorSession,
) -> OperatorSessionAuthorization:
    assert_operator_permission(
        request.app.state.settings,
        operator.permissions,
        OPERATOR_METADATA_READ,
    )
    return operator


async def _read_d1(
    operator: OperatorSession,
    session: OperatorSessionDatabase,
) -> tuple[OperatorContextResponse, OperatorOverviewResponse]:
    return await get_operator_d1_read_model(session, operator)


@router.get("/context")
async def operator_context(
    operator: Annotated[
        OperatorSessionAuthorization,
        Depends(require_operator_metadata_session),
    ],
    session: OperatorSessionDatabase,
) -> OperatorContextResponse:
    context, _ = await _read_d1(operator, session)
    return context


@router.get("/overview")
async def operator_overview(
    operator: Annotated[
        OperatorSessionAuthorization,
        Depends(require_operator_metadata_session),
    ],
    session: OperatorSessionDatabase,
) -> OperatorOverviewResponse:
    _, overview = await _read_d1(operator, session)
    return overview
