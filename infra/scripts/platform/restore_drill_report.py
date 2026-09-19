#!/usr/bin/env python3
"""Build the 4.P.5 restore-drill JSON report (honest RPO/RTO + outbox pass)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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


def postgres_rpo_pass(
    *,
    backup_ok: bool,
    restore_ok: bool,
    measured: int | None,
    target: int,
    mechanism: str,
) -> bool:
    """pg_dump_fallback is not PITR — never claim RPO pass for that mechanism."""
    if mechanism != "pgbackrest_wal":
        return False
    return backup_ok and restore_ok and le_pass(measured, target)


def mechanism_note(mechanism: str) -> str:
    if mechanism == "pg_dump_fallback":
        return (
            "pg_dump fallback is not PITR; wall-clock backup duration is recorded but "
            "rpo_pass stays false. Real ≤5m RPO requires pgBackRest+WAL (#869)."
        )
    if mechanism == "pgbackrest_wal":
        return "pgBackRest+WAL path"
    return "backup/restore not completed"


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
            backup_ok=backup_ok,
            restore_ok=restore_ok,
            measured=pg_rpo,
            target=int(e["PG_RPO_SEC"]),
            mechanism=mechanism,
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
    if allow_no_db:
        report["residual"] = "not_evidence_allow_no_db"
        report["evidence_eligible"] = False
    elif mechanism == "pg_dump_fallback":
        report["postgres_rpo_residual"] = "not_pitr_pg_dump_fallback_#869"
    return report


def _emit_warnings(report: dict[str, Any], *, allow_no_db: bool, path: Path) -> None:
    if not report["tenant_isolation_post_restore"]:
        if allow_no_db:
            print(
                "WARNING: tenant isolation not proven (ALLOW_NO_DB=1; no Postgres)",
                flush=True,
            )
            report["residual"] = "tenant_isolation_unproven_no_postgres"
            path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return
        raise SystemExit("tenant isolation check failed")
    if report["postgres"]["rpo_measured_sec"] is not None and not report["postgres"]["rpo_pass"]:
        print(
            "WARNING: postgres RPO not claimed (mechanism/target) — see residuals",
            flush=True,
        )
    if report["postgres"]["rto_measured_sec"] is not None and not report["postgres"]["rto_pass"]:
        print("WARNING: postgres RTO miss vs targets — investigate residual", flush=True)
    if not report["outbox"]["rpo_pass"]:
        print(
            "WARNING: outbox rpo_pass false (pending!=0 or outbox unreadable)",
            flush=True,
        )


def main() -> None:
    report = build_report()
    path = Path(os.environ["REPORT"])
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    _emit_warnings(report, allow_no_db=os.environ.get("ALLOW_NO_DB") == "1", path=path)


if __name__ == "__main__":
    main()
