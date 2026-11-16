#!/usr/bin/env python3
"""Honesty cases: what a report may claim, and what the validator refuses.

Every case here asserts a claim the report is *not* allowed to make. They are
grouped by the claim under test — outbox RPO, Postgres RPO by mechanism, an
unavailable run, and the report's own shape — and none of them reads a file or
runs a script.
"""

from __future__ import annotations

import unittest

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
            ("pg_dump_fallback", False, False),
            ("pgbackrest_wal", False, True),
            ("unmeasured", False, False),
            # An undrained archive, or one whose state was never recorded, makes
            # the measured age no upper bound: the claim must stay false.
            ("pgbackrest_wal", True, False),
            ("pgbackrest_wal", None, False),
        )
        for mechanism, backlog, expect in cases:
            with self.subTest(mechanism=mechanism, backlog=backlog):
                got = mod.postgres_rpo_pass(
                    {
                        "backup_ok": True,
                        "restore_ok": True,
                        "measured": 12,
                        "target": 300,
                        "mechanism": mechanism,
                        "backlog": backlog,
                    }
                )
                self.assertEqual(got, expect)


class PgBackrestRpoGateTests(unittest.TestCase):
    """rpo_pass is a PITR claim: only a measured, fresh pgBackRest WAL run earns it."""

    def test_pgbackrest_wal_with_null_rpo_cannot_pass(self) -> None:
        # Archiving was proven to work, but no RPO was measured. "Archiving is
        # on" is not "the RPO target was met", so the claim must stay false.
        report = mod.build_report(
            base_env(PG_MECHANISM="pgbackrest_wal", PG_RPO_MEASURED="", WAL_ARCHIVE_OK="true")
        )
        self.assertEqual(report["postgres"]["mechanism"], "pgbackrest_wal")
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_with_measured_rpo_can_pass(self) -> None:
        # The counterpart to the test above: the gate is not permanently closed.
        report = mod.build_report(
            base_env(
                PG_MECHANISM="pgbackrest_wal",
                PG_RPO_MEASURED="30",
                PG_RPO_SEC="300",
                WAL_ARCHIVE_OK="true",
            )
        )
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_pgbackrest_wal_over_target_fails(self) -> None:
        report = mod.build_report(
            base_env(
                PG_MECHANISM="pgbackrest_wal",
                PG_RPO_MEASURED="900",
                PG_RPO_SEC="300",
                WAL_ARCHIVE_OK="true",
            )
        )
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_pg_dump_fallback_never_claims_rpo_pass(self) -> None:
        # Even a fast, measured number cannot make a dump a PITR mechanism.
        report = mod.build_report(
            base_env(PG_MECHANISM="pg_dump_fallback", PG_RPO_MEASURED="1", WAL_ARCHIVE_OK="true")
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

    def test_honesty_validator_refuses_rpo_pass_without_a_measurement(self) -> None:
        report = mod.build_report(base_env(PG_MECHANISM="pgbackrest_wal", PG_RPO_MEASURED=""))
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError):
            mod.assert_honest(report)


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
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertEqual(report["postgres_rpo_residual"], "not_pitr_pg_dump_fallback_#869")

    def test_allow_no_db_not_evidence(self) -> None:
        report = mod.build_report(base_env(ALLOW_NO_DB="1", ISO_OK="false"))
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
