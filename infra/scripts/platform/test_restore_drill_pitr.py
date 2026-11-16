#!/usr/bin/env python3
"""PITR cases: the recovery target, the WAL backlog, and the RPO upper bound.

A restore makes two claims a reader has to trust — that the restored cluster
stopped where it was asked to, and that the RPO upper bound is the frontier the
restore demonstrated. Both are graded here against one PITR environment, so the
classes share a builder rather than each carrying a near-identical one.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from restore_drill_test_support import base_env, mod

# The committed rehearsal, read from disk so the artefact itself is graded.
ARTEFACT = (
    Path(__file__).resolve().parents[3] / "engineering" / "evidence" / "pitr" / "pitr-report.json"
)

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
        PG_RESTORE_TARGET="scratch",
        WAL_ARCHIVE_OK="true",
        TARGET_TIMESTAMP="2026-11-16T10:00:00Z",
        RECOVERY_TARGET_REACHED="true",
        RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58Z",
        CLUSTER_DATA_BYTES="1048576",
        RESTORED_ORGS="3",
        RESTORED_MEMORIES="50000",
        # The PITR producer never measures isolation, so it records that fact
        # rather than a failure it never observed.
        ISO_OK="",
    )
    env.update(overrides)
    return env


def untargeted_env(**overrides: str) -> dict[str, str]:
    """A run with no recovery target: the only shape that can carry a bound."""
    env = pitr_env(
        TARGET_TIMESTAMP="",
        RECOVERY_TARGET_REACHED="",
        WAL_ARCHIVE_QUIESCED_AT="2026-11-16T10:00:05Z",
        # An untargeted run is a destructive restore, not a scratch rehearsal.
        PG_RESTORE_TARGET="host",
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
        # A targeted restore proves the target, not an RPO: no bound is carried.
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertEqual(
            report["postgres_rpo_residual"], "targeted_restore_proves_target_not_rpo"
        )
        # A rehearsal never measures tenant isolation: the report says so
        # instead of recording a failure the producer never observed.
        self.assertIsNone(report["tenant_isolation_post_restore"])
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
        # No replay instant was recorded either, so no bound is claimed.
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])


class WalArchiveBacklogTests(unittest.TestCase):
    """An RPO read from an undrained archive is not an upper bound on the lag.

    `last_archived_time` is when an upload completed, not the transaction time
    the segment covers. While a backlog drains, an old segment uploads now and
    its age looks like a fresh recovery point, so the upload age cannot be the
    bound. The queue state is recorded beside the number as a diagnostic; the
    bound itself is the frontier the restore demonstrated.
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

    def test_matrix_unproven_inputs_are_unmeasured_not_drained(self) -> None:
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

    def test_an_unmeasured_backlog_does_not_withhold_a_demonstrated_bound(self) -> None:
        # The defect F1 names: PostgreSQL retains already-archived segments in
        # pg_wal until recycling, so a positive count of segments older than
        # last_archived_wal did not mean they were pending archival — a healthy
        # PITR run reported a backlog until those files were recycled. The
        # producer no longer measures the count, so the report records null —
        # exactly as a drill report does — and it gates nothing either way.
        report = mod.build_report(untargeted_env())
        self.assertEqual(report["drill_kind"], "pitr")
        self.assertIsNone(report["postgres"]["wal_archive_backlog"])
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)
        self.assertTrue(report["postgres"]["rpo_pass"])
        self.assertTrue(report["evidence_eligible"])

    def test_a_backlogged_archive_does_not_withhold_a_demonstrated_bound(self) -> None:
        # The deliberate reversal: a backlog is a diagnostic, not a gate. The
        # restore replayed every segment up to the replay point, so the frontier
        # it demonstrated is the proof — a gap would have stopped recovery or
        # truncated the replay timestamp, and the number would show it. The
        # continuity input is hand-set here because no producer measures it any
        # more; the case proves the writer does not gate on it either way.
        report = mod.build_report(
            untargeted_env(
                WAL_ARCHIVE_UPLOAD_AGE_SEC="1",
                WAL_ARCHIVE_LAST_SEGMENT="000000010000000000000001",
                WAL_ARCHIVE_CURRENT_SEGMENT="00000001000000000000000d",
                WAL_ARCHIVE_OLDER_SEGMENTS="3",
            )
        )
        self.assertTrue(report["postgres"]["wal_archive_backlog"])
        self.assertEqual(report["postgres"]["wal_archive_upload_age_sec"], 1)
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_unrecorded_archive_state_is_a_diagnostic_not_a_gate(self) -> None:
        # An unmeasured queue cannot tell an operator anything, but it cannot
        # withdraw a bound the restore demonstrated either.
        report = mod.build_report(
            untargeted_env(
                WAL_ARCHIVE_LAST_SEGMENT="",
                WAL_ARCHIVE_CURRENT_SEGMENT="",
                WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="",
            )
        )
        self.assertIsNone(report["postgres"]["wal_archive_backlog"])
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)
        self.assertTrue(report["postgres"]["rpo_pass"])


