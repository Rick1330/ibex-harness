"""Coverage gap tests for m4.A.2 management API paths."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR
from authclient.errors import AuthUnavailableError
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.errors import ApiError
from app.main import _make_celery_enqueue, create_app
from app.pagination import decode_cursor, page_from_rows
from app.revocation_publish import RedisOrgSuspendPublisher
from app.schemas.organizations import OrganizationPatch, OrganizationResponse
from app.schemas.users import UserCreate
from app.services import organizations as org_service
from app.services import users as user_service
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    managed_org_client,
)
from tests.unit.test_organizations_service import _MapResult, _org
from tests.unit.test_users_service import _ScalarResult, _user


def test_decode_cursor_rejects_non_object() -> None:
    raw = base64.urlsafe_b64encode(b"[1,2]").decode("ascii").rstrip("=")
    with pytest.raises(TypeError, match="invalid cursor"):
        decode_cursor(raw)


def test_page_from_rows_edge_branches() -> None:
    assert page_from_rows([], limit=2, next_cursor="x").pagination.next_cursor is None
    page = page_from_rows([1, 2, 3], limit=2, next_cursor=None)
    assert page.pagination.has_more is True
    assert page.pagination.next_cursor is None


def test_organization_settings_bounds() -> None:
    assert OrganizationPatch(settings=None).settings is None
    with pytest.raises(ValidationError):
        OrganizationPatch(settings={f"k{i}": i for i in range(51)})
    with pytest.raises(ValidationError):
        OrganizationPatch(settings={"blob": "x" * 9000})
    now = datetime.now(UTC)
    OrganizationResponse(
        id=uuid4(),
        name="n",
        slug="s",
        tier="free",
        status="active",
        settings={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_user_invite_happy_path() -> None:
    org_id = uuid4()
    row = _user(org_id=org_id, status="invited")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(row), MagicMock()])
    session.commit = AsyncMock()
    out = await user_service.create_user_invite(
        session,
        org_id,
        UserCreate(email="New@Example.com", name="N", role="member"),
        created_by=uuid4(),
    )
    assert out.invite_token
    assert out.email == row.email


@pytest.mark.asyncio
async def test_list_users_invalid_cursor_payload() -> None:
    from app.pagination import encode_cursor

    session = AsyncMock()
    bad = encode_cursor({"created_at": "2026-01-01T00:00:00+00:00"})
    with pytest.raises(ApiError) as exc:
        await user_service.list_users(session, uuid4(), cursor=bad, limit=10)
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_list_users_non_object_cursor_maps_type_error() -> None:
    import base64

    session = AsyncMock()
    bad = base64.urlsafe_b64encode(b"[1,2]").decode("ascii").rstrip("=")
    with pytest.raises(ApiError) as exc:
        await user_service.list_users(session, uuid4(), cursor=bad, limit=10)
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_patch_user_update_race_not_found() -> None:
    from app.schemas.users import UserPatch

    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(current), _ScalarResult(None)])
    patch = UserPatch(name="x")
    args = user_service.PatchUserArgs(
        org_id=org_id, user_id=user_id, patch=patch, caller_role="owner"
    )
    with pytest.raises(ApiError) as exc:
        await user_service.patch_user(session, args)
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_soft_delete_rowcount_zero() -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(current),
            _ScalarResult([]),
            MagicMock(rowcount=0),
        ]
    )
    session.rollback = AsyncMock()
    revoke = user_service.RevokeContext(revoker=AsyncMock(), access_token="t")
    with pytest.raises(ApiError) as exc:
        await user_service.soft_delete_user(session, org_id, user_id, revoke)
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_soft_delete_unavailable_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()
    user_id = uuid4()
    current = _user(id=user_id, org_id=org_id, role="member")
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_ScalarResult(current), _ScalarResult([SimpleNamespace(id="t1")])]
    )
    session.rollback = AsyncMock()
    revoker = AsyncMock()
    revoker.revoke = AsyncMock(side_effect=AuthUnavailableError())
    monkeypatch.setattr(user_service.asyncio, "sleep", AsyncMock())
    revoke = user_service.RevokeContext(revoker=revoker, access_token="t")
    with pytest.raises(AuthUnavailableError):
        await user_service.soft_delete_user(session, org_id, user_id, revoke)
    session.rollback.assert_awaited()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_suspend_race_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    publisher = AsyncMock()
    org_id = uuid4()
    with pytest.raises(ApiError):
        await org_service.suspend_organization(session, org_id, publisher)


@pytest.mark.asyncio
async def test_patch_org_race_not_found() -> None:
    current = _org()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(current), _MapResult(None)])
    patch = OrganizationPatch(name="x")
    with pytest.raises(ApiError):
        await org_service.patch_organization(session, current.id, patch)


@pytest.mark.asyncio
async def test_enqueue_job_missing_after_insert() -> None:
    org_id = uuid4()
    current = _org(id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(current), _MapResult(None)])
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    with pytest.raises(ApiError) as exc:
        await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=lambda *_: None)
    assert exc.value.code == VALIDATION_ERROR


def test_suspend_requires_publisher() -> None:
    _assert_org_runtime_dependency_503("org_suspend_publisher", "post", "/suspend")


def test_delete_org_requires_enqueue() -> None:
    _assert_org_runtime_dependency_503("enqueue_org_deletion", "delete", "")


def _assert_org_runtime_dependency_503(attr: str, method: str, path_suffix: str) -> None:
    org_id = uuid4()
    with managed_org_client(ManagedClientOpts(org_id=org_id, role="owner")) as (
        client,
        _res,
        _pub,
    ):
        setattr(client.app.state.api, attr, None)
        call = getattr(client, method)
        resp = call(
            f"/v1/organizations/{org_id}{path_suffix}",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == SERVICE_DEGRADED


def test_make_celery_enqueue_sends_task() -> None:
    sent: list[tuple] = []

    class _Celery:
        def __init__(self, *_a, **_k):
            pass

        def send_task(self, name, args=None, queue=None):
            sent.append((name, args, queue))

    with patch("celery.Celery", _Celery):
        enqueue = _make_celery_enqueue("redis://localhost:6379/0")
        enqueue("job-1", "org-1")
    assert sent == [("ibex.worker.org.delete_organization", ["job-1", "org-1"], "maintenance")]


def test_lifespan_wires_redis_publisher_and_closes() -> None:
    settings = Settings(
        database_url=None,
        redis_url="redis://localhost:6379/0",
        celery_broker_url="redis://localhost:6379/1",
    )
    validator = StaticTokenValidator({}, available=True)
    closer = AsyncMock()
    pub = MagicMock()
    pub.aclose = closer

    with (
        patch("app.main.RedisOrgSuspendPublisher", return_value=pub),
        patch("app.main._make_celery_enqueue", return_value=lambda *_: None),
        patch("authclient.revoke.GRPCTokenRevoker") as revoker_cls,
    ):
        revoker = MagicMock()
        revoker.aclose = AsyncMock()
        revoker_cls.return_value = revoker
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 503
            assert app.state.api.org_suspend_publisher is pub
    closer.assert_awaited()
    revoker.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_redis_publisher_success_and_get_client(monkeypatch: pytest.MonkeyPatch) -> None:
    pub = RedisOrgSuspendPublisher("redis://localhost:6379/0")
    published: list[str] = []

    class _Client:
        async def publish(self, channel, payload):
            published.append(payload)
            return 1

        async def aclose(self):
            return None

    client = _Client()
    monkeypatch.setattr(pub, "_get_client", lambda: client)
    await pub.publish_org_suspend("org-1")
    assert published
    pub._client = client
    await pub.aclose()
    assert pub._client is None


@pytest.mark.asyncio
async def test_redis_get_client_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    pub = RedisOrgSuspendPublisher("redis://localhost:6379/0")

    class _Redis:
        @staticmethod
        def from_url(url, decode_responses=False):
            assert url == "redis://localhost:6379/0"
            return "client"

    import sys
    import types

    fake_asyncio = types.SimpleNamespace(Redis=_Redis)
    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = fake_asyncio
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)
    assert pub._get_client() == "client"
    assert pub._get_client() == "client"
