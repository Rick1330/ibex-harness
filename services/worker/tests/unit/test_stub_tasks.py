"""Unit tests for noop task callables."""

from __future__ import annotations

from app.tasks import maintenance, stubs


def test_stub_tasks_return_payloads() -> None:
    assert stubs.extraction_noop.run() == {"status": "noop", "queue": "extraction"}
    assert stubs.embedding_noop.run() == {"status": "noop", "queue": "embedding"}
    assert stubs.mcp_audit_noop.run() == {"status": "noop", "queue": "mcp_audit"}
    assert stubs.result_probe.run() == {"status": "probe", "queue": "maintenance"}


def test_maintenance_noop_sweep_returns_payload() -> None:
    assert maintenance.noop_sweep.run() == {"status": "noop"}
