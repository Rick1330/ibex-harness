"""Unit coverage for the bounded, tenant-bound D2 metadata read service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Awaitable
from dataclasses import dataclass
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
from app.schemas.operator_traces import OperatorTraceListQuery
from app.services.operator_traces import (
    get_operator_trace,
    get_operator_trace_run,
    list_operator_trace_runs,
    list_operator_traces,
)
from app.services.operator_traces_publication import map_publication, publication_for_requests
from tests.unit.operator.conftest import create_operator_app, operator_settings

ORG = uuid4()
START = datetime(2026, 9, 27, 8, tzinfo=UTC)
END = START + timedelta(minutes=2)
RUN = uuid4()
CURSOR_SECRET = "cursor-secret-32-bytes-minimum!!"


def auth() -> OperatorSessionAuthorization:
    return OperatorSessionAuthorization(org_id=ORG, permissions=1, session_id="s", subject="u")


def cursor_settings(**overrides: object):
    values: dict[str, object] = {"operator_cursor_secret": CURSOR_SECRET}
    values.update(overrides)
    return operator_settings(**values)


def row(trace_id: str = "trace-a", *, request_id: str = "request-a", run_id=None) -> dict[str, object]:
    return {
        "run_id": run_id or RUN,
        "trace_id": trace_id,
        "request_id": request_id,
        "agent_id": None,
        "session_id": None,
        "checkpoint_id": None,
        "schema_version": "evidence.v1",
        "status": "ok",
        "error_code": None,
        "capture_mode": "metadata",
        "started_at": START,
        "ended_at": END,
        "completeness": "partial",
        "sample_decision": "kept",
    }


def outbox_row(
    request_id: str = "request-a",
    *,
    status: str = "delivered",
    seq: int = 1,
) -> dict[str, object]:
    return {
        "aggregate_id": request_id,
        "aggregate_seq": seq,
        "delivery_status": status,
        "created_at": START,
        "delivered_at": END if status == "delivered" else None,
    }


@dataclass(frozen=True)
class SessionFixtures:
    outbox: list[dict[str, object]] | None = None
    count: int | None = None
    spans: list[dict[str, object]] | None = None
    assembly: dict[str, object] | None = None
    candidates: list[dict[str, object]] | None = None
    directive: dict[str, object] | None = None
    tools: list[dict[str, object]] | None = None


def _mapping_result(rows: list[dict[str, object]], *, scalar: object | None = None) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    if scalar is not None:
        result.scalar_one.return_value = scalar
    return result


def _route_sql(
    sql: str,
    *,
    run_rows: list[dict[str, object]],
    matched: int,
    table_rows: dict[str, list[dict[str, object]]],
) -> MagicMock:
    if "set_config" in sql:
        return _mapping_result([], scalar="ok")
    if "count(" in sql.replace(" ", ""):
        return _mapping_result([], scalar=matched)
    for marker, marker_rows in table_rows.items():
        if marker in sql:
            return _mapping_result(marker_rows)
    return _mapping_result(run_rows, scalar=matched)


def session_for(*rows: dict[str, object], fixtures: SessionFixtures | None = None) -> AsyncMock:
    """Route mock execute results by SQL shape (list / count / outbox / child)."""
    seed = fixtures or SessionFixtures()
    run_rows = list(rows)
    matched = seed.count if seed.count is not None else len(run_rows)
    table_rows = {
        "evidence_outbox": list(seed.outbox or ()),
        "evidence_spans": list(seed.spans or ()),
        "evidence_assembly": [seed.assembly] if seed.assembly is not None else [],
        "evidence_score": list(seed.candidates or ()),
        "evidence_directive": [seed.directive] if seed.directive is not None else [],
        "evidence_tool": list(seed.tools or ()),
    }

    async def _execute(query, params=None):
        return _route_sql(str(query).lower(), run_rows=run_rows, matched=matched, table_rows=table_rows)

    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=None)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.begin_nested = MagicMock(return_value=nested)
    return session


async def assert_api_error(operation: Awaitable[object], code: str) -> ApiError:
    with pytest.raises(ApiError) as error:
        await operation
    assert error.value.code == code
    return error.value


async def list_call(
    session: AsyncMock,
    settings,
    operator: OperatorSessionAuthorization | None = None,
    **overrides: object,
) -> object:
    values: dict[str, object] = {
        "started_after": START,
        "started_before": END,
        "status": None,
        "limit": 1,
        "cursor": None,
    }
    values.update(overrides)
    query = OperatorTraceListQuery.model_construct(**values)
    return await list_operator_traces(session, settings, operator or auth(), query)


async def assert_list_error(code: str, **kwargs: object) -> ApiError:
    settings = kwargs.pop("settings", None) or cursor_settings()
    operator = kwargs.pop("operator", None)
    session = kwargs.pop("session", None) or session_for()
    return await assert_api_error(list_call(session, settings, operator, **kwargs), code)


async def first_page_with_cursor(
    settings,
    *,
    status: str | None = None,
    started_after: datetime | None = START,
    started_before: datetime | None = END,
) -> object:
    first = session_for(row("trace-a"), row("trace-b", run_id=uuid4(), request_id="request-b"))
    result = await list_call(
        first,
        settings,
        auth(),
        started_after=started_after,
        started_before=started_before,
        status=status,
        limit=1,
        cursor=None,
    )
    assert result.next_cursor
    return result


@pytest.mark.asyncio
async def test_list_is_metadata_only_and_binds_org_and_query() -> None:
    session = session_for(row(), fixtures=SessionFixtures(outbox=[outbox_row()]))
    result = await list_call(
        session,
        cursor_settings(),
        auth(),
        started_after=START - timedelta(hours=1),
        started_before=END + timedelta(hours=1),
        status=None,
        limit=10,
        cursor=None,
    )
    assert result.items[0].trace_id == "trace-a"
    assert result.items[0].duration_ms == 120000
    assert result.items[0].evidence.source == "postgres.evidence_runs"
    assert result.items[0].evidence.schema_version == "evidence.v1"
    assert result.items[0].evidence.capture_mode == "metadata"
    assert result.items[0].evidence.publication_state == "published"
    assert result.items[0].evidence.source_watermark == "outbox:1"
    assert result.items[0].evidence.retention == "unknown"
    assert result.returned_count == 1
    assert result.matched_count == 1
    assert result.query_grammar_version == "operator.trace-query.v1"


@pytest.mark.asyncio
async def test_list_publication_unavailable_without_outbox() -> None:
    result = await list_call(session_for(row()), cursor_settings(), auth(), limit=10)
    assert result.items[0].evidence.publication_state == "unavailable"
    assert result.items[0].evidence.source_watermark == "not_provided"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", "pending"),
        ("in_flight", "pending"),
        ("failed", "failed"),
        ("poison", "poison"),
    ],
)
async def test_list_maps_outbox_publication_states(status: str, expected: str) -> None:
    result = await list_call(
        session_for(row(), fixtures=SessionFixtures(outbox=[outbox_row(status=status)])),
        cursor_settings(),
        auth(),
        limit=10,
    )
    assert result.items[0].evidence.publication_state == expected
    assert result.items[0].evidence.source_watermark == "not_provided"


@pytest.mark.asyncio
async def test_list_maps_partial_publication_when_delivered_and_pending_mix() -> None:
    result = await list_call(
        session_for(
            row(),
            fixtures=SessionFixtures(
                outbox=[
                    outbox_row(status="delivered", seq=2),
                    outbox_row(status="pending", seq=1),
                ],
            ),
        ),
        cursor_settings(),
        auth(),
        limit=10,
    )
    assert result.items[0].evidence.publication_state == "partial"
    assert result.items[0].evidence.source_watermark == "outbox:2"
    assert result.items[0].evidence.ingestion_lag_ms is not None
    assert result.items[0].evidence.ingestion_lag_ms >= 120_000


@pytest.mark.asyncio
async def test_watermark_uses_delivered_seq_only_when_pending_is_higher() -> None:
    result = await list_call(
        session_for(
            row(),
            fixtures=SessionFixtures(
                outbox=[
                    outbox_row(status="delivered", seq=1),
                    outbox_row(status="pending", seq=2),
                ],
            ),
        ),
        cursor_settings(),
        auth(),
        limit=10,
    )
    assert result.items[0].evidence.publication_state == "partial"
    assert result.items[0].evidence.source_watermark == "outbox:1"
    assert result.items[0].evidence.ingestion_lag_ms is not None


@pytest.mark.asyncio
async def test_list_maps_partial_when_failed_mixes_with_pending() -> None:
    result = await list_call(
        session_for(
            row(),
            fixtures=SessionFixtures(
                outbox=[
                    outbox_row(status="failed", seq=2),
                    outbox_row(status="pending", seq=1),
                ],
            ),
        ),
        cursor_settings(),
        auth(),
        limit=10,
    )
    assert result.items[0].evidence.publication_state == "partial"


def _hydrated_child_fixtures() -> SessionFixtures:
    memory_id = uuid4()
    return SessionFixtures(
        outbox=[outbox_row()],
        spans=[
            {
                "span_id": "span-1",
                "parent_span_id": None,
                "operation_kind": "llm",
                "status": "ok",
                "error_code": None,
                "started_at": START,
                "ended_at": END,
            }
        ],
        assembly={
            "budget_calculation_ms": 1,
            "directive_load_ms": 2,
            "hot_memory_retrieval_ms": 3,
            "cold_memory_retrieval_ms": 4,
            "ranking_ms": 5,
            "packing_ms": 6,
            "formatting_ms": 7,
            "total_ms": 28,
            "candidates_evaluated": 9,
        },
        candidates=[
            {
                "memory_id": memory_id,
                "retrieval_rank": 1,
                "final_rank": 1,
                "delta_rank": 0,
                "category": "fact",
                "token_estimate": 12,
                "exclusion": "kept",
                "score_schema": "interim_v1",
                "composite_score": 0.9,
            }
        ],
        directive={
            "directive_version_id": uuid4(),
            "content_hash": "abc",
            "schema_version": "directive.v1",
        },
        tools=[
            {
                "tool_name": "search",
                "status": "ok",
                "error_code": None,
                "created_at": START,
            }
        ],
    )


@pytest.mark.asyncio
async def test_run_detail_hydrates_child_sections_and_interim_score_note() -> None:
    detail = await get_operator_trace_run(
        session_for(row(), fixtures=_hydrated_child_fixtures()),
        auth(),
        run_id=RUN,
    )
    assert len(detail.spans) == 1
    assert detail.assembly is not None
    assert detail.assembly.total_ms == 28
    assert len(detail.candidates) == 1
    assert detail.score_schema_note is not None
    assert "interim_v1" in detail.score_schema_note
    assert "score_explanation" in detail.unavailable_sections
    assert detail.directive is not None
    assert detail.directive.content_hash == "abc"
    assert len(detail.tools) == 1
    assert "content" in detail.unavailable_sections
    assert "spans" not in detail.unavailable_sections


@pytest.mark.asyncio
async def test_run_detail_marks_missing_children_unavailable() -> None:
    detail = await get_operator_trace_run(session_for(row()), auth(), run_id=RUN)
    for section in ("spans", "assembly", "candidates", "score_explanation", "directives", "tools"):
        assert section in detail.unavailable_sections


@pytest.mark.asyncio
async def test_list_rejects_empty_and_overlong_trace_id_for_runs() -> None:
    await assert_api_error(list_operator_trace_runs(session_for(), auth(), trace_id=""), NOT_FOUND)
    await assert_api_error(
        list_operator_trace_runs(session_for(), auth(), trace_id="x" * 257),
        NOT_FOUND,
    )
    await assert_api_error(
        list_operator_trace_runs(session_for(row()), auth(), trace_id="trace-a", limit=0),
        VALIDATION_ERROR,
    )


@pytest.mark.asyncio
async def test_list_applies_equality_filters_without_error() -> None:
    session = session_for(row())
    result = await list_call(
        session,
        cursor_settings(),
        auth(),
        limit=10,
        trace_id="trace-a",
        request_id="request-a",
        run_id=RUN,
        session_id=uuid4(),
        error_code="E_TIMEOUT",
        completeness="partial",
        capture_mode="metadata",
    )
    assert result.returned_count == 1


@pytest.mark.asyncio
async def test_publication_query_failure_fails_closed() -> None:
    session = session_for(row())

    async def _execute(query, params=None):
        sql = str(query).lower()
        if "evidence_outbox" in sql:
            raise SQLAlchemyError("outbox down")
        result = MagicMock()
        if "set_config" in sql:
            result.scalar_one.return_value = "ok"
            result.mappings.return_value.all.return_value = []
            return result
        if "count(" in sql.replace(" ", ""):
            result.scalar_one.return_value = 1
            result.mappings.return_value.all.return_value = []
            return result
        result.mappings.return_value.all.return_value = [row()]
        return result

    session.execute = AsyncMock(side_effect=_execute)
    await assert_list_error(SERVICE_DEGRADED, session=session, limit=10)


@pytest.mark.asyncio
async def test_map_publication_and_direct_publication_helpers() -> None:
    assert map_publication([], None, None).publication_state == "unavailable"
    assert map_publication(["unknown-status"], 3, None).publication_state == "unavailable"
    assert map_publication(["delivered"], None, 10).source_watermark == "not_provided"
    empty = await publication_for_requests(session_for(), ORG, [], datetime.now(UTC))
    assert empty == {}
    failed = AsyncMock()
    failed.execute.side_effect = SQLAlchemyError("outbox")
    await assert_api_error(
        publication_for_requests(failed, ORG, ["req-a"], datetime.now(UTC)),
        SERVICE_DEGRADED,
    )


@pytest.mark.asyncio
async def test_list_rejects_invalid_status_and_naive_datetimes() -> None:
    await assert_list_error(
        VALIDATION_ERROR,
        settings=cursor_settings(),
        status="weird",
        limit=1,
    )
    naive = END.replace(tzinfo=None)
    await assert_list_error(
        VALIDATION_ERROR,
        settings=cursor_settings(),
        started_after=naive,
        started_before=END,
        limit=1,
    )


@pytest.mark.asyncio
async def test_matched_count_failure_returns_null_and_alias_works() -> None:
    session = session_for(row(), fixtures=SessionFixtures(outbox=[outbox_row()]))
    original = session.execute

    async def _execute(query, params=None):
        sql = str(query).lower()
        if "count(" in sql.replace(" ", ""):
            raise SQLAlchemyError("count failed")
        return await original(query, params)

    session.execute = AsyncMock(side_effect=_execute)
    result = await list_call(session, cursor_settings(), auth(), limit=10)
    assert result.matched_count is None
    aliased = await get_operator_trace(session_for(row()), auth(), trace_id="trace-a")
    assert aliased.returned_count == 1


@pytest.mark.asyncio
async def test_run_detail_with_candidates_without_interim_note() -> None:
    session = session_for(
        row(),
        fixtures=SessionFixtures(
            candidates=[
                {
                    "memory_id": uuid4(),
                    "retrieval_rank": 1,
                    "final_rank": None,
                    "delta_rank": None,
                    "category": None,
                    "token_estimate": None,
                    "exclusion": "kept",
                    "score_schema": "stable_v1",
                    "composite_score": None,
                }
            ],
        ),
    )
    detail = await get_operator_trace_run(session, auth(), run_id=RUN)
    assert detail.score_schema_note is None
    assert "score_explanation" not in detail.unavailable_sections
    assert "candidates" not in detail.unavailable_sections
    assert len(detail.candidates) == 1
    assert detail.candidates[0].final_rank is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"started_after": END, "started_before": START},
        {"started_before": START + timedelta(days=8)},
        {"limit": 101},
        {"cursor": "tampered"},
    ],
)
async def test_list_rejects_bad_bounds_and_cursor(overrides: dict[str, object]) -> None:
    await assert_list_error(VALIDATION_ERROR, settings=cursor_settings(), **overrides)


@pytest.mark.asyncio
async def test_list_uses_signed_cursor_and_rejects_query_replay() -> None:
    settings = cursor_settings()
    first_result = await first_page_with_cursor(settings, status="ok")
    second = session_for(row("trace-c", run_id=uuid4(), request_id="request-c"))
    await list_call(
        second,
        settings,
        auth(),
        started_after=START,
        started_before=END,
        status="ok",
        limit=1,
        cursor=first_result.next_cursor,
    )
    encoded, signature = first_result.next_cursor.split(".", 1)
    assert signature
    tampered = f"{encoded}.{'0' * 64}"
    payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
    payload["expires_at"] = "2020-01-01T00:00:00+00:00"
    expired_encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    expired_signature = hmac.new(
        settings.operator_cursor_secret.encode(), expired_encoded.encode(), hashlib.sha256
    ).hexdigest()
    invalid_cursors = [
        (auth(), "error", first_result.next_cursor),
        (
            OperatorSessionAuthorization(org_id=uuid4(), permissions=1, session_id="s", subject="u"),
            "ok",
            first_result.next_cursor,
        ),
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
    settings = cursor_settings()
    first_result = await first_page_with_cursor(
        settings, status=None, started_after=None, started_before=None
    )
    second_result = await list_call(
        session_for(row("trace-c", run_id=uuid4(), request_id="request-c")),
        settings,
        auth(),
        started_after=None,
        started_before=None,
        status=None,
        limit=1,
        cursor=first_result.next_cursor,
    )
    assert second_result.query_start == first_result.query_start
    assert second_result.query_end == first_result.query_end


@pytest.mark.asyncio
async def test_list_fails_closed_when_cursor_key_or_database_is_unavailable() -> None:
    await assert_list_error(
        SERVICE_DEGRADED,
        session=session_for(row("trace-a"), row("trace-b", run_id=uuid4())),
        settings=cursor_settings(operator_cursor_secret=None),
    )
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("db")
    await assert_list_error(SERVICE_DEGRADED, session=session)


@pytest.mark.asyncio
async def test_trace_runs_are_deterministic_multi_run_listing() -> None:
    run_b = uuid4()
    session = session_for(
        row("trace-a", request_id="r1"),
        row("trace-a", request_id="r2", run_id=run_b),
    )
    result = await list_operator_trace_runs(session, auth(), trace_id="trace-a")
    assert result.schema_version == "operator.trace-list.v1"
    assert len(result.items) == 2
    assert {item.request_id for item in result.items} == {"r1", "r2"}
    missing = session_for()
    await assert_api_error(list_operator_trace_runs(missing, auth(), trace_id="foreign"), NOT_FOUND)


@pytest.mark.asyncio
async def test_run_detail_is_snapshot_and_foreign_or_missing_is_404() -> None:
    detail = await get_operator_trace_run(session_for(row()), auth(), run_id=RUN)
    assert detail.schema_version == "operator.trace-detail.v1"
    assert "content" in detail.unavailable_sections
    assert detail.run_id == RUN
    missing = session_for()
    not_found = await assert_api_error(get_operator_trace_run(missing, auth(), run_id=uuid4()), NOT_FOUND)
    assert not_found.message == "Trace not found"
    failed = AsyncMock()
    failed.execute.side_effect = SQLAlchemyError("db")
    await assert_api_error(get_operator_trace_run(failed, auth(), run_id=RUN), SERVICE_DEGRADED)


@pytest.mark.asyncio
async def test_list_maps_unfinished_and_late_lifecycle_metadata() -> None:
    unfinished = row("trace-open")
    unfinished["ended_at"] = None
    unfinished["completeness"] = "late"
    unfinished["status"] = "failed"
    session = session_for(unfinished)
    result = await list_call(
        session,
        cursor_settings(),
        auth(),
        started_after=START,
        started_before=END,
        status="error",
        limit=1,
        cursor=None,
    )
    assert result.items[0].duration_ms is None
    assert result.items[0].status == "error"
    assert result.items[0].evidence.freshness == "stale"
    list_calls = [call for call in session.execute.await_args_list if "evidence_runs" in str(call.args[0]).lower() and "count" not in str(call.args[0]).lower().replace(" ", "")]
    assert list_calls
    sql = str(list_calls[0].args[0])
    compiled = list_calls[0].args[0].compile()
    assert "status !=" in sql or "status <>" in sql
    assert compiled.params.get("status_1") == "ok"


@pytest.mark.asyncio
async def test_list_error_filter_sql_excludes_ok_literal_equality() -> None:
    session = session_for(row())
    await list_call(session, cursor_settings(), auth(), status="error", limit=1)
    list_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "evidence_runs" in str(call.args[0]).lower() and "count(" not in str(call.args[0]).lower().replace(" ", "")
    )
    assert "status !=" in list_sql or "status <>" in list_sql


def test_mounted_d2_routes_require_session_and_return_no_store_metadata() -> None:
    org_id = uuid4()
    validator = StaticTokenValidator(
        {
            "ibex_pat_test_secret": ValidateResult(
                org_id=org_id, permissions=OPERATOR_METADATA_READ, user_id="u1"
            )
        }
    )
    settings = cursor_settings()
    with create_operator_app(settings=settings, validator=validator) as (app, client):
        assert client.get("/v1/operator/traces").status_code == 401
        app.dependency_overrides[operator_org_session] = lambda: session_for(row())
        assert client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"}).status_code == 200
        response = client.get("/v1/operator/traces?limit=1")
        runs = client.get("/v1/operator/traces/trace-a")
        detail = client.get(f"/v1/operator/traces/runs/{RUN}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["items"][0]["evidence"]["source"] == "postgres.evidence_runs"
    assert runs.status_code == 200
    assert runs.json()["schema_version"] == "operator.trace-list.v1"
    assert detail.status_code == 200
    assert "content" in detail.json()["unavailable_sections"]
