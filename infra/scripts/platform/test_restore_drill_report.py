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
    def test_outbox_rpo_matrix(self) -> None:
        cases = (
            (0, 0, True),
            (0, 12, True),
            (1, 0, False),
            (3, 9, False),
            (None, 0, False),
            (0, None, False),
        )
        for pending, seq, expect in cases:
            with self.subTest(pending=pending, seq=seq):
                got = _mod.outbox_rpo_pass(
                    pending=pending, max_aggregate_seq=seq, target=0
                )
                self.assertEqual(got, expect)


class PostgresRpoHonestyTests(unittest.TestCase):
    def test_rpo_pass_by_mechanism(self) -> None:
        cases = (
            ("pg_dump_fallback", False),
            ("pgbackrest_wal", True),
            ("unmeasured", False),
        )
        for mechanism, expect in cases:
            with self.subTest(mechanism=mechanism):
                got = _mod.postgres_rpo_pass(
                    backup_ok=True,
                    restore_ok=True,
                    measured=12,
                    target=300,
                    mechanism=mechanism,
                )
                self.assertEqual(got, expect)


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
