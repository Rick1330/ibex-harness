#!/usr/bin/env python3
"""PITR cases: the recovery target that was asked for, and the WAL backlog.

A point-in-time rehearsal makes exactly two claims a reader has to trust — that
the restored cluster stopped at the requested moment, and that the RPO quoted
was measured against a drained archive. Both are graded here against a PITR
environment, so the three classes share one builder rather than three
near-identical ones.
"""

from __future__ import annotations

import unittest

from restore_drill_test_support import base_env, mod


def pitr_env(**overrides: str) -> dict[str, str]:
    """A point-in-time rehearsal with every field the report grades recorded."""
    env = base_env(
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


class PitrReportTests(unittest.TestCase):
    """A point-in-time rehearsal reports the target it asked for and reached."""

    def test_reached_target_is_recorded_and_eligible(self) -> None:
        report = mod.build_report(pitr_env())
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
        report = mod.build_report(
            pitr_env(RECOVERY_TARGET_REACHED="false", RECOVERY_REPLAY_TIMESTAMP="2026-11-16T10:00:09Z")
        )
        self.assertFalse(report["postgres"]["recovery_target_reached"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["evidence_eligible"])

    def test_no_target_requested_is_not_a_reached_target(self) -> None:
        report = mod.build_report(
            pitr_env(TARGET_TIMESTAMP="", RECOVERY_TARGET_REACHED="", RECOVERY_REPLAY_TIMESTAMP="")
        )
        self.assertIsNone(report["postgres"]["target_timestamp"])
        self.assertIsNone(report["postgres"]["recovery_target_reached"])


class WalArchiveBacklogTests(unittest.TestCase):
    """An RPO read from an undrained archive is not an upper bound on the lag.

    `last_archived_time` is when an upload completed, not the transaction time
    the segment covers. While a backlog drains, an old segment uploads now and
    its age looks like a fresh recovery point, so the queue state has to be part
    of the claim.
    """

    def test_backlog_matrix(self) -> None:
        cases = (
            # (last, current, failed, expect, why)
            (
                "000000010000000000000011",
                "000000010000000000000012",
                False,
                False,
                "current segment is one ahead: nothing older is queued",
            ),
            (
                "000000010000000000000012",
                "000000010000000000000012",
                False,
                False,
                "current segment already archived",
            ),
            (
                "000000010000000000000001",
                "00000001000000000000000d",
                False,
                True,
                "twelve segments queued behind the last upload",
            ),
            (
                "0000000100000000000000ff",
                "000000010000000000000100",
                False,
                False,
                "the gap crosses a log boundary but is still one segment",
            ),
            (
                "000000020000000000000011",
                "000000010000000000000012",
                False,
                True,
                "different timelines cannot be compared: fail closed",
            ),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                True,
                True,
                "a push failed after the last success: the queue is not draining",
            ),
            ("", "000000010000000000000012", False, None, "no last segment"),
            ("000000010000000000000011", "", False, None, "no current segment"),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                None,
                None,
                "failed-push state never recorded",
            ),
            ("not-a-segment", "000000010000000000000012", False, None, "garbage name"),
        )
        for last, current, failed, expect, why in cases:
            with self.subTest(why=why):
                got = mod.wal_archive_backlog(
                    last_archived_wal=last,
                    current_wal=current,
                    last_failed_after_archive=failed,
                )
                self.assertEqual(got, expect, why)

    def test_drained_archive_can_claim_rpo_pass(self) -> None:
        report = mod.build_report(pitr_env())
        self.assertFalse(report["postgres"]["wal_archive_backlog"])
        self.assertTrue(report["postgres"]["rpo_pass"])
        self.assertTrue(report["evidence_eligible"])

    def test_backlogged_archive_cannot_claim_rpo_pass(self) -> None:
        # A one-second-old upload of a segment written twenty minutes ago is a
        # backlog draining, not a one-second RPO.
        report = mod.build_report(
            pitr_env(
                PG_RPO_MEASURED="1",
                WAL_ARCHIVE_UPLOAD_AGE_SEC="1",
                WAL_ARCHIVE_LAST_SEGMENT="000000010000000000000001",
                WAL_ARCHIVE_CURRENT_SEGMENT="00000001000000000000000d",
            )
        )
        self.assertTrue(report["postgres"]["wal_archive_backlog"])
        self.assertEqual(report["postgres"]["wal_archive_upload_age_sec"], 1)
        # The observation is kept, but it is not carried as the measured RPO.
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        # The restore and its target are still proven; only the RPO claim is
        # withheld, so the report remains citable for what it did prove.
        self.assertTrue(report["evidence_eligible"])

    def test_unrecorded_archive_state_cannot_claim_rpo_pass(self) -> None:
        report = mod.build_report(
            pitr_env(
                WAL_ARCHIVE_LAST_SEGMENT="",
                WAL_ARCHIVE_CURRENT_SEGMENT="",
                WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="",
            )
        )
        self.assertIsNone(report["postgres"]["wal_archive_backlog"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_honesty_validator_refuses_a_forged_rpo_pass_over_a_backlog(self) -> None:
        report = mod.build_report(
            pitr_env(
                WAL_ARCHIVE_LAST_SEGMENT="000000010000000000000001",
                WAL_ARCHIVE_CURRENT_SEGMENT="00000001000000000000000d",
            )
        )
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError):
            mod.assert_honest(report)

    def test_honesty_validator_refuses_an_rpo_pass_over_the_target(self) -> None:
        report = mod.build_report(pitr_env(PG_RPO_MEASURED="30"))
        report["postgres"]["rpo_measured_sec"] = 900
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError):
            mod.assert_honest(report)


class TargetVerificationTests(unittest.TestCase):
    """A requested recovery target that was not proven is a failed claim."""

    def test_empty_target_result_cannot_pass(self) -> None:
        # The producer records no result when psql fails, the row is malformed,
        # or replay is -1. That is a target nobody checked.
        for empty in ("", "   "):
            with self.subTest(target_reached=repr(empty)):
                report = mod.build_report(
                    pitr_env(
                        RECOVERY_TARGET_REACHED=empty,
                        RECOVERY_REPLAY_TIMESTAMP="",
                    )
                )
                self.assertIsNone(report["postgres"]["recovery_target_reached"])
                self.assertFalse(report["postgres"]["rpo_pass"])
                self.assertFalse(report["evidence_eligible"])
                report["postgres"]["rpo_pass"] = True
                with self.assertRaises(mod.ReportHonestyError):
                    mod.assert_honest(report)

    def test_missing_target_result_with_a_requested_target_cannot_pass(self) -> None:
        # TARGET_TIMESTAMP present and RECOVERY_TARGET_REACHED absent is the
        # host branch's old behaviour; it must fail closed, not pass.
        env = pitr_env()
        env.pop("RECOVERY_TARGET_REACHED")
        report = mod.build_report(env)
        self.assertEqual(report["postgres"]["target_timestamp"], "2026-11-16T10:00:00Z")
        self.assertIsNone(report["postgres"]["recovery_target_reached"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["evidence_eligible"])

    def test_fractional_replay_timestamp_is_preserved(self) -> None:
        # The producer compares exact microseconds; the report must carry the
        # precision it was given instead of rounding it to a whole second.
        report = mod.build_report(
            pitr_env(
                TARGET_TIMESTAMP="2026-11-16T10:00:00.900Z",
                RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58.800Z",
            )
        )
        self.assertEqual(
            report["postgres"]["recovery_replay_timestamp"],
            "2026-11-16T09:59:58.800Z",
        )
        self.assertTrue(report["postgres"]["rpo_pass"])


if __name__ == "__main__":
    unittest.main()