class RpoUpperBoundTests(unittest.TestCase):
    """The bound is the frontier the restore demonstrated, referenced to the quiesce.

    ``ceil(wal_archive_quiesced_at - recovery_replay_timestamp)``. It is not
    inferred from ``pg_stat_archiver``: a push slower than ``archive_timeout``
    leaves the counters looking drained while the newest recoverable commit is
    older than the number they would produce.
    """

    def test_drained_counters_over_an_old_frontier_are_not_a_pass(self) -> None:
        # The reviewer's counterexample: every counter says the queue is drained,
        # and the frontier is still 400 s old. The number is the frontier.
        report = mod.build_report(
            untargeted_env(
                WAL_ARCHIVE_OK="true",
                WAL_ARCHIVE_UPLOAD_AGE_SEC="1",
                WAL_ARCHIVE_TIMEOUT_SEC="60",
                WAL_ARCHIVE_QUIESCED_AT="2026-11-16T10:07:38Z",
                RECOVERY_REPLAY_TIMESTAMP="2026-11-16T10:00:58Z",
            )
        )
        self.assertIsNone(report["postgres"]["wal_archive_backlog"])
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 400)
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertTrue(report["evidence_eligible"])

    def test_a_targeted_restore_records_no_bound(self) -> None:
        report = mod.build_report(
            pitr_env(WAL_ARCHIVE_QUIESCED_AT="2026-11-16T10:00:01Z")
        )
        self.assertEqual(report["postgres"]["target_timestamp"], "2026-11-16T10:00:00Z")
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertEqual(
            report["postgres_rpo_residual"], "targeted_restore_proves_target_not_rpo"
        )
        # The target and the restore are still proven, so it stays citable.
        self.assertTrue(report["postgres"]["recovery_target_reached"])
        self.assertTrue(report["evidence_eligible"])

    def test_an_unreadable_instant_is_not_a_bound(self) -> None:
        # Empty, unparseable, zone-less and non-UTC values are all "not
        # measured": the frontier pair has to be two real UTC instants.
        bad_values = ("", "yesterday", "2026-11-16T10:00:00", "2026-11-16T10:00:00+02:00")
        for bad in bad_values:
            with self.subTest(instant=bad):
                self.assertIsNone(mod.rpo_upper_bound(bad, "2026-11-16T10:00:00Z"))
        report = mod.build_report(untargeted_env())
        report["postgres"]["wal_archive_quiesced_at"] = "yesterday"
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("must be an ISO8601 UTC timestamp", str(raised.exception))

    def test_a_negative_difference_is_unmeasured_not_zero(self) -> None:
        self.assertIsNone(
            mod.rpo_upper_bound("2026-11-16T10:00:00Z", "2026-11-16T10:00:01Z")
        )
        report = mod.build_report(
            untargeted_env(
                WAL_ARCHIVE_QUIESCED_AT="2026-11-16T09:59:50Z",
                RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58Z",
            )
        )
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_the_bound_rounds_up(self) -> None:
        # 2.5 s is 3 s: a bound must not round toward optimism.
        self.assertEqual(
            mod.rpo_upper_bound("2026-11-16T10:00:02.500Z", "2026-11-16T10:00:00Z"), 3
        )

    def test_an_unset_archive_timeout_does_not_withhold_the_bound(self) -> None:
        report = mod.build_report(untargeted_env(WAL_ARCHIVE_TIMEOUT_SEC=""))
        self.assertIsNone(report["postgres"]["wal_archive_timeout_sec"])
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)
        self.assertTrue(report["postgres"]["rpo_pass"])

    def test_a_non_numeric_archive_timeout_is_unproven_not_fatal(self) -> None:
        # The writer used to raise on this *after* the restore ran, so the run
        # left no report at all.
        self.assertIsNone(mod.parse_int_or_none("unknown"))
        report = mod.build_report(untargeted_env(WAL_ARCHIVE_TIMEOUT_SEC="unknown"))
        self.assertIsNone(report["postgres"]["wal_archive_timeout_sec"])
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)

    def test_a_forged_bound_is_refused(self) -> None:
        report = mod.build_report(untargeted_env())
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 7)
        report["postgres"]["rpo_upper_bound_sec"] = 17
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("does not match the frontier", str(raised.exception))

    def test_a_pass_without_a_quiesce_instant_is_refused(self) -> None:
        report = mod.build_report(untargeted_env(WAL_ARCHIVE_QUIESCED_AT=""))
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("wal_archive_quiesced_at", str(raised.exception))

    def test_a_pass_without_a_replay_instant_is_refused(self) -> None:
        report = mod.build_report(untargeted_env(RECOVERY_REPLAY_TIMESTAMP=""))
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("recovery_replay_timestamp", str(raised.exception))

    def test_a_pass_over_the_target_is_refused(self) -> None:
        # The frontier derives 400 s; the builder withholds the pass, and a
        # report that claims one anyway is refused.
        report = mod.build_report(
            untargeted_env(
                WAL_ARCHIVE_QUIESCED_AT="2026-11-16T10:07:38Z",
                RECOVERY_REPLAY_TIMESTAMP="2026-11-16T10:00:58Z",
            )
        )
        self.assertEqual(report["postgres"]["rpo_upper_bound_sec"], 400)
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("above the 300s target", str(raised.exception))


