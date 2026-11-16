#!/usr/bin/env python3
"""Unit tests for restore_drill_report (outbox RPO + pg_dump honesty + O02/O03)."""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import shutil
import subprocess  # nosec B404 - the drill tests must run the real script; argv is fixed and there is no shell
import sys
import tempfile
import unittest
from pathlib import Path

_PLATFORM_DIR = Path(__file__).resolve().parent
_REPORT_PY = _PLATFORM_DIR / "restore_drill_report.py"
_DRILL_SH = _PLATFORM_DIR / "restore-drill.sh"
_PITR_RESTORE_SH = _PLATFORM_DIR / "pgbackrest-restore.sh"
_spec = importlib.util.spec_from_file_location("restore_drill_report", _REPORT_PY)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load restore_drill_report from {_REPORT_PY}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["restore_drill_report"] = _mod
_spec.loader.exec_module(_mod)

# Container-engine stub for the scratch PITR path. Every psql answer is matched
# on the SQL the script actually issues, so a query this stub does not know
# returns nothing — which the script must treat as unmeasured, not as a pass.
# The values are fixtures: none is a credential and none is real cluster data.
_ENGINE_STUB = r"""#!/usr/bin/env bash
set -u
first="${1:-}"
shift || true
case "$first" in
  volume | rm | logs | run) exit 0 ;;
  inspect) printf '%s\n' "${STUB_NETWORK:-stubnet}"; exit 0 ;;
  compose)
    case " $* " in
      *" stop "*) exit 1 ;;
      *" ps -q objectstore "*) printf 'objectcid\n' ;;
      *" config "*) printf '%s\n' "${STUB_COMPOSE_CONFIG:-}" ;;
      *) : ;;
    esac
    exit 0
    ;;
  exec)
    printf 'EXEC %s\n' "$*" >>"${STUB_LOG:-/dev/null}"
    case " $* " in
      *pg_is_in_recovery*) printf 'f\n' ;;
      *pg_last_xact_replay_timestamp*) printf '%s|12345678\n' "${STUB_REPLAY_US:--1}" ;;
      *ibex_core.organizations*) printf '2\n' ;;
      *ibex_core.memories*) printf '9\n' ;;
      *) : ;;
    esac
    exit 0
    ;;
esac
exit 0
"""


