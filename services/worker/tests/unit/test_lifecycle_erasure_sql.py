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


def test_receipt_upsert_replaces_an_invalidated_verified_proof() -> None:
    """Only the worker writes receipts, so a contradicted proof must be replaceable.

    The first two conditions keep the narrow monotonicity that still matters: an
    existing ``verified`` is never replaced by a weaker outcome the worker did not
    earn. The third lets the one run that observed a live copy replace it, which
    is the case the receipt exists to report.
    """
    sql = " ".join(le._UPSERT_RECEIPT_SQL.split())
    assert "ibex_core.erasure_store_receipts.status <> 'verified'" in sql
    assert "EXCLUDED.status = 'verified'" in sql
    assert "CAST(:invalidate_proof AS boolean)" in sql
    # Coverage travels with the proof it belongs to, so a verified update
    # replaces the addresses the receipt now covers.
    assert "CAST(:covered_addresses AS text[])" in sql
    assert "covered_addresses = EXCLUDED.covered_addresses" in sql
