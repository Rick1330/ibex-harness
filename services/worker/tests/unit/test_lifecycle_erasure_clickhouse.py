"""Unit tests for the ClickHouse op the erasure consumer reuses.

The erasure stage does not build its own ClickHouse statement: it calls the
event-scoped op written for org deletion. Reusing it is only safe because that
op binds the org and the event id, and because it refuses a query paired with the
wrong table — a query run against ``llm_traces`` with an event predicate would
delete the wrong rows and report success. Both properties are pinned here
because the erasure stage is a new caller of that op.
"""

from __future__ import annotations

import pytest

_ORG_ID = "00000000-0000-0000-0000-000000000002"
_EVENT_ID = "00000000-0000-0000-0000-00000000000a"


def test_event_scoped_clickhouse_op_binds_org_and_event() -> None:
    """The reused ClickHouse op narrows to one event and still binds the org."""
    from app.tasks import org_deletion_stores as stores

    op = stores.CHOp(
        stores.CHClient(http=object(), url="http://clickhouse/", auth=None),
        stores.CH_EVENT_TABLE,
        _ORG_ID,
        event_id=_EVENT_ID,
    )
    query, params = stores._ch_statement(
        op, stores.CH_DELETE_QUERIES, stores.CH_EVENT_DELETE_QUERY
    )
    assert query == stores.CH_EVENT_DELETE_QUERY
    assert params["param_org_id"] == _ORG_ID
    assert params["param_event_id"] == _EVENT_ID


def test_event_scoped_clickhouse_op_refuses_another_table() -> None:
    """An event query paired with the wrong table would delete rows silently."""
    from app.tasks import org_deletion_stores as stores

    op = stores.CHOp(
        stores.CHClient(http=object(), url="http://clickhouse/", auth=None),
        "llm_traces",
        _ORG_ID,
        event_id=_EVENT_ID,
    )
    with pytest.raises(ValueError, match="evidence table"):
        stores._ch_statement(op, stores.CH_DELETE_QUERIES, stores.CH_EVENT_DELETE_QUERY)
