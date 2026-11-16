#!/usr/bin/env python3
"""Build the 4.P.5 restore-drill JSON report (honest RPO/RTO + outbox pass).

The report is also the producer for the restore-drill Prometheus metrics
(O02): a successful drill writes ``ibex_restore_drill_last_success_unixtime``,
``ibex_restore_drill_duration_seconds`` and ``ibex_restore_drill_rto_pass`` to
the node-exporter textfile directory that ``pgbackrest-backup.sh`` already
writes. A failed drill never advances the last-success timestamp; it preserves
the previous value so a real failure cannot look like a fresh success.

This module is the entry point the shell producers invoke
(``restore-drill.sh`` and ``pitr_report.sh`` both run it by path). It owns the
process — the report file, the metrics textfile and the exit codes — and none
of the report's shape: the producer facts, the blocks and the honesty rules
live in ``restore_drill_report_schema.py`` next to this file.

``__all__`` below is the whole public surface of this module: every public name
defined in this file, plus the schema names it deliberately re-exports for the
tests and the producer. Nothing else from the schema module is re-exported —
import the rest of it from ``restore_drill_report_schema.py`` directly.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# The schema module is a sibling file, not an installed package: the producers
# run this script by path and do not set PYTHONPATH, so the script's own
# directory is added to the import path before the sibling is imported. Ruff
# exempts a module-level import that follows a sys.path modification, so this
# needs no noqa.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The schema names the tests and the producer call through this file, plus
# ``_fixture_rows``, which ``drill_metrics`` uses internally and which stays
# private (hence absent from ``__all__``).
from restore_drill_report_schema import (
    ReportHonestyError,
    _fixture_rows,
    assert_honest,
    build_report,
    outbox_rpo_pass,
    parse_int_or_none,
    postgres_rpo_pass,
    wal_archive_backlog,
)

# Every public name defined here, plus the seven schema names deliberately
# re-exported above. A name that is not in this list is not part of the surface.
__all__ = [
    "DEFAULT_METRICS_FILENAME",
    "DEFAULT_STATE_DIR",
    "ReportHonestyError",
    "assert_honest",
    "build_report",
    "drill_metrics",
    "main",
    "metrics_path_from_env",
    "outbox_rpo_pass",
    "parse_int_or_none",
    "postgres_rpo_pass",
    "read_last_success",
    "render_metrics",
    "wal_archive_backlog",
    "write_metrics",
    "write_report",
]

DEFAULT_STATE_DIR = "/var/lib/ibex/backup"
DEFAULT_METRICS_FILENAME = "ibex_restore_drill_metrics.prom"

# Metric order is fixed so the textfile diff is stable between runs.
_METRIC_ORDER = (
    "ibex_restore_drill_last_success_unixtime",
    "ibex_restore_drill_duration_seconds",
    "ibex_restore_drill_rto_pass",
    "ibex_restore_drill_rto_evidence_pass",
    "ibex_restore_drill_fixture_rows",
)

_METRIC_HELP = {
    "ibex_restore_drill_last_success_unixtime": (
        "Unix time of the last restore drill whose report was evidence-eligible"
    ),
    "ibex_restore_drill_duration_seconds": (
        "Wall-clock duration of the restore drill that wrote this file"
    ),
    # Bandit B105 reads the "_pass" suffix as a password-like literal. These are
    # Prometheus metric names and their help text, not credentials.
    "ibex_restore_drill_rto_pass": (  # nosec B105
        "1 when the measured Postgres RTO met IBEX_RTO_TARGET_SEC, 0 otherwise"
    ),
    "ibex_restore_drill_rto_evidence_pass": (  # nosec B105
        "1 when the RTO passed and the restored fixture was at least the minimum "
        "evidence size, 0 otherwise"
    ),
    "ibex_restore_drill_fixture_rows": (
        "Memory rows seeded for the restore drill's RTO measurement"
    ),
}


def metrics_path_from_env(env: dict[str, str] | None = None) -> Path:
    e = env if env is not None else dict(os.environ)
    explicit = (e.get("IBEX_DRILL_METRICS_PATH") or "").strip()
    if explicit:
        return Path(explicit)
    state_dir = (e.get("IBEX_BACKUP_STATE_DIR") or "").strip() or DEFAULT_STATE_DIR
    return Path(state_dir) / DEFAULT_METRICS_FILENAME


def read_last_success(path: Path) -> int | None:
    """Read the previous last-success value so a failed drill cannot reset it."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    match = re.search(
        r"^ibex_restore_drill_last_success_unixtime\s+(\d+)\s*$",
        text,
        re.MULTILINE,
    )
    return int(match.group(1)) if match else None


