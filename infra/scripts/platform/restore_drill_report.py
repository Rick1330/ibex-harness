#!/usr/bin/env python3
"""Build the 4.P.5 restore-drill JSON report (honest RPO/RTO + outbox pass).

The report is also the producer for the restore-drill Prometheus metrics
(O02): a successful drill writes ``ibex_restore_drill_last_success_unixtime``,
``ibex_restore_drill_duration_seconds`` and ``ibex_restore_drill_rto_pass`` to
the node-exporter textfile directory that ``pgbackrest-backup.sh`` already
writes. A failed drill never advances the last-success timestamp; it preserves
the previous value so a real failure cannot look like a fresh success.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = "/var/lib/ibex/backup"
DEFAULT_METRICS_FILENAME = "ibex_restore_drill_metrics.prom"
DEFAULT_MIN_FIXTURE_ROWS = 1000

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
    "ibex_restore_drill_rto_pass": (
        "1 when the measured Postgres RTO met IBEX_RTO_TARGET_SEC, 0 otherwise"
    ),
    "ibex_restore_drill_rto_evidence_pass": (
        "1 when the RTO passed and the restored fixture was at least the minimum "
        "evidence size, 0 otherwise"
    ),
    "ibex_restore_drill_fixture_rows": (
        "Memory rows seeded for the restore drill's RTO measurement"
    ),
}


def parse_int_or_none(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    return int(raw)


def le_pass(measured: int | None, target: int) -> bool:
    if measured is None:
        return False
    return measured <= target


def outbox_rpo_pass(*, pending: int | None, max_aggregate_seq: int | None, target: int = 0) -> bool:
    """Outbox RPO target is 0: pass only when pending is known and == target.

    max_aggregate_seq must be readable (non-null) so we know the query worked.
    A nonzero pending count means unreplicated outbox work — fail closed.
    """
    if pending is None or max_aggregate_seq is None:
        return False
    return pending == target


def postgres_rpo_pass(ctx: dict[str, Any]) -> bool:
    """pg_dump_fallback is not PITR — never claim RPO pass for that mechanism.

    Expected keys: mechanism, backup_ok, restore_ok, measured, target.
    """
    if ctx.get("mechanism") != "pgbackrest_wal":
        return False
    measured = ctx.get("measured")
    measured_sec = measured if isinstance(measured, int) else None
    return (
        bool(ctx.get("backup_ok"))
        and bool(ctx.get("restore_ok"))
        and le_pass(measured_sec, int(ctx["target"]))
    )


def mechanism_note(mechanism: str) -> str:
    if mechanism == "pg_dump_fallback":
        return (
            "pg_dump fallback is not PITR; wall-clock backup duration is recorded but "
            "rpo_pass stays false. Real ≤5m RPO requires pgBackRest+WAL (#869)."
        )
    if mechanism == "pgbackrest_wal":
        return "pgBackRest+WAL path"
    return "backup/restore not completed"


def _fixture_block(e: dict[str, str]) -> dict[str, Any]:
    """Record how much data the RTO was measured on (O03).

    A restore of two rows finishes in about a second, so an RTO reported without
    its fixture size is not evidence for a real database. Both the seeded and
    the post-restore row counts are kept; ``rto_evidence_pass`` uses the
    post-restore count when present and requires it to clear the configured
    floor.
    """
    min_rows = parse_int_or_none(e.get("DRILL_MIN_FIXTURE_ROWS", ""))
    return {
        "rows": parse_int_or_none(e.get("FIXTURE_ROWS", "")),
        "orgs": parse_int_or_none(e.get("FIXTURE_ORGS", "")),
        "rows_verified": parse_int_or_none(e.get("FIXTURE_ROWS_ACTUAL", "")),
        "rows_restored": parse_int_or_none(e.get("FIXTURE_ROWS_RESTORED", "")),
        "min_rows_for_rto_evidence": (
            min_rows if min_rows is not None else DEFAULT_MIN_FIXTURE_ROWS
        ),
    }


def _fixture_rows(fixture: dict[str, Any]) -> int | None:
    """Rows the RTO was measured on: an observed count, never the requested one.

    ``rows`` is what the script was asked to seed. Only ``rows_verified`` (after
    the seed) and ``rows_restored`` (after the restore) prove that data existed.
    An ALLOW_NO_DB smoke seeds nothing, so both are absent and the evidence
    claim fails closed instead of falling back to the requested number.
    """
    restored = fixture.get("rows_restored")
    if isinstance(restored, int):
        return restored
    verified = fixture.get("rows_verified")
    if isinstance(verified, int):
        return verified
    return None


def rto_evidence_pass(*, rto_pass: bool, fixture: dict[str, Any]) -> bool:
    """RTO evidence needs both a target pass and a fixture above the floor."""
    rows = _fixture_rows(fixture)
    floor = fixture.get("min_rows_for_rto_evidence")
    if not isinstance(floor, int):
        floor = DEFAULT_MIN_FIXTURE_ROWS
    return bool(rto_pass) and rows is not None and rows >= floor


def _postgres_block(e: dict[str, str], *, mechanism: str, note: str) -> dict[str, Any]:
    pg_rpo = parse_int_or_none(e.get("PG_RPO_MEASURED", ""))
    pg_rto = parse_int_or_none(e.get("PG_RTO_MEASURED", ""))
    backup_ok = e.get("PG_BACKUP_OK") == "true"
    restore_ok = e.get("PG_RESTORE_OK") == "true"
    return {
        "rpo_target_sec": int(e["PG_RPO_SEC"]),
        "rto_target_sec": int(e["PG_RTO_SEC"]),
        "rpo_measured_sec": pg_rpo,
        "rto_measured_sec": pg_rto,
        "backup_ok": backup_ok,
        "restore_ok": restore_ok,
        "rpo_pass": postgres_rpo_pass(
            {
                "backup_ok": backup_ok,
                "restore_ok": restore_ok,
                "measured": pg_rpo,
                "target": int(e["PG_RPO_SEC"]),
                "mechanism": mechanism,
            }
        ),
        "rto_pass": restore_ok and le_pass(pg_rto, int(e["PG_RTO_SEC"])),
        "mechanism": mechanism,
        "note": note,
    }


def _outbox_block(e: dict[str, str]) -> dict[str, Any]:
    outbox_seq = parse_int_or_none(e.get("OUTBOX_SEQ", ""))
    outbox_pending = parse_int_or_none(e.get("OUTBOX_PENDING", ""))
    return {
        "rpo_target": 0,
        "max_aggregate_seq": outbox_seq,
        "pending": outbox_pending,
        "rpo_pass": outbox_rpo_pass(
            pending=outbox_pending,
            max_aggregate_seq=outbox_seq,
            target=0,
        ),
    }


def build_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    e = env if env is not None else dict(os.environ)
    mechanism = e.get("PG_MECHANISM", "unmeasured")
    note = mechanism_note(mechanism)
    backup_ok = e.get("PG_BACKUP_OK") == "true"
    restore_ok = e.get("PG_RESTORE_OK") == "true"
    allow_no_db = e.get("ALLOW_NO_DB") == "1"
    iso_ok = e.get("ISO_OK") == "true"
    kyverno_ok = e.get("KYVERNO_OK") == "true"

    report: dict[str, Any] = {
        "milestone": "4.P.5",
        "transcript": e.get("TRANSCRIPT"),
        "evidence_eligible": (not allow_no_db) and iso_ok and backup_ok and restore_ok,
        "allow_no_db": allow_no_db,
        "postgres": _postgres_block(e, mechanism=mechanism, note=note),
        "clickhouse": {
            "rpo_target_sec": int(e["CH_RPO_SEC"]),
            "rto_target_sec": int(e["CH_RTO_SEC"]),
            "rpo_measured_sec": parse_int_or_none(e.get("CH_RPO_MEASURED", "")),
            "rto_measured_sec": parse_int_or_none(e.get("CH_RTO_MEASURED", "")),
            "reachable": e.get("CH_REACHABLE") == "true",
            "note": "reachability timing only when measured; unmeasured fields are null",
        },
        "redis": {
            "backup": False,
            "note": "intentional — cache/ephemeral (locked decision)",
        },
        "object_minio": {
            "rpo_target_sec": int(e["OBJ_RPO_SEC"]),
            "rto_target_sec": int(e["OBJ_RTO_SEC"]),
            "rpo_measured_sec": parse_int_or_none(e.get("OBJ_RPO_MEASURED", "")),
            "rto_measured_sec": parse_int_or_none(e.get("OBJ_RTO_MEASURED", "")),
        },
        "outbox": _outbox_block(e),
        "tenant_isolation_post_restore": iso_ok,
        "helm_lint_template": e.get("KIND_OK") == "true",
        "kyverno_policy_applied": kyverno_ok,
        "kyverno_residual": None if kyverno_ok else "#869",
    }
    fixture = _fixture_block(e)
    report["fixture"] = fixture
    report["postgres"]["rto_evidence_pass"] = rto_evidence_pass(
        rto_pass=bool(report["postgres"]["rto_pass"]),
        fixture=fixture,
    )
    if allow_no_db:
        report["residual"] = "not_evidence_allow_no_db"
        report["evidence_eligible"] = False
    elif mechanism == "pg_dump_fallback":
        report["postgres_rpo_residual"] = "not_pitr_pg_dump_fallback_#869"
    return report


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


def _require_tenant_isolation(report: dict[str, Any], *, allow_no_db: bool, path: Path) -> None:
    if report["tenant_isolation_post_restore"]:
        return
    if allow_no_db:
        print(
            "WARNING: tenant isolation not proven (ALLOW_NO_DB=1; no Postgres)",
            flush=True,
        )
        report["residual"] = "tenant_isolation_unproven_no_postgres"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
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
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    allow_no_db = os.environ.get("ALLOW_NO_DB") == "1"
    _require_tenant_isolation(report, allow_no_db=allow_no_db, path=path)
    if report["tenant_isolation_post_restore"] or allow_no_db:
        _emit_metric_warnings(report)
    _write_drill_metrics(report)


if __name__ == "__main__":
    main()
