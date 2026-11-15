"""Unit tests for the ClickHouse and object-store deletion stages.

The stage helpers are parameterised over an allowlisted table set and share one
HTTP client; these tests pin the statement each verb posts, the org (and event)
it binds, and the classification that decides whether a failing ClickHouse
response is "no such table" or a real failure. Nothing here reaches a store.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import org_deletion_stores as stores


class _Resp:
    """One ClickHouse HTTP response, as the code reads it."""

    def __init__(self, status_code: int, text: str = "0") -> None:
        self.status_code = status_code
        self.text = text


class _ClickHouse:
    """A ClickHouse HTTP client stub that records every POSTed parameter set."""

    def __init__(self, *statuses: int, body: str = "0") -> None:
        self.statuses = list(statuses)
        self.body = body
        self.queries: list[dict[str, str]] = []

    def post(self, _url: str, *, params: dict[str, str], auth: Any, timeout: float) -> _Resp:
        del auth, timeout
        self.queries.append(params)
        status = self.statuses.pop(0) if self.statuses else 200
        return _Resp(status, self.body)


def _client(*statuses: int, body: str = "0") -> stores.CHClient:
    return stores.CHClient(
        http=_ClickHouse(*statuses, body=body), url="http://clickhouse:8123/", auth=None
    )


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the poll delay so the wait loops cost no wall-clock time."""
    monkeypatch.setattr(
        stores, "asyncio", SimpleNamespace(to_thread=asyncio.to_thread, sleep=AsyncMock())
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_clickhouse_dsn_requires_a_configured_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("CLICKHOUSE_DSN", "IBEX_WORKER_CLICKHOUSE_DSN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="CLICKHOUSE_DSN required"):
        stores.clickhouse_dsn(MagicMock(clickhouse_dsn=None))


@pytest.mark.parametrize(
    ("body", "unknown"),
    [
        ("Code: 47. DB::Exception: UNKNOWN_TABLE", True),
        ("Code: 60. Table ibex.usage_facts doesn't exist", True),
        ("Code: 62. Syntax error", False),
    ],
)
def test_ch_unknown_table_classification(body: str, unknown: bool) -> None:
    assert stores._ch_unknown_table(body) is unknown


# ---------------------------------------------------------------------------
# Statement selection
# ---------------------------------------------------------------------------


def test_ch_statement_without_an_event_binds_only_the_org() -> None:
    op = stores.CHOp(_client(), "usage_facts", "org-1")

    query, params = stores._ch_statement(op, stores.CH_DELETE_QUERIES, stores.CH_EVENT_DELETE_QUERY)

    assert query == stores.CH_DELETE_QUERIES["usage_facts"]
    assert params == {"param_org_id": "org-1"}


# ---------------------------------------------------------------------------
# Mutate
# ---------------------------------------------------------------------------


def test_ch_mutate_posts_the_table_mutation_for_the_org() -> None:
    client = _client(200)

    stores.ch_mutate_table(stores.CHOp(client, "llm_traces", "org-1"))

    assert client.http.queries == [
        {"query": stores.CH_DELETE_QUERIES["llm_traces"], "param_org_id": "org-1"}
    ]


def test_ch_mutate_tolerates_a_table_that_does_not_exist() -> None:
    client = _client(500, body="Code: 60. Table ibex.usage_facts doesn't exist")

    stores.ch_mutate_table(stores.CHOp(client, "usage_facts", "org-1"))


def test_ch_mutate_surfaces_a_real_failure() -> None:
    client = _client(502, body="Bad gateway")

    with pytest.raises(RuntimeError, match="clickhouse mutate usage_facts: 502"):
        stores.ch_mutate_table(stores.CHOp(client, "usage_facts", "org-1"))


# ---------------------------------------------------------------------------
# Count and wait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ch_count_reads_the_row_count() -> None:
    client = _client(200, body=" 3\n")

    assert await stores.ch_count(stores.CHOp(client, "evidence_events", "org-1")) == 3
    assert client.http.queries == [
        {"query": stores.CH_COUNT_QUERIES["evidence_events"], "param_org_id": "org-1"}
    ]


@pytest.mark.asyncio
async def test_ch_count_treats_a_missing_table_as_empty() -> None:
    client = _client(404, body="UNKNOWN_TABLE")

    assert await stores.ch_count(stores.CHOp(client, "evidence_events", "org-1")) == 0


@pytest.mark.asyncio
async def test_ch_wait_absent_returns_once_the_count_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stores, "ch_count", AsyncMock(return_value=0))

    await stores.ch_wait_absent(stores.CHOp(_client(), "llm_traces", "org-1"), time.monotonic() + 5)


@pytest.mark.asyncio
async def test_ch_wait_absent_polls_until_the_rows_are_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    counts = AsyncMock(side_effect=[3, 1, 0])
    monkeypatch.setattr(stores, "ch_count", counts)

    await stores.ch_wait_absent(stores.CHOp(_client(), "llm_traces", "org-1"), time.monotonic() + 5)

    assert counts.await_count == 3


@pytest.mark.asyncio
async def test_ch_wait_absent_times_out_when_rows_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    monkeypatch.setattr(stores, "ch_count", AsyncMock(return_value=4))

    with pytest.raises(TimeoutError, match="rows remain"):
        await stores.ch_wait_absent(
            stores.CHOp(_client(), "llm_traces", "org-1"), time.monotonic() + 0.01
        )


# ---------------------------------------------------------------------------
# Client construction and the two stage entrypoints
# ---------------------------------------------------------------------------


def test_clickhouse_client_shares_one_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extraction import clickhouse_traces

    shared = object()
    monkeypatch.setattr(clickhouse_traces, "shared_clickhouse_client", lambda: shared)
    monkeypatch.setattr(
        clickhouse_traces, "_http_endpoint", lambda _dsn: ("http://clickhouse:8123/", ("u", "p"))
    )
    settings = MagicMock(clickhouse_dsn="clickhouse://u:p@clickhouse:8123/ibex")

    client = stores.clickhouse_client(settings)

    assert (client.url, client.auth, client.http) == (
        "http://clickhouse:8123/",
        ("u", "p"),
        shared,
    )


@pytest.mark.asyncio
async def test_stage_clickhouse_mutates_then_waits_for_every_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(*([200] * len(stores.CH_TABLES)))
    monkeypatch.setattr(stores, "clickhouse_client", lambda _settings: client)
    waited: list[str] = []

    async def record(op, _deadline):
        waited.append(op.table)

    monkeypatch.setattr(stores, "ch_wait_absent", record)

    await stores.stage_clickhouse(MagicMock(), org_id="org-1")

    assert [query["param_org_id"] for query in client.http.queries] == ["org-1"] * len(
        stores.CH_TABLES
    )
    assert waited == list(stores.CH_TABLES)


@pytest.mark.asyncio
async def test_delete_clickhouse_event_narrows_the_mutation_to_one_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(200)
    monkeypatch.setattr(stores, "clickhouse_client", lambda _settings: client)
    monkeypatch.setattr(stores, "ch_wait_absent", AsyncMock())

    await stores.delete_clickhouse_event(
        MagicMock(), org_id="org-1", event_id="evt-9", deadline=42.0
    )

    assert client.http.queries == [
        {
            "query": stores.CH_EVENT_DELETE_QUERY,
            "param_org_id": "org-1",
            "param_event_id": "evt-9",
        }
    ]
    op, deadline = stores.ch_wait_absent.await_args.args  # type: ignore[attr-defined]
    assert (op.table, op.event_id, deadline) == (stores.CH_EVENT_TABLE, "evt-9", 42.0)


# ---------------------------------------------------------------------------
# Object store
# ---------------------------------------------------------------------------


def test_delete_objectstore_sync_deletes_each_uri_then_the_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import objectstore_client

    calls: list[str] = []
    monkeypatch.setattr(
        objectstore_client,
        "delete_uri",
        lambda uri, *, org_id, settings=None: calls.append(f"uri:{uri}"),
    )
    monkeypatch.setattr(
        objectstore_client,
        "delete_org_prefix",
        lambda org_id, *, settings=None: calls.append(f"prefix:{org_id}"),
    )

    stores.delete_objectstore_sync(
        MagicMock(s3_endpoint="http://localhost:9000"),
        "org-1",
        ["s3://ibex-sessions/org-1/a.json", "s3://ibex-sessions/org-1/b.json"],
    )

    assert calls == [
        "uri:s3://ibex-sessions/org-1/a.json",
        "uri:s3://ibex-sessions/org-1/b.json",
        "prefix:org-1",
    ]
