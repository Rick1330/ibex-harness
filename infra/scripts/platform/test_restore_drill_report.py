#!/usr/bin/env python3
"""Unit tests for restore_drill_report (outbox RPO + pg_dump honesty + O02/O03)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PLATFORM_DIR = Path(__file__).resolve().parent
_REPORT_PY = _PLATFORM_DIR / "restore_drill_report.py"
_DRILL_SH = _PLATFORM_DIR / "restore-drill.sh"
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


class PgBackrestRpoGateTests(unittest.TestCase):
    """rpo_pass is a PITR claim: only a measured, fresh pgBackRest WAL run earns it."""

    def test_pgbackrest_wal_with_null_rpo_cannot_pass(self) -> None:
        # Archiving was proven to work, but no RPO was measured. "Archiving is
        # on" is not "the RPO target was met", so the claim must stay false.
        report = _mod.build_report(
            _base_env(PG_MECHANISM="pgbackrest_wal", PG_RPO_MEASURED="", WAL_ARCHIVE_OK="true")
        )
        self.assertEqual(report["postgres"]["mechanism"], "pgbackrest_wal")
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_with_measured_rpo_can_pass(self) -> None:
        # The counterpart to the test above: the gate is not permanently closed.
        report = _mod.build_report(
            _base_env(
                PG_MECHANISM="pgbackrest_wal",
                PG_RPO_MEASURED="30",
                PG_RPO_SEC="300",
                WAL_ARCHIVE_OK="true",
            )
        )
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_over_target_fails(self) -> None:
        report = _mod.build_report(
            _base_env(
                PG_MECHANISM="pgbackrest_wal",
                PG_RPO_MEASURED="900",
                PG_RPO_SEC="300",
                WAL_ARCHIVE_OK="true",
            )
        )
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pg_dump_fallback_never_claims_rpo_pass(self) -> None:
        # Even a fast, measured number cannot make a dump a PITR mechanism.
        report = _mod.build_report(
            _base_env(PG_MECHANISM="pg_dump_fallback", PG_RPO_MEASURED="1", WAL_ARCHIVE_OK="true")
        )
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")


class PitrReportTests(unittest.TestCase):
    """A point-in-time rehearsal reports the target it asked for and reached."""

    def _pitr_env(self, **overrides: str) -> dict[str, str]:
        env = _base_env(
            DRILL_KIND="pitr",
            PG_MECHANISM="pgbackrest_wal",
            PG_RPO_MEASURED="45",
            WAL_ARCHIVE_OK="true",
            TARGET_TIMESTAMP="2026-11-16T10:00:00Z",
            RECOVERY_TARGET_REACHED="true",
            RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58Z",
            CLUSTER_DATA_BYTES="1048576",
            RESTORED_ORGS="3",
            RESTORED_MEMORIES="50000",
            ISO_OK="false",
        )
        env.update(overrides)
        return env

    def test_reached_target_is_recorded_and_eligible(self) -> None:
        report = _mod.build_report(self._pitr_env())
        self.assertEqual(report["drill_kind"], "pitr")
        self.assertEqual(report["postgres"]["target_timestamp"], "2026-11-16T10:00:00Z")
        self.assertTrue(report["postgres"]["recovery_target_reached"])
        self.assertEqual(report["postgres"]["recovery_replay_timestamp"], "2026-11-16T09:59:58Z")
        self.assertEqual(report["postgres"]["cluster_data_bytes"], 1048576)
        self.assertEqual(report["postgres"]["restored_row_counts"]["memories"], 50000)
        self.assertTrue(report["postgres"]["rpo_pass"])
        # A scratch rehearsal never proves tenant isolation; it must not need to.
        self.assertFalse(report["tenant_isolation_post_restore"])
        self.assertTrue(report["evidence_eligible"])

    def test_missed_target_cannot_pass(self) -> None:
        report = _mod.build_report(
            self._pitr_env(RECOVERY_TARGET_REACHED="false", RECOVERY_REPLAY_TIMESTAMP="2026-11-16T10:00:09Z")
        )
        self.assertFalse(report["postgres"]["recovery_target_reached"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["evidence_eligible"])

    def test_no_target_requested_is_not_a_reached_target(self) -> None:
        report = _mod.build_report(
            self._pitr_env(TARGET_TIMESTAMP="", RECOVERY_TARGET_REACHED="", RECOVERY_REPLAY_TIMESTAMP="")
        )
        self.assertIsNone(report["postgres"]["target_timestamp"])
        self.assertIsNone(report["postgres"]["recovery_target_reached"])


class UnavailableMechanismTests(unittest.TestCase):
    """PITR that cannot run must say why, and must never claim a pass."""

    def _unavailable_env(self, **overrides: str) -> dict[str, str]:
        env = _base_env(
            PG_MECHANISM="unavailable",
            PG_BACKUP_OK="false",
            PG_RESTORE_OK="false",
            PG_RTO_MEASURED="",
            BLOCKED_BY="the pgbackrest binary is not installed on this host",
        )
        env.update(overrides)
        return env

    def test_unavailable_without_blocked_by_is_rejected(self) -> None:
        for empty in ("", "   "):
            with (
                self.subTest(blocked_by=repr(empty)),
                self.assertRaises(_mod.ReportHonestyError),
            ):
                _mod.build_report(self._unavailable_env(BLOCKED_BY=empty))

    def test_unavailable_with_reason_claims_nothing(self) -> None:
        report = _mod.build_report(self._unavailable_env())
        self.assertEqual(report["postgres"]["mechanism"], "unavailable")
        self.assertEqual(report["blocked_by"], "the pgbackrest binary is not installed on this host")
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["postgres"]["rto_pass"])
        self.assertFalse(report["evidence_eligible"])
        self.assertEqual(report["postgres_rpo_residual"], "pitr_unavailable")

    def test_unavailable_cannot_carry_a_restore_result(self) -> None:
        # A producer that passes restore_ok=true for a run that never restored
        # must not be able to turn the report into a pass.
        report = _mod.build_report(
            self._unavailable_env(PG_BACKUP_OK="true", PG_RESTORE_OK="true", PG_RTO_MEASURED="1")
        )
        self.assertFalse(report["postgres"]["restore_ok"])
        self.assertFalse(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_honesty_validator_refuses_a_fallback_rpo_pass(self) -> None:
        report = _mod.build_report(_base_env())
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(_mod.ReportHonestyError):
            _mod.assert_honest(report)

    def test_honesty_validator_refuses_rpo_pass_without_a_measurement(self) -> None:
        report = _mod.build_report(_base_env(PG_MECHANISM="pgbackrest_wal", PG_RPO_MEASURED=""))
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(_mod.ReportHonestyError):
            _mod.assert_honest(report)


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


class DrillMechanismFallbackTests(unittest.TestCase):
    """`--mechanism=pgbackrest` must fail, not degrade into pg_dump."""

    # Commands the drill needs before it reaches the mechanism guard. pgbackrest
    # is deliberately absent from the directory, which is the condition under
    # test; nothing here is a stub of the script's own logic.
    _PATH_COMMANDS = (
        "bash",
        "cat",
        "date",
        "dirname",
        "grep",
        "mkdir",
        "python3",
        "seq",
        "sleep",
        "tail",
        "tee",
        "tr",
    )

    def test_pgbackrest_mechanism_fails_loudly_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            bindir.mkdir()
            for name in self._PATH_COMMANDS:
                found = shutil.which(name)
                if found:
                    os.symlink(found, bindir / name)
            report_dir = root / "reports"
            env = {
                **os.environ,
                "PATH": str(bindir),
                "RESTORE_DRILL_REPORT_DIR": str(report_dir),
                "IBEX_DRILL_METRICS_PATH": str(root / "metrics.prom"),
                "IBEX_DRILL_ENVIRONMENT_CLASS": "test-harness",
                "SKIP_COMPOSE": "1",
                # Never connected to: the guard fires before any database access.
                "POSTGRES_DSN": "postgres://drill:drill@127.0.0.1:1/drill?sslmode=disable",
            }
            env.pop("IBEX_DRILL_MECHANISM", None)
            env.pop("POSTGRES_CONTAINER", None)
            proc = subprocess.run(
                ["/bin/bash", str(_DRILL_SH), "--mechanism=pgbackrest"],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("refusing to fall back to pg_dump", output)
            self.assertIn("pgbackrest binary is not installed", output)
            # It failed before touching a database: no seeding, no data loss.
            self.assertNotIn("seeding org markers", output)
            written = json.loads((report_dir / "restore-drill-report.json").read_text())
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")
            self.assertTrue(written["blocked_by"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertFalse(written["evidence_eligible"])
            self.assertEqual(written["environment_class"], "test-harness")

    def test_env_equivalent_selects_the_same_path(self) -> None:
        # The env form and the flag form must select the same mechanism.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            bindir.mkdir()
            for name in self._PATH_COMMANDS:
                found = shutil.which(name)
                if found:
                    os.symlink(found, bindir / name)
            report_dir = root / "reports"
            env = {
                **os.environ,
                "PATH": str(bindir),
                "RESTORE_DRILL_REPORT_DIR": str(report_dir),
                "IBEX_DRILL_METRICS_PATH": str(root / "metrics.prom"),
                "IBEX_DRILL_MECHANISM": "pgbackrest",
                "SKIP_COMPOSE": "1",
                "POSTGRES_DSN": "postgres://drill:drill@127.0.0.1:1/drill?sslmode=disable",
            }
            env.pop("POSTGRES_CONTAINER", None)
            proc = subprocess.run(
                ["/bin/bash", str(_DRILL_SH)],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("refusing to fall back to pg_dump", output)
            written = json.loads((report_dir / "restore-drill-report.json").read_text())
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")


if __name__ == "__main__":
    unittest.main()
