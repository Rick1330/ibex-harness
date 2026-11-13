#!/usr/bin/env python3
"""Unit tests for restore_drill_report (outbox RPO + pg_dump honesty + O02/O03)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
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
        "PG_RPO_MEASURED": "",
        "PG_RTO_MEASURED": "3",
        "OUTBOX_SEQ": "0",
        "OUTBOX_PENDING": "0",
        "ISO_OK": "true",
        "KIND_OK": "true",
        "KYVERNO_OK": "false",
        "TRANSCRIPT": _TRANSCRIPT_FIXTURE,
        "CH_REACHABLE": "false",
        "FIXTURE_ROWS": "50000",
        "FIXTURE_ORGS": "2",
        "FIXTURE_ROWS_ACTUAL": "50000",
        "FIXTURE_ROWS_RESTORED": "50000",
        "DRILL_MIN_FIXTURE_ROWS": "1000",
        "DRILL_DURATION_SEC": "42",
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
                    {
                        "backup_ok": True,
                        "restore_ok": True,
                        "measured": 12,
                        "target": 300,
                        "mechanism": mechanism,
                    }
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
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")

    def test_allow_no_db_not_evidence(self) -> None:
        report = _mod.build_report(_base_env(ALLOW_NO_DB="1", ISO_OK="false"))
        self.assertFalse(report["evidence_eligible"])
        self.assertTrue(report["allow_no_db"])

    def test_fixture_size_is_recorded(self) -> None:
        report = _mod.build_report(_base_env())
        self.assertEqual(report["fixture"]["rows"], 50000)
        self.assertEqual(report["fixture"]["orgs"], 2)
        self.assertEqual(report["fixture"]["rows_verified"], 50000)
        self.assertEqual(report["fixture"]["rows_restored"], 50000)
        self.assertTrue(report["postgres"]["rto_evidence_pass"])

    def test_pre_backup_count_cannot_claim_rto_evidence(self) -> None:
        # The restore is the step under test. A post-seed count proves the data
        # existed before the backup, not that it came back, so it must not stand
        # in for the post-restore count.
        report = _mod.build_report(
            _base_env(FIXTURE_ROWS_ACTUAL="50000", FIXTURE_ROWS_RESTORED="")
        )
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertEqual(report["fixture"]["rows_verified"], 50000)
        self.assertIsNone(report["fixture"]["rows_restored"])

    def test_unverified_fixture_cannot_claim_rto_evidence(self) -> None:
        # A smoke run (ALLOW_NO_DB) seeds nothing, so the requested row count
        # must not be used as if it had been observed.
        report = _mod.build_report(
            _base_env(FIXTURE_ROWS="50000", FIXTURE_ROWS_ACTUAL="", FIXTURE_ROWS_RESTORED="")
        )
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertIsNone(report["fixture"]["rows_verified"])
        self.assertIsNone(report["fixture"]["rows_restored"])

    def test_two_row_fixture_cannot_claim_rto_evidence(self) -> None:
        # The defect O03 names: a ~1 s restore of two rows used to report
        # rto_pass=true with nothing recording how little data that was.
        report = _mod.build_report(
            _base_env(FIXTURE_ROWS="2", FIXTURE_ROWS_ACTUAL="2", FIXTURE_ROWS_RESTORED="2")
        )
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertEqual(report["fixture"]["rows"], 2)

    def test_rto_target_is_configurable(self) -> None:
        fast = _mod.build_report(_base_env(PG_RTO_MEASURED="10", PG_RTO_SEC="1800"))
        slow = _mod.build_report(_base_env(PG_RTO_MEASURED="10", PG_RTO_SEC="5"))
        self.assertTrue(fast["postgres"]["rto_pass"])
        self.assertFalse(slow["postgres"]["rto_pass"])


class DrillMetricsTests(unittest.TestCase):
    def test_success_advances_last_success_and_reports_rto(self) -> None:
        report = _mod.build_report(_base_env())
        metrics = _mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=42,
            previous_last_success=None,
        )
        self.assertEqual(metrics["ibex_restore_drill_last_success_unixtime"], 1_700_000_000)
        self.assertEqual(metrics["ibex_restore_drill_duration_seconds"], 42)
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 1)
        self.assertEqual(metrics["ibex_restore_drill_rto_evidence_pass"], 1)
        self.assertEqual(metrics["ibex_restore_drill_fixture_rows"], 50000)

    def test_failed_run_preserves_previous_success(self) -> None:
        report = _mod.build_report(_base_env(PG_RESTORE_OK="false"))
        metrics = _mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=1,
            previous_last_success=1_690_000_000,
        )
        self.assertEqual(metrics["ibex_restore_drill_last_success_unixtime"], 1_690_000_000)
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 0)

    def test_no_previous_success_omits_metric(self) -> None:
        report = _mod.build_report(_base_env(PG_RESTORE_OK="false"))
        metrics = _mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=None,
            previous_last_success=None,
        )
        self.assertNotIn("ibex_restore_drill_last_success_unixtime", metrics)
        self.assertNotIn("ibex_restore_drill_duration_seconds", metrics)
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 0)

    def test_small_fixture_sets_rto_evidence_zero(self) -> None:
        report = _mod.build_report(
            _base_env(FIXTURE_ROWS="2", FIXTURE_ROWS_ACTUAL="2", FIXTURE_ROWS_RESTORED="2")
        )
        metrics = _mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=1,
            previous_last_success=None,
        )
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 1)
        self.assertEqual(metrics["ibex_restore_drill_rto_evidence_pass"], 0)
        self.assertEqual(metrics["ibex_restore_drill_fixture_rows"], 2)

    def test_render_and_write_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ibex_restore_drill_metrics.prom"
            metrics = {
                "ibex_restore_drill_last_success_unixtime": 1_700_000_000,
                "ibex_restore_drill_duration_seconds": 42,
                # Metric name, not a credential: Bandit B105 reads the "_pass"
                # suffix as a password-like literal.
                "ibex_restore_drill_rto_pass": 1,  # nosec B105
            }
            _mod.write_metrics(path, metrics)
            text = path.read_text(encoding="utf-8")
            self.assertIn("# TYPE ibex_restore_drill_last_success_unixtime gauge", text)
            self.assertIn("ibex_restore_drill_last_success_unixtime 1700000000", text)
            self.assertIn("ibex_restore_drill_rto_pass 1", text)
            self.assertEqual(_mod.read_last_success(path), 1_700_000_000)

    def test_read_last_success_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.prom"
            self.assertIsNone(_mod.read_last_success(path))


if __name__ == "__main__":
    unittest.main()
