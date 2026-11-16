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

import datetime
import os
from dataclasses import dataclass
from typing import Any

from restore_drill_archive import ArchiveContinuity, wal_archive_backlog

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
    """Integer, or ``None`` when the producer recorded nothing readable.

    A value the producer could not parse is unproven, not a crash: raising here
    killed the report writer *after* a restore had already run, so the run left
    no artefact at all. "unknown" and "" both mean the same thing to a reader.
    """
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


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

    ``bound`` is the frontier the restore demonstrated, not an observation of
    ``pg_stat_archiver``: a drained-looking queue over a commit older than the
    number claims is exactly the case this refuses. A targeted restore proves
    the target was reached, not an RPO, so it never passes.

    Expected keys: mechanism, backup_ok, restore_ok, bound, target,
    target_requested.
    """
    if ctx.get("mechanism") != "pgbackrest_wal":
        return False
    if ctx.get("target_requested"):
        return False
    bound = ctx.get("bound")
    if isinstance(bound, bool) or not isinstance(bound, int):
        return False
    return (
        bool(ctx.get("backup_ok"))
        and bool(ctx.get("restore_ok"))
        and le_pass(bound, int(ctx["target"]))
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


def _archive_continuity(e: dict[str, str]) -> ArchiveContinuity:
    """The two measurements that establish continuity beyond adjacency."""
    return ArchiveContinuity(
        wal_segment_size=parse_int_or_none(e.get("WAL_ARCHIVE_WAL_SEGMENT_SIZE", "")),
        older_segments_present=parse_int_or_none(e.get("WAL_ARCHIVE_OLDER_SEGMENTS", "")),
    )


def _wal_archive_facts(e: dict[str, str]) -> dict[str, Any]:
    """What the producer observed about the archive. Diagnostics only.

    None of these gates the RPO. The restore replays every segment from the
    backup to the replay point, so a gap either stops recovery or truncates the
    replay timestamp, and the derived bound shows it. The counters are recorded
    for diagnosis: ``pg_wal`` holds retained-but-archived segments, and
    ``wal_archive_ok`` is sampled before the backup, so a freshly initialised
    stanza reads ``false`` for a run that demonstrably worked.
    """
    continuity = _archive_continuity(e)
    return {
        "wal_archive_ok": e.get("WAL_ARCHIVE_OK") == "true",
        "wal_archive_upload_age_sec": parse_int_or_none(
            e.get("WAL_ARCHIVE_UPLOAD_AGE_SEC", "")
        ),
        "wal_archive_timeout_sec": parse_int_or_none(
            e.get("WAL_ARCHIVE_TIMEOUT_SEC", "")
        ),
        "wal_archive_wal_segment_size": continuity.wal_segment_size,
        "wal_archive_backlog": wal_archive_backlog(
            last_archived_wal=e.get("WAL_ARCHIVE_LAST_SEGMENT"),
            current_wal=e.get("WAL_ARCHIVE_CURRENT_SEGMENT"),
            last_failed_after_archive=parse_bool_or_none(
                e.get("WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE")
            ),
            continuity=continuity,
        ),
    }


def _iso_micros(value: Any) -> int | None:
    """Integer microseconds for an ISO8601 UTC instant, or ``None``.

    The producers write ``…Z`` at microsecond precision. A zone-less or non-UTC
    value is not the instant the frontier pair is made of, so it is refused
    rather than converted through the host's local time.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.timedelta(0):
        return None
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
    delta = parsed - epoch
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def rpo_upper_bound(quiesced_at: Any, replay_at: Any) -> int | None:
    """The RPO upper bound the restore demonstrated, in whole seconds.

    ``ceil(wal_archive_quiesced_at - recovery_replay_timestamp)``. Once the
    primary is stopped nothing new is archived, so the newest recoverable commit
    is frozen at that instant; the restored cluster replayed up to
    ``recovery_replay_timestamp``. The gap is the wall-clock distance to the
    newest recoverable commit, so it includes idle time before the stop and
    cannot report a bound smaller than the producer's own quiescence.

    Rounded **up**: a bound must not round toward optimism. A negative difference
    is ``None``, never 0: a replay later than the quiesce instant means these are
    not the frontier pair, not that the RPO is zero.
    """
    quiesced = _iso_micros(quiesced_at)
    replay = _iso_micros(replay_at)
    if quiesced is None or replay is None:
        return None
    delta = quiesced - replay
    if delta < 0:
        return None
    return -(-delta // 1_000_000)


def _restore_outcome(facts: RunFacts) -> tuple[bool, bool]:
    """The (backup_ok, restore_ok) a report may carry for this run.

    An ``unavailable`` run restored nothing, so its report must not also carry
    the booleans of a run that happened.
    """
    if facts.mechanism == "unavailable":
        return False, False
    return facts.backup_ok, facts.restore_ok


def _postgres_block(e: dict[str, str], *, facts: RunFacts, note: str) -> dict[str, Any]:
    pg_rto = parse_int_or_none(e.get("PG_RTO_MEASURED", ""))
    backup_ok, restore_ok = _restore_outcome(facts)
    rpo_target = target_sec(e, "PG_RPO_SEC")
    rto_target = target_sec(e, "PG_RTO_SEC")
    archive = _wal_archive_facts(e)
    # The RPO is what the restore demonstrated between the instant archiving
    # stopped and the instant the restored cluster replayed to: null when either
    # instant is missing, so the field cannot be quoted as a bound the run did
    # not establish.
    quiesced_at = optional_text(e.get("WAL_ARCHIVE_QUIESCED_AT"))
    replay_at = optional_text(e.get("RECOVERY_REPLAY_TIMESTAMP"))
    # A dump has no recoverable WAL position and a targeted restore proves the
    # target rather than an RPO: neither carries a number.
    bound = None
    if facts.mechanism == "pgbackrest_wal" and not facts.target_requested:
        bound = rpo_upper_bound(quiesced_at, replay_at)
    rpo_pass = postgres_rpo_pass(
        {
            "backup_ok": backup_ok,
            "restore_ok": restore_ok,
            "bound": bound,
            "target": rpo_target,
            "mechanism": facts.mechanism,
            "target_requested": facts.target_requested,
        }
    )
    return {
        "rpo_target_sec": rpo_target,
        "rto_target_sec": rto_target,
        "rpo_upper_bound_sec": bound,
        "rto_measured_sec": pg_rto,
        "backup_ok": backup_ok,
        "restore_ok": restore_ok,
        "rpo_pass": rpo_pass,
        "rto_pass": restore_ok and le_pass(pg_rto, rto_target),
        "mechanism": facts.mechanism,
        # scratch|host from the branch the run took; never an env class.
        "restore_target": optional_text(e.get("PG_RESTORE_TARGET")),
        **archive,
        "wal_archive_quiesced_at": quiesced_at,
        "target_timestamp": optional_text(e.get("TARGET_TIMESTAMP")),
        "recovery_target_reached": facts.target_reached,
        "recovery_replay_timestamp": replay_at,
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
    iso_ok: bool | None
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
        iso_ok=parse_bool_or_none(e.get("ISO_OK")),
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
    survives the restore, so only a measured ``true`` qualifies. A point-in-time
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
    return facts.iso_ok is True


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
        raise ReportHonestyError(f"rpo_pass requires mechanism pgbackrest_wal, got {mechanism!r}")


def _require_untargeted_restore(postgres: dict[str, Any]) -> None:
    """A targeted restore proves the target, not an RPO.

    Its elapsed time is dominated by the operator's target choice and the
    restore, so the gap is not archive lag; a targeted run cannot pass at all.
    """
    target = postgres.get("target_timestamp")
    if target:
        raise ReportHonestyError(
            "an RPO upper bound requires an untargeted restore: a targeted "
            "restore proves the target was reached, not an RPO "
            f"(target_timestamp={target})"
        )


def _require_completed_restore(postgres: dict[str, Any]) -> None:
    """An RPO measured over a restore that did not complete is not a result.

    The producer always builds ``rpo_pass`` from ``restore_ok``, but a report is
    a file: one written or edited outside the producer can carry a pass over a
    restore that failed, and an operator reading it at 03:00 has no way to tell.
    """
    if postgres.get("restore_ok") is not True:
        raise ReportHonestyError("rpo_pass requires a completed restore (restore_ok=true)")


def _require_instant(value: Any, field: str) -> None:
    """One half of the frontier pair: present, and a parseable ISO8601 UTC instant."""
    if _iso_micros(value) is not None:
        return
    if not (isinstance(value, str) and value.strip()):
        raise ReportHonestyError(f"an RPO upper bound requires {field}: nothing was recorded")
    raise ReportHonestyError(f"{field} must be an ISO8601 UTC timestamp, got {value!r}")


def _require_frontier_facts(postgres: dict[str, Any]) -> None:
    """The bound is derived from two measured instants; both have to be readable.

    A number without them is an assertion, and each instant gets its own message
    so an operator at 03:00 knows which measurement the run is missing.
    """
    for field in ("wal_archive_quiesced_at", "recovery_replay_timestamp"):
        _require_instant(postgres.get(field), field)


def _require_rpo_derived(postgres: dict[str, Any]) -> None:
    """The number must be the one the two instants produce.

    A report is a file: a number written beside a frontier that does not produce
    it is a forgery, not a measurement. The validator re-derives it instead of
    trusting the field, so ``17`` beside a 400 s frontier is refused.
    """
    claimed = _integer_seconds(postgres.get("rpo_upper_bound_sec"), "rpo_upper_bound_sec")
    derived = rpo_upper_bound(
        postgres.get("wal_archive_quiesced_at"),
        postgres.get("recovery_replay_timestamp"),
    )
    if derived != claimed:
        raise ReportHonestyError(
            "rpo_upper_bound_sec does not match the frontier it claims: "
            f"{claimed}s reported, {derived}s derived"
        )


def _integer_seconds(value: Any, field: str) -> int:
    """The contract is integer seconds: a float is rejected, never compared.

    Skipping the comparison for a non-integer is how ``900.0`` against a 300 s
    target used to pass: the guard silently returned "not above target" for a
    value it could not read. A report that carries a float is malformed, and a
    malformed report is refused rather than half-checked.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportHonestyError(
            f"{field} must be integer seconds, got {value!r}"
        )
    return value


def _require_rpo_within_target(postgres: dict[str, Any]) -> None:
    """An RPO upper bound above the target is a miss, not a pass."""
    bound = _integer_seconds(postgres.get("rpo_upper_bound_sec"), "rpo_upper_bound_sec")
    target = _integer_seconds(postgres.get("rpo_target_sec"), "rpo_target_sec")
    if bound > target:
        raise ReportHonestyError(
            f"rpo_pass cannot be claimed with an RPO upper bound of {bound}s "
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
        _require_untargeted_restore(postgres)
        _require_completed_restore(postgres)
        _require_frontier_facts(postgres)
        _require_rpo_derived(postgres)
        _require_rpo_within_target(postgres)
    elif postgres.get("rpo_upper_bound_sec") is not None:
        # A number with no pass must still be internally consistent: it has to
        # be the one the recorded frontier produces, on the mechanism that can
        # produce it, for a run that was not targeted.
        _require_pitr_mechanism(mechanism)
        _require_untargeted_restore(postgres)
        _require_frontier_facts(postgres)
        _require_rpo_derived(postgres)
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


def _residuals(
    *, allow_no_db: bool, mechanism: str, target_requested: bool
) -> dict[str, str]:
    """The residual tag an operator reads to see why a claim is absent."""
    if allow_no_db:
        return {"residual": "not_evidence_allow_no_db"}
    if mechanism == "unavailable":
        return {"postgres_rpo_residual": "pitr_unavailable"}
    if mechanism == "pg_dump_fallback":
        return {"postgres_rpo_residual": "not_pitr_pg_dump_fallback_#869"}
    if target_requested:
        return {"postgres_rpo_residual": "targeted_restore_proves_target_not_rpo"}
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
        _residuals(
            allow_no_db=facts.allow_no_db,
            mechanism=facts.mechanism,
            target_requested=facts.target_requested,
        )
    )
    return assert_honest(report)
