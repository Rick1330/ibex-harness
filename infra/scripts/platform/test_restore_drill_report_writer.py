#!/usr/bin/env python3
"""Report-writer cases: the report file, the metrics textfile, and their readers.

A run that cannot write its evidence must not look like one that did. These
cases drive the writer against a real temporary directory, so the atomic
replace, the loud failure, and the metrics round trip are the shipped ones.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess  # nosec B404 - the wrapper test runs the shipped function; argv is fixed
import tempfile
import time
import unittest
from pathlib import Path

from restore_drill_test_support import DEV_TOOL_SH, base_env, mod


class ReportWriterTests(unittest.TestCase):
    """A run that cannot write its evidence must not look like one that did."""

    def test_write_report_replaces_atomically_and_leaves_no_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pitr-report.json"
            path.write_text('{"stale": true}\n', encoding="utf-8")
            mod.write_report(path, {"fresh": True})
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
            with (
                contextlib.redirect_stdout(io.StringIO()) as printed,
                self.assertRaises(SystemExit) as raised,
            ):
                mod.write_report(path, {"fresh": True})
            self.assertNotEqual(raised.exception.code, 0)
            self.assertIn("could not write the report", printed.getvalue())

    def test_main_exits_non_zero_when_the_report_cannot_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("", encoding="utf-8")
            env = base_env(REPORT=str(blocker / "pitr-report.json"), ALLOW_NO_DB="1")
            saved = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    mod.main()
            finally:
                os.environ.clear()
                os.environ.update(saved)
            self.assertNotEqual(raised.exception.code, 0)


# A stand-in for `pgbackrest-restore.sh` inside a throwaway ROOT_DIR: it either
# writes the report the wrapper looks for, or leaves the path empty. The wrapper
# under test is the shipped `v1_pitr`, not a copy of it.
_STUB_RESTORE = """#!/usr/bin/env bash
{write}
exit {status}
"""

_WRITE_REPORT = 'printf \'{{"drill_started_at": "%s"}}\n\' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$PGBACKREST_RESTORE_REPORT"'


def pitr_wrapper(root: Path, *, writes: bool, status: int) -> dict[str, str]:
    """Build a ROOT_DIR the shipped v1_pitr can run against, and its environment."""
    conf = root / "infra" / "backup" / "pgbackrest" / "pgbackrest.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[global]\nrepo1-type=s3\n", encoding="utf-8")
    (conf.parent / "pgbackrest.conf.example").write_text("[global]\n", encoding="utf-8")
    lib = root / "infra" / "scripts" / "lib"
    lib.mkdir(parents=True)
    (lib / "dotenv.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    restore = root / "infra" / "scripts" / "platform" / "pgbackrest-restore.sh"
    restore.parent.mkdir(parents=True)
    write = _WRITE_REPORT if writes else ":"
    restore.write_text(
        _STUB_RESTORE.format(write=write, status=status), encoding="utf-8"
    )
    env_file = root / "profile.env"
    env_file.write_text("", encoding="utf-8")
    env = {**os.environ, "V1_ENV": str(env_file), "IBEX_CONTAINER_CLI": "true"}
    env.pop("IBEX_PITR_REPORT", None)
    return env


def run_v1_pitr(root: Path, env: dict[str, str], report: Path, target: str) -> subprocess.CompletedProcess:
    """Source the shipped wrapper, point it at ``root``, and run one v1_pitr."""
    script = 'source "$1" help >/dev/null; ROOT_DIR="$2"; IBEX_PITR_REPORT="$3"; v1_pitr "$4"'
    return subprocess.run(  # nosec B603 - fixed argv, no shell interpolation
        [
            "/bin/bash",
            "-c",
            script,
            "v1_pitr",
            str(DEV_TOOL_SH),
            str(root),
            str(report),
            target,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


class PitrReportIdentityTests(unittest.TestCase):
    """The wrapper prints a report path only for the report this run wrote."""

    _TARGET = "2026-11-16T07:42:48Z"

    def test_a_stale_report_in_the_same_second_is_not_reported_as_written(self) -> None:
        # The defect: mtime and the run's start are both whole seconds, so an
        # earlier report left in place satisfied the check when the retry started
        # in the same second, and its path was printed as this run's report.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            report.write_text('{"evidence_eligible": true}\n', encoding="utf-8")
            # A timestamp at or after this run's start is the ambiguity the
            # wrapper used to read as "this run wrote it". One second ahead makes
            # the old check deterministic instead of a race on the clock tick.
            ahead = time.time() + 1
            os.utime(report, (ahead, ahead))
            proc = run_v1_pitr(
                root, pitr_wrapper(root, writes=False, status=1), report, self._TARGET
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn(f"pitr report=NOT WRITTEN ({report})", output)
            self.assertNotIn(f"pitr report={report}", output)
            # The previous report is kept, under a name that cannot be mistaken
            # for this run's evidence.
            self.assertFalse(report.exists())
            self.assertTrue((root / "pitr-report.json.previous").exists())

    def test_a_report_this_run_wrote_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_v1_pitr(
                root, pitr_wrapper(root, writes=True, status=0), report, self._TARGET
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn(f"pitr report={report}", output)
            self.assertTrue(report.exists())


class DrillMetricsTests(unittest.TestCase):
    def test_success_advances_last_success_and_reports_rto(self) -> None:
        report = mod.build_report(base_env())
        metrics = mod.drill_metrics(
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
        report = mod.build_report(base_env(PG_RESTORE_OK="false"))
        metrics = mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=1,
            previous_last_success=1_690_000_000,
        )
        self.assertEqual(metrics["ibex_restore_drill_last_success_unixtime"], 1_690_000_000)
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 0)

    def test_no_previous_success_omits_metric(self) -> None:
        report = mod.build_report(base_env(PG_RESTORE_OK="false"))
        metrics = mod.drill_metrics(
            report,
            now=1_700_000_000,
            duration_seconds=None,
            previous_last_success=None,
        )
        self.assertNotIn("ibex_restore_drill_last_success_unixtime", metrics)
        self.assertNotIn("ibex_restore_drill_duration_seconds", metrics)
        self.assertEqual(metrics["ibex_restore_drill_rto_pass"], 0)

    def test_small_fixture_sets_rto_evidence_zero(self) -> None:
        report = mod.build_report(
            base_env(FIXTURE_ROWS="2", FIXTURE_ROWS_ACTUAL="2", FIXTURE_ROWS_RESTORED="2")
        )
        metrics = mod.drill_metrics(
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
            mod.write_metrics(path, metrics)
            text = path.read_text(encoding="utf-8")
            self.assertIn("# TYPE ibex_restore_drill_last_success_unixtime gauge", text)
            self.assertIn("ibex_restore_drill_last_success_unixtime 1700000000", text)
            self.assertIn("ibex_restore_drill_rto_pass 1", text)
            self.assertEqual(mod.read_last_success(path), 1_700_000_000)

    def test_read_last_success_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.prom"
            self.assertIsNone(mod.read_last_success(path))


if __name__ == "__main__":
    unittest.main()