def _utc_micros(iso: str) -> int:
    """Integer microseconds for an ISO8601 UTC timestamp, without float rounding."""
    parsed = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    delta = parsed - epoch
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


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
        # A drained archive: the newest archived segment is the one before the
        # one being written, and no push has failed since the last success.
        "WAL_ARCHIVE_OK": "true",
        "WAL_ARCHIVE_UPLOAD_AGE_SEC": "30",
        "WAL_ARCHIVE_LAST_SEGMENT": "000000010000000000000011",
        "WAL_ARCHIVE_CURRENT_SEGMENT": "000000010000000000000012",
        "WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE": "false",
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
                got = _mod.postgres_rpo_pass(
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
            env = self._unavailable_env(BLOCKED_BY=empty)
            with self.subTest(blocked_by=repr(empty)):
                with self.assertRaises(_mod.ReportHonestyError):
                    _mod.build_report(env)

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
                got = _mod.wal_archive_backlog(
                    last_archived_wal=last,
                    current_wal=current,
                    last_failed_after_archive=failed,
                )
                self.assertEqual(got, expect, why)

    def _pitr_env(self, **overrides: str) -> dict[str, str]:
        env = _base_env(
            DRILL_KIND="pitr",
            PG_MECHANISM="pgbackrest_wal",
            PG_RPO_MEASURED="17",
            WAL_ARCHIVE_OK="true",
            TARGET_TIMESTAMP="2026-11-16T10:00:00Z",
            RECOVERY_TARGET_REACHED="true",
            RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58Z",
            ISO_OK="false",
        )
        env.update(overrides)
        return env

    def test_drained_archive_can_claim_rpo_pass(self) -> None:
        report = _mod.build_report(self._pitr_env())
        self.assertFalse(report["postgres"]["wal_archive_backlog"])
        self.assertTrue(report["postgres"]["rpo_pass"])
        self.assertTrue(report["evidence_eligible"])

    def test_backlogged_archive_cannot_claim_rpo_pass(self) -> None:
        # A one-second-old upload of a segment written twenty minutes ago is a
        # backlog draining, not a one-second RPO.
        report = _mod.build_report(
            self._pitr_env(
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
        report = _mod.build_report(
            self._pitr_env(
                WAL_ARCHIVE_LAST_SEGMENT="",
                WAL_ARCHIVE_CURRENT_SEGMENT="",
                WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="",
            )
        )
        self.assertIsNone(report["postgres"]["wal_archive_backlog"])
        self.assertFalse(report["postgres"]["rpo_pass"])

    def test_honesty_validator_refuses_a_forged_rpo_pass_over_a_backlog(self) -> None:
        report = _mod.build_report(
            self._pitr_env(
                WAL_ARCHIVE_LAST_SEGMENT="000000010000000000000001",
                WAL_ARCHIVE_CURRENT_SEGMENT="00000001000000000000000d",
            )
        )
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(_mod.ReportHonestyError):
            _mod.assert_honest(report)

    def test_honesty_validator_refuses_an_rpo_pass_over_the_target(self) -> None:
        report = _mod.build_report(self._pitr_env(PG_RPO_MEASURED="30"))
        report["postgres"]["rpo_measured_sec"] = 900
        report["postgres"]["rpo_pass"] = True
        with self.assertRaises(_mod.ReportHonestyError):
            _mod.assert_honest(report)


class TargetVerificationTests(unittest.TestCase):
    """A requested recovery target that was not proven is a failed claim."""

    def _pitr_env(self, **overrides: str) -> dict[str, str]:
        env = _base_env(
            DRILL_KIND="pitr",
            PG_MECHANISM="pgbackrest_wal",
            PG_RPO_MEASURED="17",
            WAL_ARCHIVE_OK="true",
            TARGET_TIMESTAMP="2026-11-16T10:00:00Z",
            RECOVERY_TARGET_REACHED="true",
            RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58Z",
            ISO_OK="false",
        )
        env.update(overrides)
        return env

    def test_empty_target_result_cannot_pass(self) -> None:
        # The producer records no result when psql fails, the row is malformed,
        # or replay is -1. That is a target nobody checked.
        for empty in ("", "   "):
            with self.subTest(target_reached=repr(empty)):
                report = _mod.build_report(
                    self._pitr_env(
                        RECOVERY_TARGET_REACHED=empty,
                        RECOVERY_REPLAY_TIMESTAMP="",
                    )
                )
                self.assertIsNone(report["postgres"]["recovery_target_reached"])
                self.assertFalse(report["postgres"]["rpo_pass"])
                self.assertFalse(report["evidence_eligible"])
                report["postgres"]["rpo_pass"] = True
                with self.assertRaises(_mod.ReportHonestyError):
                    _mod.assert_honest(report)

    def test_missing_target_result_with_a_requested_target_cannot_pass(self) -> None:
        # TARGET_TIMESTAMP present and RECOVERY_TARGET_REACHED absent is the
        # host branch's old behaviour; it must fail closed, not pass.
        env = self._pitr_env()
        env.pop("RECOVERY_TARGET_REACHED")
        report = _mod.build_report(env)
        self.assertEqual(report["postgres"]["target_timestamp"], "2026-11-16T10:00:00Z")
        self.assertIsNone(report["postgres"]["recovery_target_reached"])
        self.assertFalse(report["postgres"]["rpo_pass"])
        self.assertFalse(report["evidence_eligible"])

    def test_fractional_replay_timestamp_is_preserved(self) -> None:
        # The producer compares exact microseconds; the report must carry the
        # precision it was given instead of rounding it to a whole second.
        report = _mod.build_report(
            self._pitr_env(
                TARGET_TIMESTAMP="2026-11-16T10:00:00.900Z",
                RECOVERY_REPLAY_TIMESTAMP="2026-11-16T09:59:58.800Z",
            )
        )
        self.assertEqual(
            report["postgres"]["recovery_replay_timestamp"],
            "2026-11-16T09:59:58.800Z",
        )
        self.assertTrue(report["postgres"]["rpo_pass"])


class ReportWriterTests(unittest.TestCase):
    """A run that cannot write its evidence must not look like one that did."""

    def test_write_report_replaces_atomically_and_leaves_no_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pitr-report.json"
            path.write_text('{"stale": true}\n', encoding="utf-8")
            _mod.write_report(path, {"fresh": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"fresh": True})
            leftovers = [p.name for p in Path(directory).iterdir() if p.name != path.name]
            self.assertEqual(leftovers, [])

    def test_write_report_failure_is_loud(self) -> None:
        # A path whose parent is a regular file cannot be created: the writer
        # must exit non-zero and say so rather than return quietly.
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("", encoding="utf-8")
            path = blocker / "pitr-report.json"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                with self.assertRaises(SystemExit) as raised:
                    _mod.write_report(path, {"fresh": True})
            self.assertNotEqual(raised.exception.code, 0)
            self.assertIn("could not write the report", printed.getvalue())

    def test_main_exits_non_zero_when_the_report_cannot_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("", encoding="utf-8")
            env = _base_env(REPORT=str(blocker / "pitr-report.json"), ALLOW_NO_DB="1")
            saved = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        _mod.main()
            finally:
                os.environ.clear()
                os.environ.update(saved)
            self.assertNotEqual(raised.exception.code, 0)


class PitrRestoreScriptTests(unittest.TestCase):
    """End-to-end cases against the real restore script, with a stubbed engine.

    The report writer is only half of the honesty boundary: the producer decides
    what it observed. These cases drive `pgbackrest-restore.sh` through its
    scratch branch so the comparison, the exit trap and the report write are the
    ones that ship.
    """

    def _run_restore(
        self,
        root: Path,
        *,
        target: str,
        replay_us: int,
        report: Path,
        scratch: str | None = "stubvol",
    ) -> subprocess.CompletedProcess:
        bindir = root / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "stub-engine"
        stub.write_text(_ENGINE_STUB, encoding="utf-8")
        stub.chmod(0o755)
        conf = root / "pgbackrest.conf"
        conf.write_text("[global]\nrepo1-type=s3\n", encoding="utf-8")
        compose = root / "compose.yml"
        compose.write_text("services: {}\n", encoding="utf-8")
        env = {
            **os.environ,
            "PGBACKREST_REPO1_CIPHER_PASS": "fixture-cipher",
            "PGBACKREST_REPO1_S3_KEY": "fixture-key",
            "PGBACKREST_REPO1_S3_KEY_SECRET": "fixture-secret",
            "PGBACKREST_CONF": str(conf),
            "PGBACKREST_STANZA": "ibex-main",
            "COMPOSE_FILE": str(compose),
            "IBEX_CONTAINER_CLI": str(stub),
            "PGBACKREST_RESTORE_TARGET": target,
            "PGBACKREST_RESTORE_REPORT": str(report),
            # A host data directory that does not exist, so the destructive
            # branch refuses deterministically when no scratch volume is given.
            "PGBACKREST_PGDATA": str(root / "no-such-datadir"),
            "STUB_REPLAY_US": str(replay_us),
            "STUB_LOG": str(root / "engine.log"),
            # Compose metadata for the profile: what a stopped primary still
            # answers, and the identity a recovery must connect with.
            "STUB_COMPOSE_CONFIG": (
                '{"services": {"postgres": {"environment": '
                '{"POSTGRES_USER": "ibex", "POSTGRES_DB": "ibex"}}}}'
            ),
            "TMPDIR": str(root),
        }
        if scratch is None:
            env.pop("PGBACKREST_RESTORE_SCRATCH_VOLUME", None)
        else:
            env["PGBACKREST_RESTORE_SCRATCH_VOLUME"] = scratch
        # Fixed argv, no shell: the only variable is the script path this test owns.
        return subprocess.run(  # nosec B603
            ["/bin/bash", str(_PITR_RESTORE_SH)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_replay_fractionally_before_the_target_passes(self) -> None:
        # The defect: replay .800 against target .900. PostgreSQL rounds the
        # replay epoch to 49 and `date +%s` truncates the target to 48, so the
        # whole-second comparison failed a restore that was correct.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48.900Z",
                replay_us=_utc_micros("2026-11-16T07:42:48.800Z"),
                report=report,
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("recovery target reached", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])
            self.assertEqual(
                written["postgres"]["recovery_replay_timestamp"],
                "2026-11-16T07:42:48.800000Z",
            )
            self.assertTrue(written["postgres"]["restore_ok"])

    def test_replay_fractionally_after_the_target_fails(self) -> None:
        # The other half of the same comparison: rounding must not hide a miss.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48.100Z",
                replay_us=_utc_micros("2026-11-16T07:42:48.900Z"),
                report=report,
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("replayed past the target", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(written["postgres"]["recovery_target_reached"])
            self.assertFalse(written["postgres"]["restore_ok"])
            self.assertTrue(written["blocked_by"])

    def test_unproven_target_fails_a_targeted_restore(self) -> None:
        # psql failing, a malformed row, or replay == -1 leaves the result empty.
        # A targeted restore with an unproven target is not a success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48Z",
                replay_us=-1,
                report=report,
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("did not prove the requested target", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertIsNone(written["postgres"]["recovery_target_reached"])
            self.assertFalse(written["postgres"]["restore_ok"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertFalse(written["evidence_eligible"])
            self.assertTrue(written["blocked_by"])

    def test_offline_primary_uses_the_profile_identity(self) -> None:
        # The live primary is stopped — the exact state of a real recovery. The
        # restored cluster is bootstrapped with the profile's `ibex` role, so a
        # verification that connected as `postgres` would fail every query for
        # 120 s and fail a restore that worked.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48Z",
                replay_us=_utc_micros("2026-11-16T07:42:47Z"),
                report=report,
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            calls = (root / "engine.log").read_text(encoding="utf-8")
            self.assertIn("-U ibex -d ibex", calls)
            self.assertNotIn("-U postgres", calls)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])

    def test_unexplained_failure_replaces_a_stale_success(self) -> None:
        # A run that dies before any caller records a reason must still leave a
        # report saying why — and must not leave the previous run's success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            report.write_text(
                json.dumps({"evidence_eligible": True, "postgres": {"rpo_pass": True}}),
                encoding="utf-8",
            )
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48Z",
                replay_us=_utc_micros("2026-11-16T07:42:47Z"),
                report=report,
                scratch=None,
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("refused: could not stop Postgres", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            # The stale success is gone: this is the current run's report.
            self.assertFalse(written["evidence_eligible"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")
            self.assertTrue(written["blocked_by"])
            self.assertIn("exited with status", written["blocked_by"])
            self.assertFalse(written["evidence_eligible"])

    def test_report_write_failure_fails_a_successful_restore(self) -> None:
        # The restore and its verification succeed, then the report cannot be
        # written. A run that cannot produce evidence must not exit zero.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_dir = root / "report-is-a-directory"
            report_dir.mkdir()
            proc = self._run_restore(
                root,
                target="2026-11-16T07:42:48Z",
                replay_us=_utc_micros("2026-11-16T07:42:47Z"),
                report=report_dir,
            )
            output = proc.stdout + proc.stderr
            self.assertIn("scratch restore ok", output)
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("could not write the PITR report", output)


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
            # Fixed argv, no shell: the only variable is the script path this test owns.
            proc = subprocess.run(  # nosec B603
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
            # Fixed argv, no shell: the only variable is the script path this test owns.
            proc = subprocess.run(  # nosec B603
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