def drill_metrics(
    report: dict[str, Any],
    *,
    now: int,
    duration_seconds: int | None,
    previous_last_success: int | None,
) -> dict[str, int]:
    """Compute the Prometheus gauges for one drill report.

    ``last_success`` advances only when the report is evidence-eligible. A run
    that failed keeps the previous success time (or omits the metric when no
    successful drill has ever been recorded), so ``IBEXRestoreDrillMissing``
    keeps firing until a real success happens.
    """
    metrics: dict[str, int] = {}
    if report.get("evidence_eligible"):
        metrics["ibex_restore_drill_last_success_unixtime"] = int(now)
    elif previous_last_success is not None:
        metrics["ibex_restore_drill_last_success_unixtime"] = int(previous_last_success)
    if duration_seconds is not None:
        metrics["ibex_restore_drill_duration_seconds"] = int(duration_seconds)
    postgres = report["postgres"]
    metrics["ibex_restore_drill_rto_pass"] = 1 if postgres.get("rto_pass") else 0
    metrics["ibex_restore_drill_rto_evidence_pass"] = (
        1 if postgres.get("rto_evidence_pass") else 0
    )
    fixture = report.get("fixture") or {}
    rows = _fixture_rows(fixture)
    if rows is not None:
        metrics["ibex_restore_drill_fixture_rows"] = int(rows)
    return metrics


def render_metrics(metrics: dict[str, int]) -> str:
    lines: list[str] = []
    for name in _METRIC_ORDER:
        if name not in metrics:
            continue
        lines.extend(
            (
                f"# HELP {name} {_METRIC_HELP[name]}",
                f"# TYPE {name} gauge",
                f"{name} {int(metrics[name])}",
            )
        )
    # Any future metric not in the fixed order still gets emitted, in name order,
    # so adding one cannot silently drop it from the textfile.
    for name in sorted(set(metrics) - set(_METRIC_ORDER)):
        lines.extend(
            (
                f"# HELP {name} Restore-drill gauge",
                f"# TYPE {name} gauge",
                f"{name} {int(metrics[name])}",
            )
        )
    return "\n".join(lines) + "\n"


def write_metrics(path: Path, metrics: dict[str, int]) -> None:
    """Write the textfile atomically: node-exporter must never read a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_metrics(metrics)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write the report atomically, and fail loudly when it cannot be written.

    The file is replaced through a temporary sibling so a reader never sees a
    partial document, and a previous run's report cannot survive as if it
    described this one. An OSError is turned into a named error and a non-zero
    exit: a run that cannot produce evidence must not look like one that did.
    """
    text = json.dumps(report, indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    except OSError as error:
        print(f"ERROR: could not write the report to {path}: {error}", flush=True)
        raise SystemExit(1) from error


def _require_tenant_isolation(report: dict[str, Any], *, allow_no_db: bool, path: Path) -> None:
    if report["tenant_isolation_post_restore"]:
        return
    if report.get("drill_kind") == "pitr":
        # A point-in-time rehearsal restores into a scratch volume and never
        # proves tenant isolation; the report keeps that field false and claims
        # nothing about it. The drill is where isolation is proven.
        return
    if report["postgres"].get("mechanism") == "unavailable":
        # Nothing was restored, so there is no restored data to isolate.
        return
    if allow_no_db:
        print(
            "WARNING: tenant isolation not proven (ALLOW_NO_DB=1; no Postgres)",
            flush=True,
        )
        report["residual"] = "tenant_isolation_unproven_no_postgres"
        write_report(path, report)
        return
    raise SystemExit("tenant isolation check failed")


def _warn_if_false(ok: bool, message: str) -> None:
    if not ok:
        print(message, flush=True)


def _emit_metric_warnings(report: dict[str, Any]) -> None:
    pg = report["postgres"]
    if pg["rpo_measured_sec"] is not None:
        _warn_if_false(
            pg["rpo_pass"],
            "WARNING: postgres RPO not claimed (mechanism/target) — see residuals",
        )
    if pg["rto_measured_sec"] is not None:
        _warn_if_false(pg["rto_pass"], "WARNING: postgres RTO miss vs targets — investigate residual")
        _warn_if_false(
            pg["rto_evidence_pass"],
            "WARNING: postgres RTO evidence not claimed (fixture below the evidence floor)",
        )
    _warn_if_false(
        report["outbox"]["rpo_pass"],
        "WARNING: outbox rpo_pass false (pending!=0 or outbox unreadable)",
    )


def _write_drill_metrics(report: dict[str, Any]) -> Path | None:
    if os.environ.get("IBEX_DRILL_METRICS_DISABLED") == "1":
        return None
    path = metrics_path_from_env()
    metrics = drill_metrics(
        report,
        now=int(time.time()),
        duration_seconds=parse_int_or_none(os.environ.get("DRILL_DURATION_SEC")),
        previous_last_success=read_last_success(path),
    )
    try:
        write_metrics(path, metrics)
    except OSError as error:
        print(f"ERROR: could not write drill metrics to {path}: {error}", flush=True)
        raise SystemExit(1) from error
    print(f"drill metrics written to {path}", flush=True)
    return path


def main() -> None:
    report = build_report()
    path = Path(os.environ["REPORT"])
    write_report(path, report)
    print(json.dumps(report, indent=2))
    allow_no_db = os.environ.get("ALLOW_NO_DB") == "1"
    _require_tenant_isolation(report, allow_no_db=allow_no_db, path=path)
    if report["tenant_isolation_post_restore"] or allow_no_db:
        _emit_metric_warnings(report)
    _write_drill_metrics(report)


if __name__ == "__main__":
    main()
