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

# A 16 MiB cluster (256 segments per WAL log id) with nothing older left in
# pg_wal: the reference state a single matrix row may vary from.
_DRAINED_ARCHIVE = mod.ArchiveContinuity(
    wal_segment_size=16 * 1024 * 1024, older_segments_present=0
)


def pitr_env(**overrides: str) -> dict[str, str]:
    """A point-in-time rehearsal with every field the report grades recorded."""
    env = base_env(
        DRILL_KIND="pitr",
        PG_MECHANISM="pgbackrest_wal",
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

    def _assert_matrix(
        self,
        cases: tuple[
            tuple[str, str, bool | None, mod.ArchiveContinuity, bool | None, str], ...
        ],
    ) -> None:
        """Run one (last, current, failed, continuity, expect, why) table."""
        for last, current, failed, continuity, expect, why in cases:
            with self.subTest(why=why):
                got = mod.wal_archive_backlog(
                    last_archived_wal=last,
                    current_wal=current,
                    last_failed_after_archive=failed,
                    continuity=continuity,
                )
                self.assertEqual(got, expect, why)

    def test_matrix_drained_or_no_gap_is_not_a_backlog(self) -> None:
        # Adjacency, an archived current segment, and a one-segment log boundary
        # crossing all leave the archive drained.
        cases = (
            (
                "000000010000000000000011",
                "000000010000000000000012",
                False,
                _DRAINED_ARCHIVE,
                False,
                "current segment is one ahead and pg_wal holds nothing older",
            ),
            (
                "000000010000000000000012",
                "000000010000000000000012",
                False,
                _DRAINED_ARCHIVE,
                False,
                "current segment already archived",
            ),
            (
                "0000000100000000000000ff",
                "000000010000000000000100",
                False,
                _DRAINED_ARCHIVE,
                False,
                "the gap crosses a log boundary but is still one segment",
            ),
        )
        self._assert_matrix(cases)

    def test_matrix_real_gap_is_a_backlog(self) -> None:
        # A multi-segment gap, or an older segment left in pg_wal, is a backlog.
        cases = (
            (
                "000000010000000000000001",
                "00000001000000000000000d",
                False,
                _DRAINED_ARCHIVE,
                True,
                "twelve segments queued behind the last upload",
            ),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                False,
                mod.ArchiveContinuity(wal_segment_size=16 * 1024 * 1024, older_segments_present=3),
                True,
                "an older segment is still in pg_wal: adjacency does not prove continuity",
            ),
        )
        self._assert_matrix(cases)

    def test_matrix_unproven_inputs_fail_closed(self) -> None:
        # A name that does not parse, or a fact never measured, is not drained.
        cases = (
            (
                "000000020000000000000011",
                "000000010000000000000012",
                False,
                _DRAINED_ARCHIVE,
                None,
                "different timelines cannot be compared: fail closed",
            ),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                False,
                mod.ArchiveContinuity(wal_segment_size=16 * 1024 * 1024, older_segments_present=None),
                None,
                "the pg_wal listing was never measured",
            ),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                False,
                mod.ArchiveContinuity(wal_segment_size=None, older_segments_present=0),
                None,
                "the segment size was never measured: no multiplier to derive",
            ),
            ("", "000000010000000000000012", False, _DRAINED_ARCHIVE, None, "no last segment"),
            ("000000010000000000000011", "", False, _DRAINED_ARCHIVE, None, "no current segment"),
            (
                "not-a-segment",
                "000000010000000000000012",
                False,
                _DRAINED_ARCHIVE,
                None,
                "garbage name",
            ),
        )
        self._assert_matrix(cases)

    def test_matrix_failed_push_withholds_the_drain_claim(self) -> None:
        # A recorded failure is a backlog; an unrecorded one cannot be trusted.
        cases = (
            (
                "000000010000000000000011",
                "000000010000000000000012",
                True,
                _DRAINED_ARCHIVE,
                True,
                "a push failed after the last success: the queue is not draining",
            ),
            (
                "000000010000000000000011",
                "000000010000000000000012",
                None,
                _DRAINED_ARCHIVE,
                None,
                "failed-push state never recorded",
            ),
        )
        self._assert_matrix(cases)

    def test_segment_size_sets_the_log_multiplier(self) -> None:
        # 2**32 bytes per log id, whatever the cluster's segment size is.
        cases = ((1024 * 1024, 4096), (16 * 1024 * 1024, 256), (64 * 1024 * 1024, 64))
        for size, expect in cases:
            with self.subTest(wal_segment_size=size):
                self.assertEqual(mod.segments_per_log(size), expect)
        for unknown in (None, 0, -1, 7 * 1024 * 1024):
            with self.subTest(wal_segment_size=unknown):
                self.assertIsNone(mod.segments_per_log(unknown))

    def test_log_rollover_is_one_segment_at_every_segment_size(self) -> None:
        # A real rollover: the last segment of log N is archived and the writer
        # has just moved to segment 0 of log N+1. That is one segment of gap, not
        # a backlog — and not a negative gap either.
        cases = (
            # (segment size, last segment, current segment, segments per log)
            # Log 0's last segment, then log 1's first: a real rollover.
            (1024 * 1024, "000000010000000000000fff", "000000010000000100000000", 4096),
            (16 * 1024 * 1024, "0000000100000000000000ff", "000000010000000100000000", 256),
            (64 * 1024 * 1024, "00000001000000000000003f", "000000010000000100000000", 64),
        )
        for size, last, current, per_log in cases:
            with self.subTest(wal_segment_size=size):
                continuity = mod.ArchiveContinuity(
                    wal_segment_size=size, older_segments_present=0
                )
                self.assertFalse(
                    mod.wal_archive_backlog(
                        last_archived_wal=last,
                        current_wal=current,
                        last_failed_after_archive=False,
                        continuity=continuity,
                    ),
                    f"a one-segment rollover at {per_log} segments per log is drained",
                )

    def test_real_gap_is_a_backlog_at_every_segment_size(self) -> None:
        # The defect F3 names: a 32-segment gap across a log boundary. With a
        # fixed 256 multiplier the 1 MiB case computed -3808 and reported no
        # backlog; with the derived multiplier it is 32 segments and a backlog.
        cases = (
            # (segment size, last segment, current segment, segments in the gap)
            # The last segment of log 0 is archived; the writer is on segment 31
            # of log 1, which is 32 segments of WAL behind the archive.
            (1024 * 1024, "000000010000000000000fff", "00000001000000010000001f", 32),
            (16 * 1024 * 1024, "0000000100000000000000ff", "00000001000000010000001f", 32),
            (64 * 1024 * 1024, "00000001000000000000003f", "00000001000000010000001f", 32),
        )
        for size, last, current, gap in cases:
            with self.subTest(wal_segment_size=size):
                continuity = mod.ArchiveContinuity(
                    wal_segment_size=size, older_segments_present=0
                )
                self.assertTrue(
                    mod.wal_archive_backlog(
                        last_archived_wal=last,
                        current_wal=current,
                        last_failed_after_archive=False,
                        continuity=continuity,
                    ),
                    f"a {gap}-segment gap is a backlog at {size} byte segments",
                )

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
        report = mod.build_report(pitr_env())
        report["postgres"]["rpo_measured_sec"] = 900
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError):
            mod.assert_honest(report)


