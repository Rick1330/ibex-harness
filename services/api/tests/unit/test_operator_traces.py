"""Unit coverage for the bounded, tenant-bound D2 metadata read service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR
from authclient.permissions import OPERATOR_METADATA_READ
from sqlalchemy.exc import SQLAlchemyError

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.services.operator_traces import get_operator_trace, list_operator_traces
from tests.unit.operator.conftest import create_operator_app, operator_settings

ORG = uuid4()
START = datetime(2026, 9, 27, 8, tzinfo=UTC)
END = START + timedelta(minutes=2)
RUN = uuid4()


def auth() -> OperatorSessionAuthorization:
    return OperatorSessionAuthorization(org_id=ORG, permissions=1, session_id="s", subject="u")


def row(trace_id: str = "trace-a") -> dict[str, object]:
    return {
        "run_id": RUN,
        "trace_id": trace_id,
        "request_id": "request-a",
        "agent_id": None,
        "session_id": None,
        "checkpoint_id": None,
        "status": "ok",
        "error_code": None,
        "started_at": START,
        "ended_at": END,
        "completeness": "partial",
        "sample_decision": "kept",
    }


def session_for(*rows: dict[str, object]) -> AsyncMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = list(rows)
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


async def assert_api_error(operation: Awaitable[object], code: str) -> ApiError:
    with pytest.raises(ApiError) as error:
        await operation
    assert error.value.code == code
    return error.value


async def assert_list_error(
    code: str,
    *,
    settings=None,
    operator=None,
    session=None,
    **overrides: object,
) -> ApiError:
    values: dict[str, object] = {
        "query_start": START,
        "query_end": END,
        "status": None,
        "limit": 1,
        "cursor": None,
    }
    values.update(overrides)
    return await assert_api_error(
        list_operator_traces(
            session or session_for(),
            settings or operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!"),
            operator or auth(),
            **values,
        ),
        code,
    )


@pytest.mark.asyncio
async def test_list_is_metadata_only_and_binds_org_and_query() -> None:
    session = session_for(row())
    result = await list_operator_traces(
        session,
        operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!"),
        auth(),
        query_start=START - timedelta(hours=1),
        query_end=END + timedelta(hours=1),
        status=None,
        limit=10,
        cursor=None,
    )
    assert result.items[0].trace_id == "trace-a"
    assert result.items[0].duration_ms == 120000
    assert result.items[0].evidence.source == "postgres.evidence_runs"
    assert result.items[0].evidence.source_watermark == "not_provided"
    assert result.items[0].evidence.retention == "unknown"
    query_call = session.execute.await_args_list[-1]
    assert "org_id = :org_id" in str(query_call.args[0])
    assert str(ORG) in repr(query_call.args[1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"query_start": END, "query_end": START},
        {"query_end": START + timedelta(days=8)},
        {"limit": 101},
        {"cursor": "tampered"},
    ],
)
async def test_list_rejects_bad_bounds_and_cursor(overrides: dict[str, object]) -> None:
    settings = operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!")
    await assert_list_error(VALIDATION_ERROR, settings=settings, **overrides)


@pytest.mark.asyncio
async def test_list_uses_signed_cursor_and_rejects_query_replay() -> None:
    settings = operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!")
    first = session_for(row("trace-a"), row("trace-b"))
    first_result = await list_operator_traces(first, settings, auth(), query_start=START, query_end=END, status="ok", limit=1, cursor=None)
    assert first_result.next_cursor
    second = session_for(row("trace-c"))
    await list_operator_traces(second, settings, auth(), query_start=START, query_end=END, status="ok", limit=1, cursor=first_result.next_cursor)
    encoded, signature = first_result.next_cursor.split(".", 1)
    assert signature
    tampered = f"{encoded}.{'0' * 64}"
    payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
    payload["expires_at"] = "2020-01-01T00:00:00+00:00"
    expired_encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    expired_signature = hmac.new(settings.operator_cursor_secret.encode(), expired_encoded.encode(), hashlib.sha256).hexdigest()
    invalid_cursors = [
        (auth(), "error", first_result.next_cursor),
        (OperatorSessionAuthorization(org_id=uuid4(), permissions=1, session_id="s", subject="u"), "ok", first_result.next_cursor),
        (auth(), "ok", tampered),
        (auth(), "ok", f"{expired_encoded}.{expired_signature}"),
    ]
    for operator, status, cursor in invalid_cursors:
        await assert_list_error(
            VALIDATION_ERROR,
            settings=settings,
            session=second,
            operator=operator,
            status=status,
            cursor=cursor,
        )


@pytest.mark.asyncio
async def test_default_cursor_reuses_signed_bounds() -> None:
    settings = operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!")
    first = session_for(row("trace-a"), row("trace-b"))
    first_result = await list_operator_traces(
        first, settings, auth(), query_start=None, query_end=None, status=None, limit=1, cursor=None
    )
    assert first_result.next_cursor
    second = session_for(row("trace-c"))
    second_result = await list_operator_traces(
        second, settings, auth(), query_start=None, query_end=None, status=None, limit=1, cursor=first_result.next_cursor
    )
    assert second_result.query_start == first_result.query_start
    assert second_result.query_end == first_result.query_end


@pytest.mark.asyncio
async def test_list_fails_closed_when_cursor_key_or_database_is_unavailable() -> None:
    await assert_list_error(
        SERVICE_DEGRADED,
        session=session_for(row("trace-a"), row("trace-b")),
        settings=operator_settings(operator_cursor_secret=None),
    )
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("db")
    await assert_list_error(SERVICE_DEGRADED, session=session)


@pytest.mark.asyncio
async def test_detail_is_snapshot_and_foreign_or_missing_is_404() -> None:
    detail = await get_operator_trace(session_for(row()), auth(), trace_id="trace-a")
    assert detail.schema_version == "operator.trace-detail.v1"
    assert "content" in detail.unavailable_sections
    missing = session_for()
    not_found = await assert_api_error(get_operator_trace(missing, auth(), trace_id="foreign"), NOT_FOUND)
    assert not_found.message == "Trace not found"
    await assert_api_error(get_operator_trace(missing, auth(), trace_id=""), NOT_FOUND)
    failed = AsyncMock()
    failed.execute.side_effect = SQLAlchemyError("db")
    await assert_api_error(get_operator_trace(failed, auth(), trace_id="trace-a"), SERVICE_DEGRADED)


@pytest.mark.asyncio
async def test_list_maps_unfinished_and_late_lifecycle_metadata() -> None:
    unfinished = row("trace-open")
    unfinished["ended_at"] = None
    unfinished["completeness"] = "late"
    unfinished["status"] = "failed"
    result = await list_operator_traces(session_for(unfinished), operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!"), auth(), query_start=START, query_end=END, status="error", limit=1, cursor=None)
    assert result.items[0].duration_ms is None
    assert result.items[0].status == "error"
    assert result.items[0].evidence.freshness == "stale"


def test_mounted_d2_routes_require_session_and_return_no_store_metadata() -> None:
    org_id = uuid4()
    validator = StaticTokenValidator({"ibex_pat_test_secret": ValidateResult(org_id=org_id, permissions=OPERATOR_METADATA_READ, user_id="u1")})
    settings = operator_settings(operator_cursor_secret="cursor-secret-32-bytes-minimum!!")
    with create_operator_app(settings=settings, validator=validator) as (app, client):
        assert client.get("/v1/operator/traces").status_code == 401
        app.dependency_overrides[operator_org_session] = lambda: session_for(row())
        assert client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"}).status_code == 200
        response = client.get("/v1/operator/traces?limit=1")
        detail = client.get("/v1/operator/traces/trace-a")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["items"][0]["evidence"]["source"] == "postgres.evidence_runs"
    assert detail.status_code == 200
    assert "content" in detail.json()["unavailable_sections"]
