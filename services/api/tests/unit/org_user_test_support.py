"""Shared helpers for org/user management API unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from authclient.permissions import ADMIN, USER_MANAGE
from authclient.revoke import NoopTokenRevoker
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import ApiRuntimeOverrides, create_app
from app.revocation_publish import RecordingOrgSuspendPublisher


def owner_result(*, org_id: UUID | None = None, user_id: str | None = None) -> ValidateResult:
    return ValidateResult(
        org_id=org_id or uuid4(),
        permissions=ADMIN | USER_MANAGE,
        user_id=user_id or str(uuid4()),
    )


@contextmanager
def api_client(
    *,
    token: str = "owner-token",
    result: ValidateResult | None = None,
    publisher: RecordingOrgSuspendPublisher | None = None,
    enqueue_calls: list[tuple[str, str]] | None = None,
) -> Iterator[tuple[TestClient, ValidateResult, RecordingOrgSuspendPublisher]]:
    res = result or owner_result()
    pub = publisher or RecordingOrgSuspendPublisher()
    calls = enqueue_calls if enqueue_calls is not None else []

    def _enqueue(job_id: str, org_id: str) -> None:
        calls.append((job_id, org_id))

    settings = Settings(database_url=None)
    app = create_app(
        settings=settings,
        validator=StaticTokenValidator({token: res}),
        runtime=ApiRuntimeOverrides(
            token_revoker=NoopTokenRevoker(),
            org_suspend_publisher=pub,
            enqueue_org_deletion=_enqueue,
        ),
    )
    with TestClient(app) as client:
        yield client, res, pub


def sample_org_row(org_id: UUID, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    base = {
        "id": org_id,
        "name": "Acme",
        "slug": "acme",
        "tier": "free",
        "status": "active",
        "billing_email": "billing@example.com",
        "settings": {},
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


def sample_user_row(org_id: UUID, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "org_id": org_id,
        "email": "user@example.com",
        "name": "User",
        "role": "member",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base