class CommittedPitrArtefactTests(unittest.TestCase):
    """The committed rehearsal is a targeted run, and its artefact says so."""

    def _artefact(self) -> dict[str, Any]:
        return json.loads(ARTEFACT.read_text(encoding="utf-8"))

    def test_the_committed_artefact_carries_no_rpo_claim(self) -> None:
        report = self._artefact()
        self.assertNotIn("rpo_measured_sec", report["postgres"])
        self.assertNotIn("wal_archive_older_segments", report["postgres"])
        # The branch the run took, and the archive diagnostics the shipped
        # producer writes. Omitting them is what let the artefact stop being
        # producer-faithful; the upload age is the one the transcript recorded.
        self.assertEqual(report["postgres"]["restore_target"], "scratch")
        self.assertEqual(report["postgres"]["wal_archive_upload_age_sec"], 17)
        for field in (
            "wal_archive_timeout_sec",
            "wal_archive_wal_segment_size",
            "wal_archive_backlog",
        ):
            with self.subTest(field=field):
                self.assertIn(field, report["postgres"])
        self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertEqual(
            report["postgres_rpo_residual"], "targeted_restore_proves_target_not_rpo"
        )
        self.assertTrue(report["postgres"]["recovery_target_reached"])
        self.assertTrue(report["evidence_eligible"])
        # The rehearsal never measured tenant isolation, and says so.
        self.assertIsNone(report["tenant_isolation_post_restore"])
        self.assertEqual(report["residual"], "tenant_isolation_not_measured_pitr")
        mod.assert_honest(report)

    def test_a_forced_pass_on_the_artefact_is_refused(self) -> None:
        report = self._artefact()
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("untargeted restore", str(raised.exception))
        # Without the target it fails on the missing quiesce instant instead.
        report["postgres"]["target_timestamp"] = None
        with self.assertRaises(mod.ReportHonestyError) as raised:
            mod.assert_honest(report)
        self.assertIn("wal_archive_quiesced_at", str(raised.exception))


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
        # The target is proven; the run is targeted, so it carries no RPO claim.
        self.assertFalse(report["postgres"]["rpo_pass"])


if __name__ == "__main__":
    unittest.main()
