"""Unit tests for the store stages that reach PostgreSQL and object storage.

Every stage must raise unless absence is confirmed; a stage that reported success
on "the delete was accepted" would turn a store refusal into a receipt nobody
earned. These tests drive the dispatcher's fail-closed branch, the
``session_events`` stage, and the object-store stage against replaced clients, so
the decision rules are exercised without a server. The cache stages are in
``test_lifecycle_erasure_cache.py``; the SQL those stages run against real
PostgreSQL and ClickHouse is covered by the integration suite.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import _StoreTarget
from tests.unit.lifecycle_erasure_fakes import erasure

# ---------------------------------------------------------------------------
# The dispatcher fails closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_store_fails_closed_instead_of_falling_through() -> None:
    with pytest.raises(RuntimeError, match="no erasure stage"):
        await le._stage(
            _StoreTarget("filesystem", ("/tmp/x",)), erasure(), time.monotonic() + 1
        )


# ---------------------------------------------------------------------------
# session_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_event_locator_must_be_a_row_id() -> None:
    """A locator that is not a bigint cannot name a session_events row.

    The refusal is fixed text: the locator is caller-written, and anything it
    carries would otherwise reach the receipt's ``error`` column and the log.
    """
    locator = "not-a-row-id"
    with pytest.raises(RuntimeError, match="not a row id") as refused:
        await le._stage_session_events((locator,), erasure(), time.monotonic() + 1)
    assert locator not in str(refused.value)


# ---------------------------------------------------------------------------
# The object store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_object_store_stage_waits_until_head_reports_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    present = {"s3://bucket/one.json"}

    def delete(uri: str, *, org_id: str, settings: Any | None = None) -> None:
        del org_id, settings
        present.discard(uri)

    def exists(uri: str, *, org_id: str, settings: Any | None = None) -> bool:
        del org_id, settings
        return uri in present

    monkeypatch.setattr(le.staging, "delete_uri", delete)
    monkeypatch.setattr(le.staging, "object_exists", exists)
    await le._stage_objectstore(
        ("s3://bucket/one.json",), erasure(), time.monotonic() + 10
    )
    assert present == set()


@pytest.mark.asyncio
async def test_object_store_stage_raises_when_the_object_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delete the store accepted but did not apply is not an erasure."""
    monkeypatch.setattr(
        le.staging, "delete_uri", lambda uri, *, org_id, settings=None: None
    )
    monkeypatch.setattr(
        le.staging, "object_exists", lambda uri, *, org_id, settings=None: True
    )
    with pytest.raises(TimeoutError):
        await le._stage_objectstore(
            ("s3://bucket/one.json",), erasure(), time.monotonic() + 0.1
        )


def test_object_exists_raises_when_the_store_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable object store must never read as "the object is gone"."""
    from app import objectstore_client

    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError, match="S3_ENDPOINT"):
        objectstore_client.object_exists("s3://bucket/org/key.json", org_id="org")
