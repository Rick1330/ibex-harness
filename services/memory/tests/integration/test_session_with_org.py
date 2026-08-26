"""session_with_org GUC behavior against live Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_session_with_org_sets_local_org_guc(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = str(uuid4())
    async with session_with_org(session_factory, org_id) as session:
        row = await session.execute(
            text("SELECT current_setting('app.current_org_id', true)")
        )
        assert row.scalar_one() == org_id

    async with session_factory() as session, session.begin():
        row = await session.execute(
            text("SELECT current_setting('app.current_org_id', true)")
        )
        assert row.scalar_one() in (None, "")
