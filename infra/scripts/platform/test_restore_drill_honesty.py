#!/usr/bin/env python3
"""Honesty cases: what a report may claim, and what the validator refuses.

Every case here asserts a claim the report is *not* allowed to make. They are
grouped by the claim under test — outbox RPO, Postgres RPO by mechanism, an
unavailable run, and the report's own shape — and none of them reads a file or
runs a script.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from restore_drill_test_support import base_env, mod


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
                got = mod.outbox_rpo_pass(
                    pending=pending, max_aggregate_seq=seq, target=0
                )
                self.assertEqual(got, expect)


class PostgresRpoHonestyTests(unittest.TestCase):
    def test_rpo_pass_by_mechanism(self) -> None:
        cases = (
            # (mechanism, targeted, bound, expected)
            ("pg_dump_fallback", False, 12, False),
            ("pgbackrest_wal", False, 12, True),
            ("unmeasured", False, 12, False),
            # A targeted restore proves the target, not an RPO.
            ("pgbackrest_wal", True, 12, False),
            # No demonstrated frontier, or one above the target: no pass.
            ("pgbackrest_wal", False, None, False),
            ("pgbackrest_wal", False, 900, False),
        )
        for mechanism, targeted, bound, expect in cases:
            with self.subTest(mechanism=mechanism, bound=bound):
                got = mod.postgres_rpo_pass(
                    {
                        "backup_ok": True,
                        "restore_ok": True,
                        "bound": bound,
                        "target": 300,
                        "mechanism": mechanism,
                        "target_requested": targeted,
                    }
                )
                self.assertEqual(got, expect)


class PgBackrestRpoGateTests(unittest.TestCase):
    """rpo_pass is a PITR claim: only a demonstrated, fresh pgBackRest WAL run earns it."""

    def test_pgbackrest_wal_without_a_frontier_cannot_pass(self) -> None:
        # Archiving was proven to work, but nothing froze the frontier: no
        # quiesce instant was recorded, so no bound can be derived. "Archiving
        # is on" is not "the RPO target was met", so the claim must stay false.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", WAL_ARCHIVE_QUIESCED_AT="")
        )
        self.assertEqual(report["postgres"]["mechanism"], "pgbackrest_wal")
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_with_a_demonstrated_bound_can_pass(self) -> None:
        # The counterpart to the test above: the gate is not permanently closed.
        # The bound is the 5 s between the quiesce instant and the replay.
        report = mod.build_report(base_env(PG_MECHANISM="pgbackrest_wal"))
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 5)
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_over_target_fails(self) -> None:
        # A frontier 400 s behind the instant archiving stopped is a miss.
        report = mod.build_report(
            base_env(
                PG_MECHANISM="pgbackrest_wal",
                WAL_ARCHIVE_QUIESCED_AT="2026-11-16T07:49:27Z",
            )
        )
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 400)
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pg_dump_fallback_never_claims_rpo_pass(self) -> None:
        # Even a fresh, proven archive cannot make a dump a PITR mechanism.
        report = mod.build_report(
            base_env(PG_MECHANISM="pg_dump_fallback", WAL_ARCHIVE_OK="true")
        )
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")


class UnavailableMechanismTests(unittest.TestCase):
    """PITR that cannot run must say why, and must never claim a pass."""

    def _unavailable_env(self, **overrides: str) -> dict[str, str]:
        env = base_env(
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
            env = self._unavailable_env(BLOCKED_BY=empty)
            with (
                self.subTest(blocked_by=repr(empty)),
                self.assertRaises(mod.ReportHonestyError),
            ):
                mod.build_report(env)

    def test_unavailable_with_reason_claims_nothing(self) -> None:
        report = mod.build_report(self._unavailable_env())
        self.assertEqual(report["postgres"]["mechanism"], "unavailable")
        self.assertEqual(report["blocked_by"], "the pgbackrest binary is not installed on this host")
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["postgres"]["rto_pass"])
        self.assertFalse(report["evidence_eligible"])
        self.assertEqual(report["postgres_rpo_residual"], "pitr_unavailable")

    def test_unavailable_cannot_carry_a_restore_result(self) -> None:
        # A producer that passes restore_ok=true for a run that never restored
        # must not be able to turn the report into a pass.
        report = mod.build_report(
            self._unavailable_env(PG_BACKUP_OK="true", PG_RESTORE_OK="true", PG_RTO_MEASURED="1")
        )
        self.assertFalse(report["postgres"]["restore_ok"])
        self.assertFalse(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_honesty_validator_refuses_a_fallback_rpo_pass(self) -> None:
        report = mod.build_report(base_env())
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError):
            mod.assert_honest(report)

    def test_honesty_validator_refuses_rpo_pass_without_a_frontier(self) -> None:
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", WAL_ARCHIVE_QUIESCED_AT="")
        )
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("wal_archive_quiesced_at", str(raised.exception))


class ReportContractTests(unittest.TestCase):
    """Rules the validator applies to a report file it did not produce."""

    def _passing_report(self) -> dict[str, Any]:
        report = mod.build_report(base_env(PG_MECHANISM="pgbackrest_wal"))
        self.assertTrue(report["postgres"]["rpo_pass"])
        return report

    def test_honesty_validator_refuses_a_pass_without_a_completed_restore(self) -> None:
        # A report written or edited outside the producer can carry the booleans
        # of a run that failed. The restore has to have completed.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_RESTORE_OK="false")
        )
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("completed restore", str(raised.exception))

    def test_a_failed_restore_carries_no_bound(self) -> None:
        # The producer used to emit a numeric bound from two valid instants even
        # though restore_ok was false. A frontier read out of a restore that did
        # not complete is not a measurement, so the field is null.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_RESTORE_OK="false")
        )
        self.assertFalse(report["postgres"]["restore_ok"])
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_honesty_validator_refuses_a_bound_over_a_failed_restore(self) -> None:
        # The non-pass branch: a number with no pass must still be internally
        # consistent, so a report edited to carry a bound over a failed restore
        # is refused. The instants still parse and still derive 5 s, so the
        # completed-run rule is the one that fires.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_RESTORE_OK="false")
        )
        report["postgres"]["rpo_upper_bound_sec"] = 5
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("completed restore", str(raised.exception))

    def test_the_validator_refuses_an_rpo_pass_over_a_failed_backup(self) -> None:
        # ``postgres_rpo_pass`` requires backup_ok *and* restore_ok, so the
        # validator must not accept a combination the producer predicate
        # rejects: a pass over a restore that worked and a backup that did not.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_BACKUP_OK="false")
        )
        self.assertTrue(report["postgres"]["restore_ok"])
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        report["postgres"]["rpo_pass"] = True
        report["postgres"]["rpo_upper_bound_sec"] = 5
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("completed backup", str(raised.exception))

    def test_the_validator_refuses_a_bound_over_a_failed_backup(self) -> None:
        # The same two facts on the non-pass branch: a number with no pass is
        # still held to the run that produced it.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_BACKUP_OK="false")
        )
        report["postgres"]["rpo_upper_bound_sec"] = 5
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("completed backup", str(raised.exception))

    def test_honesty_validator_refuses_a_float_bound(self) -> None:
        # 900.0 against a 300 s target used to pass: the comparison was skipped
        # for a non-integer, which read as "not above target".
        report = self._passing_report()
        report["postgres"]["rpo_upper_bound_sec"] = 900.0
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("rpo_upper_bound_sec must be integer seconds", str(raised.exception))

    def test_honesty_validator_refuses_a_float_target(self) -> None:
        # The bound matches its frontier, so the target check is the one reached.
        report = self._passing_report()
        report["postgres"]["rpo_target_sec"] = 300.0
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("rpo_target_sec must be integer seconds", str(raised.exception))


class TenantIsolationGateTests(unittest.TestCase):
    """The write gate reads a tri-state, not a boolean.

    ``tenant_isolation_post_restore`` is ``true`` (measured, passed), ``false``
    (measured, failed) or ``null`` (not measured in this run). A measured
    failure is never acceptable. An unmeasured result is acceptable only from a
    PITR rehearsal, which never runs a cross-tenant check and must say so, and
    it is recorded with a residual. The scheduled drill is where isolation is
    proven, so an unmeasured drill is refused.

    The gate reads the report, so it cannot prove the producer ran: a report
    edited outside the producer could set ``null``. These cases assert what it
    can enforce — a measured failure and an unmeasured claim from the producer
    that is supposed to measure.
    """

    def _run_main(self, **overrides: str) -> tuple[dict[str, Any], str]:
        """Drive the shipped entry point once; return the report and its stdout."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            env = base_env(
                REPORT=str(path), ISO_OK="", IBEX_DRILL_METRICS_DISABLED="1"
            )
            env.update(
                {"DRILL_KIND": "pitr", "PG_MECHANISM": "pgbackrest_wal", **overrides}
            )
            saved = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                with contextlib.redirect_stdout(io.StringIO()) as printed:
                    mod.main()
            finally:
                os.environ.clear()
                os.environ.update(saved)
            return json.loads(path.read_text(encoding="utf-8")), printed.getvalue()

    def test_a_measured_isolation_pass_is_written(self) -> None:
        report, _output = self._run_main(ISO_OK="true")
        self.assertTrue(report["tenant_isolation_post_restore"])
        self.assertNotIn("residual", report)

    def test_a_measured_isolation_failure_is_refused(self) -> None:
        # A drill that ran the cross-tenant check and saw it fail is a real
        # failure: no drill_kind makes that acceptable.
        with self.assertRaises(SystemExit) as raised:
            self._run_main(ISO_OK="false")
        self.assertEqual(str(raised.exception), "tenant isolation check failed")

    def test_an_unmeasured_pitr_run_is_written_with_a_residual(self) -> None:
        # The regression: a host PITR run proves the restore, the target and the
        # frontier, and never measures isolation. That is "not measured", not
        # "failed", so the run exits zero and the report names the gap.
        report, _output = self._run_main(PG_RESTORE_TARGET="host")
        self.assertEqual(report["postgres"]["restore_target"], "host")
        self.assertIsNone(report["tenant_isolation_post_restore"])
        self.assertEqual(report["residual"], "tenant_isolation_not_measured_pitr")
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_an_unmeasured_scratch_rehearsal_records_the_same_residual(self) -> None:
        report, _output = self._run_main(
            PG_RESTORE_TARGET="scratch", ENVIRONMENT_CLASS="local-podman-scratch"
        )
        self.assertEqual(report["postgres"]["restore_target"], "scratch")
        self.assertIsNone(report["tenant_isolation_post_restore"])
        self.assertEqual(report["residual"], "tenant_isolation_not_measured_pitr")

    def test_an_unmeasured_drill_run_is_refused(self) -> None:
        # The drill is where isolation is proven. A drill report that does not
        # carry a measured result must not pass the gate.
        with self.assertRaises(SystemExit) as raised:
            self._run_main(DRILL_KIND="restore-drill")
        self.assertEqual(str(raised.exception), "tenant isolation was not measured")

    def test_an_unavailable_run_need_not_measure_isolation(self) -> None:
        report, _output = self._run_main(
            PG_MECHANISM="unavailable",
            PG_BACKUP_OK="false",
            PG_RESTORE_OK="false",
            PG_RTO_MEASURED="",
            BLOCKED_BY="the pgbackrest binary is not installed on this host",
        )
        self.assertEqual(report["postgres"]["mechanism"], "unavailable")
        self.assertIsNone(report["tenant_isolation_post_restore"])

    def test_an_allow_no_db_run_is_warned_about_and_written(self) -> None:
        # ALLOW_NO_DB means the run could not measure isolation, so the producer
        # records null. It must not borrow `false`, which now means a measured
        # failure and is refused before any exemption applies.
        report, output = self._run_main(ALLOW_NO_DB="1")
        self.assertIn("tenant isolation not proven", output)
        self.assertIsNone(report["tenant_isolation_post_restore"])
        self.assertEqual(report["residual"], "tenant_isolation_unproven_no_postgres")

    def test_a_measured_failure_is_refused_before_every_exemption(self) -> None:
        # `false` is unconditional: no drill_kind, unavailable mechanism or
        # ALLOW_NO_DB flag turns a measured cross-tenant failure into a written
        # report. Each context below accepts `null`, and must still refuse
        # `false`.
        contexts = (
            {"DRILL_KIND": "restore-drill"},
            {"ALLOW_NO_DB": "1"},
            {
                "PG_MECHANISM": "unavailable",
                "PG_BACKUP_OK": "false",
                "PG_RESTORE_OK": "false",
                "PG_RTO_MEASURED": "",
                "BLOCKED_BY": "the pgbackrest binary is not installed on this host",
            },
        )
        for context in contexts:
            with self.subTest(context=context):
                with self.assertRaises(SystemExit) as raised:
                    self._run_main(ISO_OK="false", **context)
                self.assertEqual(str(raised.exception), "tenant isolation check failed")