class RpoBoundTests(unittest.TestCase):
    """The RPO is a bound with a time component, not an upload age.

    With ``archive_timeout`` disabled, segment N can finish minutes before its
    upload completes while segment N+1 already holds newer commits. The upload
    age alone then reads as a zero-second RPO over data that is not in the
    archive; the bound is the upload age plus the timeout, and without a
    measured timeout there is no bound at all.
    """

    def test_unset_archive_timeout_leaves_the_rpo_unmeasured(self) -> None:
        report = mod.build_report(
            pitr_env(WAL_ARCHIVE_UPLOAD_AGE_SEC="0", WAL_ARCHIVE_TIMEOUT_SEC="")
        )
        self.assertIsNone(report["postgres"]["wal_archive_timeout_sec"])
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        # The observation is kept: it is a diagnostic, not a claim.
        self.assertEqual(report["postgres"]["wal_archive_upload_age_sec"], 0)

    def test_zero_archive_timeout_leaves_the_rpo_unmeasured(self) -> None:
        report = mod.build_report(
            pitr_env(WAL_ARCHIVE_UPLOAD_AGE_SEC="0", WAL_ARCHIVE_TIMEOUT_SEC="0")
        )
        self.assertEqual(report["postgres"]["wal_archive_timeout_sec"], 0)
        self.assertIsNone(report["postgres"]["rpo_measured_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_archive_timeout_is_part_of_the_bound(self) -> None:
        report = mod.build_report(
            pitr_env(WAL_ARCHIVE_UPLOAD_AGE_SEC="17", WAL_ARCHIVE_TIMEOUT_SEC="60")
        )
        self.assertEqual(report["postgres"]["wal_archive_upload_age_sec"], 17)
        self.assertEqual(report["postgres"]["wal_archive_timeout_sec"], 60)
        self.assertEqual(report["postgres"]["rpo_measured_sec"], 77)
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_the_timeout_alone_can_put_a_run_over_target(self) -> None:
        # 250 s of upload age is inside the 300 s target; the 60 s the timeout
        # adds is not. A pass here would understate the real bound.
        report = mod.build_report(
            pitr_env(WAL_ARCHIVE_UPLOAD_AGE_SEC="250", WAL_ARCHIVE_TIMEOUT_SEC="60")
        )
        self.assertEqual(report["postgres"]["rpo_measured_sec"], 310)
        self.assertFalse(report["postgres"]["rpo_pass"])


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
