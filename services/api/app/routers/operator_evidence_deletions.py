"""Authenticated, metadata-only deletion evidence route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_evidence_deletions import (
    OperatorEvidenceDeletions,
    OperatorEvidenceDeletionsQuery,
)
from app.services import operator_evidence_deletions as deletion_service
from app.services.operator_evidence_deletions import DeletionArgs

router = APIRouter(prefix="/v1/operator/evidence", tags=["operator-evidence"])

OperatorSessionAuth = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("/deletions")
async def operator_evidence_deletions(
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorEvidenceDeletionsQuery, Query()],
) -> OperatorEvidenceDeletions:
    return await deletion_service.get_evidence_deletions(
        session,
        DeletionArgs(org_id=operator.org_id, range=query.range),
    )
