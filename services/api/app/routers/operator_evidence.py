"""Authenticated, metadata-only operator evidence routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_evidence import OperatorEvidenceSummary, OperatorEvidenceSummaryQuery
from app.services import operator_evidence as evidence_service
from app.services.operator_evidence import EvidenceSummaryArgs

router = APIRouter(prefix="/v1/operator/evidence", tags=["operator-evidence"])

OperatorSessionAuth = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("/summary")
async def operator_evidence_summary(
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorEvidenceSummaryQuery, Query()],
) -> OperatorEvidenceSummary:
    return await evidence_service.get_evidence_summary(
        session,
        EvidenceSummaryArgs(org_id=operator.org_id, range=query.range),
    )
