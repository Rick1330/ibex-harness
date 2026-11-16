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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = "/var/lib/ibex/backup"
DEFAULT_METRICS_FILENAME = "ibex_restore_drill_metrics.prom"
DEFAULT_MIN_FIXTURE_ROWS = 1000

# Locked targets (decision 4). A producer that does not set the variable gets the
# locked value, so the drill and the PITR report cannot grade against different
# numbers.
DEFAULT_TARGETS = {
    "PG_RPO_SEC": 300,
    "PG_RTO_SEC": 1800,
    "CH_RPO_SEC": 86400,
    "CH_RTO_SEC": 3600,
    "OBJ_RPO_SEC": 86400,
    "OBJ_RTO_SEC": 3600,
}


class ReportHonestyError(ValueError):
    """Raised when a report would claim more than the run actually proved."""


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


def parse_int_or_none(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    return int(raw)


def le_pass(measured: int | None, target: int) -> bool:
    if measured is None:
        return False
    return measured <= target


def target_sec(e: dict[str, str], key: str) -> int:
    """Read a locked target, falling back to the locked default."""
    raw = (e.get(key) or "").strip()
    if raw == "":
        return DEFAULT_TARGETS[key]
    return int(raw)


def parse_bool_or_none(raw: str | None) -> bool | None:
    """Three-state boolean: unset means "not measured", never "false"."""
    value = (raw or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


# A WAL segment file name is 24 hex digits: timeline, log, segment. The archive
# is "drained" when the newest archived segment is the one being written or the
# one before it, because then nothing older is still waiting to be pushed.
_WAL_SEGMENT_RE = re.compile(r"^[0-9A-Fa-f]{24}$")
_WAL_SEGMENTS_PER_LOG = 256


def _wal_segment_position(name: str | None) -> tuple[int, int, int] | None:
    """Split a WAL segment file name into (timeline, log, segment)."""
    value = (name or "").strip()
    if not _WAL_SEGMENT_RE.match(value):
        return None
    return (int(value[0:8], 16), int(value[8:16], 16), int(value[16:24], 16))


def wal_archive_backlog(
    *,
    last_archived_wal: str | None,
    current_wal: str | None,
    last_failed_after_archive: bool | None,
) -> bool | None:
    """Is the WAL archive queue provably drained?

    ``last_archived_time`` records when an upload *completed*, not the
    transaction time the segment it carried covers. While a backlog drains, an
    old segment uploads now and its age looks like a fresh recovery point, so an
    RPO read from it can understate the real lag by the whole length of the
    backlog.

    The queue state is what turns the upload age into a bound. When the newest
    archived segment is the one being written, or the one before it, nothing
    older is still queued, so the newest recoverable transaction is at least as
    recent as that upload: ``now - last_archived_time`` is then an upper bound on
    the RPO, and passing it does not overstate. A failed push after the last
    success means the queue is not draining, however fresh the last upload was.

    ``None`` means "cannot tell", and must never be read as "no backlog".
    """
    last = _wal_segment_position(last_archived_wal)
    current = _wal_segment_position(current_wal)
    if last is None or current is None or last_failed_after_archive is None:
        return None
    last_timeline, last_log, last_seg = last
    current_timeline, current_log, current_seg = current
    if last_timeline != current_timeline:
        # Segments on different timelines cannot be compared; a promotion is
        # exactly when the archive can lag, so fail closed.
        return True
    gap = (current_log - last_log) * _WAL_SEGMENTS_PER_LOG + (current_seg - last_seg)
    if gap > 1:
        return True
    return bool(last_failed_after_archive)


def optional_text(raw: str | None) -> str | None:
    """Trimmed text, or None when the producer left the variable unset.

    A blank variable and an absent one mean the same thing to a reader of the
    report: nothing was recorded. Collapsing both to None keeps that visible
    instead of writing ``""``, which reads like a measured empty value.
    """
    return (raw or "").strip() or None


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

    A measured age is only an upper bound on the RPO while the archive queue is
    drained, so ``backlog`` must be exactly ``False``: ``None`` (unproven) is
    refused for the same reason as ``True``.

    Expected keys: mechanism, backup_ok, restore_ok, measured, target, backlog.
    """
    if ctx.get("mechanism") != "pgbackrest_wal":
        return False
    if ctx.get("backlog") is not False:
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
    if mechanism == "unavailable":
        return (
            "pgBackRest+WAL is unavailable in this environment (see blocked_by). "
            "No restore was attempted and no RPO is claimed."
        )
    return "backup/restore not completed"


def _fixture_block(e: dict[str, str]) -> dict[str, Any]:
    """Record how much data the RTO was measured on (O03).

    A restore of two rows finishes in about a second, so an RTO reported without
    its fixture size is not evidence for a real database. The requested, the
    post-seed and the post-restore row counts are all recorded; only the
    post-restore count can satisfy ``rto_evidence_pass``, which also requires it
    to clear the configured floor.
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


def _restored_rows(fixture: dict[str, Any]) -> int | None:
    """Rows counted in the database *after* the restore: the only evidence count.

    ``rows`` is what the script was asked to seed and ``rows_verified`` is a
    pre-backup count. Neither proves that the restored database contained the
    data, so neither can stand in for an observed post-restore count: a drill
    that seeds 50k rows, backs up, and restores an empty volume would otherwise
    report evidence for a fixture it no longer had. A missing or non-integer
    value fails closed.
    """
    restored = fixture.get("rows_restored")
    return restored if isinstance(restored, int) else None


def _fixture_rows(fixture: dict[str, Any]) -> int | None:
    """Best observed row count, for the reporting gauge only (never evidence).

    The gauge may fall back to the post-seed count so an operator still sees how
    much data the drill ran with; ``rto_evidence_pass`` does not, because only
    the post-restore count proves the data survived the restore.
    """
    restored = _restored_rows(fixture)
    if restored is not None:
        return restored
    verified = fixture.get("rows_verified")
    return verified if isinstance(verified, int) else None


def rto_evidence_pass(*, rto_pass: bool, fixture: dict[str, Any]) -> bool:
    """RTO evidence needs both a target pass and an observed restored fixture.

    ``rto_pass`` alone grades a stopwatch: the floor is what makes the number
    mean something, and it is measured against the post-restore count only.
    """
    rows = _restored_rows(fixture)
    floor = fixture.get("min_rows_for_rto_evidence")
    if not isinstance(floor, int):
        floor = DEFAULT_MIN_FIXTURE_ROWS
    return bool(rto_pass) and rows is not None and rows >= floor


def _restored_row_counts(e: dict[str, str]) -> dict[str, int | None]:
    """Row counts read back from the restored cluster (null when unreadable)."""
    return {
        "organizations": parse_int_or_none(e.get("RESTORED_ORGS", "")),
        "memories": parse_int_or_none(e.get("RESTORED_MEMORIES", "")),
    }


def _wal_archive_facts(e: dict[str, str]) -> dict[str, Any]:
    """What the producer observed about the archive, and what it proves.

    The upload age is a diagnostic on its own: it is not an RPO until the queue
    is drained, so it is recorded separately from the claim it can support.
    """
    return {
        "wal_archive_ok": e.get("WAL_ARCHIVE_OK") == "true",
        "wal_archive_upload_age_sec": parse_int_or_none(
            e.get("WAL_ARCHIVE_UPLOAD_AGE_SEC", "")
        ),
        "wal_archive_backlog": wal_archive_backlog(
            last_archived_wal=e.get("WAL_ARCHIVE_LAST_SEGMENT"),
            current_wal=e.get("WAL_ARCHIVE_CURRENT_SEGMENT"),
            last_failed_after_archive=parse_bool_or_none(
                e.get("WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE")
            ),
        ),
    }


def _postgres_block(e: dict[str, str], *, facts: RunFacts, note: str) -> dict[str, Any]:
    pg_rpo = parse_int_or_none(e.get("PG_RPO_MEASURED", ""))
    pg_rto = parse_int_or_none(e.get("PG_RTO_MEASURED", ""))
    if facts.mechanism == "unavailable":
        # Nothing was restored. A report that says so must not also carry the
        # booleans of a run that happened.
        backup_ok = False
        restore_ok = False
    else:
        backup_ok = facts.backup_ok
        restore_ok = facts.restore_ok
    rpo_target = target_sec(e, "PG_RPO_SEC")
    rto_target = target_sec(e, "PG_RTO_SEC")
    archive = _wal_archive_facts(e)
    # Upload recency is an RPO only while the archive queue is drained; an
    # undrained or unproven queue leaves the measured RPO null so the field
    # cannot be quoted as a bound it never was. The observation stays visible in
    # wal_archive_upload_age_sec.
    if not archive["wal_archive_ok"] or archive["wal_archive_backlog"] is not False:
        pg_rpo = None
    rpo_pass = postgres_rpo_pass(
        {
            "backup_ok": backup_ok,
            "restore_ok": restore_ok,
            "measured": pg_rpo,
            "target": rpo_target,
            "mechanism": facts.mechanism,
            "backlog": archive["wal_archive_backlog"],
        }
    )
    # A requested recovery target that was missed, or whose result was never
    # recorded, means the restore did not prove it landed where it claimed to;
    # that run cannot carry an RPO pass either. "Not measured" is not the same
    # as "not missed": only an affirmative result clears the gate.
    if facts.target_requested and facts.target_reached is not True:
        rpo_pass = False
    return {
        "rpo_target_sec": rpo_target,
        "rto_target_sec": rto_target,
        "rpo_measured_sec": pg_rpo,
        "rto_measured_sec": pg_rto,
        "backup_ok": backup_ok,
        "restore_ok": restore_ok,
        "rpo_pass": rpo_pass,
        "rto_pass": restore_ok and le_pass(pg_rto, rto_target),
        "mechanism": facts.mechanism,
        **archive,
        "target_timestamp": optional_text(e.get("TARGET_TIMESTAMP")),
        "recovery_target_reached": facts.target_reached,
        "recovery_replay_timestamp": optional_text(e.get("RECOVERY_REPLAY_TIMESTAMP")),
        "cluster_data_bytes": parse_int_or_none(e.get("CLUSTER_DATA_BYTES", "")),
        "restored_row_counts": _restored_row_counts(e),
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


@dataclass(frozen=True)
class RunFacts:
    """The producer facts one report grades, read from the environment once.

    Bundled rather than passed as seven positional arguments so a caller cannot
    pair the mechanism of one run with the restore result of another, and so the
    eligibility rule stays a one-argument predicate.
    """

    drill_kind: str
    mechanism: str
    backup_ok: bool
    restore_ok: bool
    iso_ok: bool
    target_requested: bool
    target_reached: bool | None
    allow_no_db: bool


def read_run_facts(e: dict[str, str]) -> RunFacts:
    """Read every producer fact the report grades from one environment."""
    return RunFacts(
        drill_kind=(e.get("DRILL_KIND") or "restore-drill").strip(),
        mechanism=e.get("PG_MECHANISM", "unmeasured"),
        backup_ok=e.get("PG_BACKUP_OK") == "true",
        restore_ok=e.get("PG_RESTORE_OK") == "true",
        iso_ok=e.get("ISO_OK") == "true",
        target_requested=optional_text(e.get("TARGET_TIMESTAMP")) is not None,
        target_reached=parse_bool_or_none(e.get("RECOVERY_TARGET_REACHED")),
        allow_no_db=e.get("ALLOW_NO_DB") == "1",
    )


def _evidence_eligible(facts: RunFacts) -> bool:
    """What makes a report usable as evidence, per producer.

    The drill proves the backup is restorable *and* that tenant isolation
    survives the restore, so it needs the isolation result. A point-in-time
    rehearsal restores into a scratch volume and never touches tenant data, so
    it needs the target to have been reached instead. Neither can be eligible
    when the mechanism was unavailable or the run is an ALLOW_NO_DB smoke.
    """
    if facts.allow_no_db or facts.mechanism == "unavailable":
        return False
    if not (facts.backup_ok and facts.restore_ok):
        return False
    if facts.drill_kind == "pitr":
        # A rehearsal that asked for a target is evidence only when the restored
        # cluster proved it stopped there. An unrecorded result (``None``) is a
        # target nobody checked, not a target that was met.
        return facts.mechanism == "pgbackrest_wal" and (
            not facts.target_requested or facts.target_reached is True
        )
    return facts.iso_ok


def _require_blocked_by(report: dict[str, Any]) -> None:
    """An ``unavailable`` run must name what blocked it."""
    if not (report.get("blocked_by") or "").strip():
        raise ReportHonestyError(
            "mechanism 'unavailable' requires a non-empty blocked_by"
        )


def _require_unavailable_claims_no_pass(postgres: dict[str, Any]) -> None:
    """A run that restored nothing cannot carry an RPO or RTO pass."""
    if postgres.get("rpo_pass") or postgres.get("rto_pass"):
        raise ReportHonestyError("an unavailable run cannot claim rpo_pass/rto_pass")


def _require_unavailable_is_not_evidence(report: dict[str, Any]) -> None:
    """A run that restored nothing cannot be cited as evidence."""
    if report.get("evidence_eligible"):
        raise ReportHonestyError("an unavailable run cannot be evidence_eligible")


def _require_pitr_mechanism(mechanism: str | None) -> None:
    """``rpo_pass`` is a PITR claim: a dump or an unmeasured run cannot make it."""
    if mechanism != "pgbackrest_wal":
        raise ReportHonestyError(
            f"rpo_pass requires mechanism pgbackrest_wal, got {mechanism!r}"
        )


def _require_measured_rpo(postgres: dict[str, Any]) -> None:
    """Archiving being on is not an RPO: the gap has to have been measured."""
    if postgres.get("rpo_measured_sec") is None:
        raise ReportHonestyError("rpo_pass requires a measured RPO")


def _require_reached_target(postgres: dict[str, Any]) -> None:
    """A restore that missed — or never proved — the target cannot pass.

    Only an affirmative result clears this gate. A report whose target was
    requested but whose ``recovery_target_reached`` is null or absent is a target
    nobody checked, and reading that as "not missed" is how a targeted restore
    with an unproven target used to report success.
    """
    if postgres.get("target_timestamp") and postgres.get("recovery_target_reached") is not True:
        raise ReportHonestyError(
            "rpo_pass cannot be claimed without an affirmative recovery-target result"
        )


def _require_drained_archive(postgres: dict[str, Any]) -> None:
    """An RPO read from an undrained archive is not an upper bound on the lag."""
    if postgres.get("wal_archive_backlog") is not False:
        raise ReportHonestyError(
            "rpo_pass requires a provably drained WAL archive "
            "(wal_archive_backlog=false)"
        )


def _require_rpo_within_target(postgres: dict[str, Any]) -> None:
    """A measured RPO above the target is a miss, not a pass."""
    measured = postgres.get("rpo_measured_sec")
    target = postgres.get("rpo_target_sec")
    if isinstance(measured, int) and isinstance(target, int) and measured > target:
        raise ReportHonestyError(
            f"rpo_pass cannot be claimed with a measured RPO of {measured}s "
            f"above the {target}s target"
        )


def assert_honest(report: dict[str, Any]) -> dict[str, Any]:
    """Refuse a report whose claims exceed what the run proved.

    Every rule here exists because a report is the only artefact an operator can
    read at 03:00: a fallback or unavailable run that carried ``rpo_pass: true``,
    or an ``unavailable`` run with no reason, would be worse than no report.

    Each invariant is one named check below. They are grouped by the claim they
    defend, and a check only runs when that claim was made, so a report that
    claims nothing is accepted without walking every rule.
    """
    postgres = report["postgres"]
    mechanism = postgres.get("mechanism")
    if mechanism == "unavailable":
        _require_blocked_by(report)
        _require_unavailable_claims_no_pass(postgres)
        _require_unavailable_is_not_evidence(report)
    if postgres.get("rpo_pass"):
        _require_pitr_mechanism(mechanism)
        _require_measured_rpo(postgres)
        _require_reached_target(postgres)
        _require_drained_archive(postgres)
        _require_rpo_within_target(postgres)
    return report


def _metadata_block(e: dict[str, str], facts: RunFacts) -> dict[str, Any]:
    """Header: which run this is, and what makes it citable as evidence."""
    return {
        "milestone": "4.P.5",
        "drill_kind": facts.drill_kind,
        "drill_started_at": optional_text(e.get("DRILL_STARTED_AT")),
        "environment_class": optional_text(e.get("ENVIRONMENT_CLASS")),
        "transcript": e.get("TRANSCRIPT") or None,
        "evidence_eligible": _evidence_eligible(facts),
        "allow_no_db": facts.allow_no_db,
        "blocked_by": optional_text(e.get("BLOCKED_BY")),
    }


def _store_blocks(e: dict[str, str]) -> dict[str, Any]:
    """ClickHouse, Redis and object-store blocks: no restore claim is made."""
    return {
        "clickhouse": {
            "rpo_target_sec": target_sec(e, "CH_RPO_SEC"),
            "rto_target_sec": target_sec(e, "CH_RTO_SEC"),
            "rpo_measured_sec": parse_int_or_none(e.get("CH_RPO_MEASURED", "")),
            "rto_measured_sec": parse_int_or_none(e.get("CH_RTO_MEASURED", "")),
            "reachable": e.get("CH_REACHABLE") == "true",
            "note": (
                "reachability timing only when measured; unmeasured fields are null"
            ),
        },
        "redis": {
            "backup": False,
            "note": "intentional — cache/ephemeral (locked decision)",
        },
        "object_minio": {
            "rpo_target_sec": target_sec(e, "OBJ_RPO_SEC"),
            "rto_target_sec": target_sec(e, "OBJ_RTO_SEC"),
            "rpo_measured_sec": parse_int_or_none(e.get("OBJ_RPO_MEASURED", "")),
            "rto_measured_sec": parse_int_or_none(e.get("OBJ_RTO_MEASURED", "")),
        },
    }


def _platform_block(e: dict[str, str], facts: RunFacts) -> dict[str, Any]:
    """Isolation after restore, Helm render and Kyverno policy application."""
    kyverno_ok = e.get("KYVERNO_OK") == "true"
    return {
        "tenant_isolation_post_restore": facts.iso_ok,
        "helm_lint_template": e.get("KIND_OK") == "true",
        "kyverno_policy_applied": kyverno_ok,
        "kyverno_residual": None if kyverno_ok else "#869",
    }


def _residuals(*, allow_no_db: bool, mechanism: str) -> dict[str, str]:
    """The residual tag an operator reads to see why a claim is absent."""
    if allow_no_db:
        return {"residual": "not_evidence_allow_no_db"}
    if mechanism == "unavailable":
        return {"postgres_rpo_residual": "pitr_unavailable"}
    if mechanism == "pg_dump_fallback":
        return {"postgres_rpo_residual": "not_pitr_pg_dump_fallback_#869"}
    return {}


def build_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Assemble one report from the producer's environment.

    The blocks are built by name so the report reads as what it is — header,
    Postgres, stores, platform checks — and so no single function carries the
    complexity of all of them.
    """
    e = env if env is not None else dict(os.environ)
    facts = read_run_facts(e)
    report: dict[str, Any] = {
        **_metadata_block(e, facts),
        "postgres": _postgres_block(
            e,
            facts=facts,
            note=mechanism_note(facts.mechanism),
        ),
        **_store_blocks(e),
        "outbox": _outbox_block(e),
        **_platform_block(e, facts),
    }
    fixture = _fixture_block(e)
    report["fixture"] = fixture
    report["postgres"]["rto_evidence_pass"] = rto_evidence_pass(
        rto_pass=bool(report["postgres"]["rto_pass"]),
        fixture=fixture,
    )
    report.update(
        _residuals(allow_no_db=facts.allow_no_db, mechanism=facts.mechanism)
    )
    return assert_honest(report)


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
