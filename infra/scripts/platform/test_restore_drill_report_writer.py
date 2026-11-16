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
import tempfile
import unittest
from pathlib import Path

from restore_drill_test_support import base_env, mod


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
