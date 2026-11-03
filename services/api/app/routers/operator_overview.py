"""Authenticated, read-only D1 operator context and Overview routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_overview import OperatorContextResponse, OperatorOverviewResponse
from app.services.operator_overview import get_operator_d1_read_model

router = APIRouter(prefix="/v1/operator", tags=["operator-overview"])
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


async def _read_d1(
    operator: OperatorSessionAuthorization,
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
