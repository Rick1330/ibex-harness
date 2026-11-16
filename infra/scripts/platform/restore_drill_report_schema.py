"""The restore-drill report's shape, and the rules that keep it honest.

This module is the report itself: the producer facts it grades, the blocks it
writes, and the validator that refuses a report claiming more than the run
proved. It touches no files and writes nothing; a report is a pure function of
the environment the producer recorded, so ``build_report`` takes that mapping
as an argument and only reads the process environment when given none.

The entry point is ``restore_drill_report.py`` next to this file. It owns the
CLI, the report file, the Prometheus textfile and the exit codes, and re-exports
only the schema names it lists in its ``__all__``; anything else here is
imported from this module directly. The shell producers invoke that file by
path, so the sibling import there is made path-safe rather than relying on
``PYTHONPATH``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

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


def _archive_state_proven(
    last: tuple[int, int, int] | None,
    current: tuple[int, int, int] | None,
    last_failed_after_archive: bool | None,
) -> bool:
    """Every input the queue state is read from has to be readable.

    A segment name that does not parse, or a failed-push flag the producer never
    recorded, leaves the queue state unknown. That is not "no backlog": it is
    "cannot tell", and the caller must not turn it into a bound.
    """
    if last is None:
        return False
    if current is None:
        return False
    return last_failed_after_archive is not None


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
    if not _archive_state_proven(last, current, last_failed_after_archive):
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


def _archive_bounds_rpo(archive: dict[str, Any]) -> bool:
    """Is the archive upload age an upper bound on the RPO?

    Only a successful archive whose queue is provably drained makes the age a
    bound. An undrained or unproven queue does not, so the observation is kept
    as a diagnostic and not carried as the measured RPO.
    """
    return bool(archive["wal_archive_ok"]) and archive["wal_archive_backlog"] is False


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
    if not _archive_bounds_rpo(archive):
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


def _requested_target_proven(facts: RunFacts) -> bool:
    """An unrequested target claims nothing; a requested one needs a yes.

    An unrecorded result (``None``) is a target nobody checked, not a target
    that was met, so only an affirmative result clears this gate.
    """
    if not facts.target_requested:
        return True
    return facts.target_reached is True


def _pitr_rehearsal_is_evidence(facts: RunFacts) -> bool:
    """A rehearsal is evidence only on the WAL path, with its target proven."""
    if facts.mechanism != "pgbackrest_wal":
        return False
    return _requested_target_proven(facts)


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
        return _pitr_rehearsal_is_evidence(facts)
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


def _rpo_exceeds_target(measured: Any, target: Any) -> bool:
    """Is a measured RPO above its target?

    Both sides have to be numbers before they can be compared: an unmeasured RPO
    or an unset target is not a miss, it is an absent measurement, which the
    measured-RPO rule already refuses.
    """
    if not isinstance(measured, int):
        return False
    if not isinstance(target, int):
        return False
    return measured > target


def _require_rpo_within_target(postgres: dict[str, Any]) -> None:
    """A measured RPO above the target is a miss, not a pass."""
    measured = postgres.get("rpo_measured_sec")
    target = postgres.get("rpo_target_sec")
    if _rpo_exceeds_target(measured, target):
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