class BuildReportTests(unittest.TestCase):
    def test_outbox_pending_fails_report(self) -> None:
        report = mod.build_report(base_env(OUTBOX_PENDING="2"))
        self.assertFalse(report["outbox"]["rpo_pass"])
        self.assertEqual(report["outbox"]["pending"], 2)

    def test_pg_dump_rpo_pass_false_even_when_fast(self) -> None:
        report = mod.build_report(base_env())
        self.assertEqual(report["postgres"]["mechanism"], "pg_dump_fallback")
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")

    def test_allow_no_db_not_evidence(self) -> None:
        report = mod.build_report(base_env(ALLOW_NO_DB="1", ISO_OK=""))
        self.assertFalse(report["evidence_eligible"])
        self.assertTrue(report["allow_no_db"])

    def test_fixture_size_is_recorded(self) -> None:
        report = mod.build_report(base_env())
        self.assertEqual(report["fixture"]["rows"], 50000)
        self.assertEqual(report["fixture"]["orgs"], 2)
        self.assertEqual(report["fixture"]["rows_verified"], 50000)
        self.assertEqual(report["fixture"]["rows_restored"], 50000)
        self.assertTrue(report["postgres"]["rto_evidence_pass"])

    def test_pre_backup_count_cannot_claim_rto_evidence(self) -> None:
        # The restore is the step under test. A post-seed count proves the data
        # existed before the backup, not that it came back, so it must not stand
        # in for the post-restore count.
        report = mod.build_report(
            base_env(FIXTURE_ROWS_ACTUAL="50000", FIXTURE_ROWS_RESTORED="")
        )
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertEqual(report["fixture"]["rows_verified"], 50000)
        self.assertIsNone(report["fixture"]["rows_restored"])

    def test_unverified_fixture_cannot_claim_rto_evidence(self) -> None:
        # A smoke run (ALLOW_NO_DB) seeds nothing, so the requested row count
        # must not be used as if it had been observed.
        report = mod.build_report(
            base_env(FIXTURE_ROWS="50000", FIXTURE_ROWS_ACTUAL="", FIXTURE_ROWS_RESTORED="")
        )
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertIsNone(report["fixture"]["rows_verified"])
        self.assertIsNone(report["fixture"]["rows_restored"])

    def test_two_row_fixture_cannot_claim_rto_evidence(self) -> None:
        # The defect O03 names: a ~1 s restore of two rows used to report
        # rto_pass=true with nothing recording how little data that was.
        report = mod.build_report(
            base_env(FIXTURE_ROWS="2", FIXTURE_ROWS_ACTUAL="2", FIXTURE_ROWS_RESTORED="2")
        )
        self.assertTrue(report["postgres"]["rto_pass"])
        self.assertFalse(report["postgres"]["rto_evidence_pass"])
        self.assertEqual(report["fixture"]["rows"], 2)

    def test_rto_target_is_configurable(self) -> None:
        fast = mod.build_report(base_env(PG_RTO_MEASURED="10", PG_RTO_SEC="1800"))
        slow = mod.build_report(base_env(PG_RTO_MEASURED="10", PG_RTO_SEC="5"))
        self.assertTrue(fast["postgres"]["rto_pass"])
        self.assertFalse(slow["postgres"]["rto_pass"])


if __name__ == "__main__":
    unittest.main()
