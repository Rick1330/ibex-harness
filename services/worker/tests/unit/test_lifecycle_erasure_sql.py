"""Unit tests for the shape of the statements the erasure consumer runs.

RLS already fences a row to its tenant, but AGENTS.md §4.1 requires the explicit
``org_id`` predicate as well: one defence that a role attribute or a policy edit
turns off must not be the only thing between one tenant's settle and another's
row. The claim is the exception that proves the rule — discovery runs through a
``SECURITY DEFINER`` function because a scheduled consumer has no tenant to
select — and no statement may be built from a value. The statements' behaviour
against real PostgreSQL is covered by the integration suite.
"""

from __future__ import annotations

import inspect

from app.tasks import lifecycle_erasure as le


def test_claim_sql_goes_through_the_security_definer_function() -> None:
    sql = " ".join(le._CLAIM_SQL.split())
    assert "memory_lifecycle_claim_erasure" in sql
    # The outbox is RLS-scoped; a direct SELECT here would silently see nothing.
    assert "FROM ibex_core.memory_lifecycle_outbox" not in sql


def test_settle_statements_carry_the_org_predicate() -> None:
    """RLS is one defence; AGENTS.md §4.1 requires the explicit predicate too."""
    for name in ("_COMPLETE_SQL", "_RETRY_SQL", "_FAIL_SQL", "_RETIRE_STALE_SQL"):
        sql = " ".join(getattr(le, name).split())
        assert "org_id = CAST(:org_id AS uuid)" in sql, name


def test_sql_is_literal_not_built_from_values() -> None:
    sources = [
        inspect.getsource(module) for module in (le.sql, le.staging, le.sweep)
    ]
    for source in sources:
        assert 'f"DELETE' not in source
        assert "f'DELETE" not in source
        assert 'f"UPDATE' not in source
        assert "f'UPDATE" not in source
