#!/usr/bin/env python3
"""Unit tests for restore_drill_report (outbox RPO + pg_dump honesty)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_REPORT_PY = Path(__file__).resolve().parent / "restore_drill_report.py"
_spec = importlib.util.spec_from_file_location("restore_drill_report", _REPORT_PY)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load restore_drill_report from {_REPORT_PY}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["restore_drill_report"] = _mod
_spec.loader.exec_module(_mod)

# Fixture path only — never opens or writes this file (avoids Bandit B108).
_TRANSCRIPT_FIXTURE = "infra/scripts/platform/evidence/4p5-restore-drill/transcript.txt"


def _base_env(**overrides: str) -> dict[str, str]:
    env = {
        "PG_RPO_SEC": "300",
        "PG_RTO_SEC": "1800",
        "CH_RPO_SEC": "86400",
        "CH_RTO_SEC": "3600",
        "OBJ_RPO_SEC": "86400",
        "OBJ_RTO_SEC": "3600",
        "PG_MECHANISM": "pg_dump_fallback",
        "PG_BACKUP_OK": "true",
        "PG_RESTORE_OK": "true",
        "PG_RPO_MEASURED": "2",
        "PG_RTO_MEASURED": "3",
        "OUTBOX_SEQ": "0",
        "OUTBOX_PENDING": "0",
        "ISO_OK": "true",
        "KIND_OK": "true",
        "KYVERNO_OK": "false",
        "TRANSCRIPT": _TRANSCRIPT_FIXTURE,
        "CH_REACHABLE": "false",
    }
    env.update(overrides)
    return env


class OutboxRpoPassTests(unittest.TestCase):
    def test_pass_when_pending_zero_and_seq_known(self) -> None:
        self.assertTrue(
            _mod.outbox_rpo_pass(pending=0, max_aggregate_seq=0, target=0)
        )
        self.assertTrue(
            _mod.outbox_rpo_pass(pending=0, max_aggregate_seq=12, target=0)
        )

    def test_fail_when_pending_nonzero(self) -> None:
        self.assertFalse(
            _mod.outbox_rpo_pass(pending=1, max_aggregate_seq=0, target=0)
        )
        self.assertFalse(
            _mod.outbox_rpo_pass(pending=3, max_aggregate_seq=9, target=0)
        )

    def test_fail_when_unmeasured(self) -> None:
        self.assertFalse(
            _mod.outbox_rpo_pass(pending=None, max_aggregate_seq=0, target=0)
        )
        self.assertFalse(
            _mod.outbox_rpo_pass(pending=0, max_aggregate_seq=None, target=0)
        )


class PostgresRpoHonestyTests(unittest.TestCase):
    def test_pg_dump_fallback_never_passes_rpo(self) -> None:
        self.assertFalse(
            _mod.postgres_rpo_pass(
                backup_ok=True,
                restore_ok=True,
                measured=1,
                target=300,
                mechanism="pg_dump_fallback",
            )
        )

    def test_pgbackrest_wal_can_pass(self) -> None:
        self.assertTrue(
            _mod.postgres_rpo_pass(
                backup_ok=True,
                restore_ok=True,
                measured=12,
                target=300,
                mechanism="pgbackrest_wal",
            )
        )


class BuildReportTests(unittest.TestCase):
    def test_outbox_pending_fails_report(self) -> None:
        report = _mod.build_report(_base_env(OUTBOX_PENDING="2"))
        self.assertFalse(report["outbox"]["rpo_pass"])
        self.assertEqual(report["outbox"]["pending"], 2)

    def test_pg_dump_rpo_pass_false_even_when_fast(self) -> None:
        report = _mod.build_report(_base_env())
        self.assertEqual(report["postgres"]["mechanism"], "pg_dump_fallback")
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertEqual(report["postgres"]["rpo_measured_sec"], 2)
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")

    def test_allow_no_db_not_evidence(self) -> None:
        report = _mod.build_report(_base_env(ALLOW_NO_DB="1", ISO_OK="false"))
        self.assertFalse(report["evidence_eligible"])
        self.assertTrue(report["allow_no_db"])


if __name__ == "__main__":
    unittest.main()
