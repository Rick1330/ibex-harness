"""Scope -> permission-bit mapping tests."""

from __future__ import annotations

from authclient.permissions import (
    BILLING_READ,
    OPERATOR_METADATA_READ,
    OPERATOR_REDACTED_READ,
    TRACE_READ,
)

from mcp_gateway.scopes import Scope, permission_for_scope, scope_granted


def test_scope_values_are_contract_stable() -> None:
    assert Scope.OPERATOR_READ.value == "operator.read"
    assert Scope.RUNS_READ.value == "runs.read"
    assert Scope.EVIDENCE_READ.value == "evidence.read"
    assert Scope.BUDGET_READ.value == "budget.read"


def test_scope_maps_to_existing_permission_bits() -> None:
    assert permission_for_scope(Scope.OPERATOR_READ) == OPERATOR_METADATA_READ
    assert permission_for_scope(Scope.RUNS_READ) == TRACE_READ
    assert permission_for_scope(Scope.EVIDENCE_READ) == OPERATOR_REDACTED_READ
    assert permission_for_scope(Scope.BUDGET_READ) == BILLING_READ


def test_scope_granted_requires_every_bit() -> None:
    assert scope_granted(OPERATOR_METADATA_READ, Scope.OPERATOR_READ) is True
    assert scope_granted(0, Scope.OPERATOR_READ) is False
    assert scope_granted(TRACE_READ, Scope.OPERATOR_READ) is False
    combined = OPERATOR_REDACTED_READ | BILLING_READ
    assert scope_granted(combined, Scope.EVIDENCE_READ) is True
    assert scope_granted(combined, Scope.BUDGET_READ) is True
    assert scope_granted(combined, Scope.RUNS_READ) is False
