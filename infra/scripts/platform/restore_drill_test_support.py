"""Fixtures and helpers shared by the restore-drill report tests.

The cases are split by concern into the ``test_restore_drill_*.py`` siblings
next to this file. What more than one of them needs lives here: the report
writer loaded from its path (it is a script, not an installed module), the
paths of the scripts under test, and the base environment every report case
starts from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent
REPORT_PY = PLATFORM_DIR / "restore_drill_report.py"
DRILL_SH = PLATFORM_DIR / "restore-drill.sh"
PITR_RESTORE_SH = PLATFORM_DIR / "pgbackrest-restore.sh"

_spec = importlib.util.spec_from_file_location("restore_drill_report", REPORT_PY)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load restore_drill_report from {REPORT_PY}")
mod = importlib.util.module_from_spec(_spec)
sys.modules["restore_drill_report"] = mod
_spec.loader.exec_module(mod)


# Fixture path only — never opens or writes this file (avoids Bandit B108).
TRANSCRIPT_FIXTURE = "infra/scripts/platform/evidence/4p5-restore-drill/transcript.txt"


def base_env(**overrides: str) -> dict[str, str]:
    """A drained pg_dump-fallback drill environment, then ``overrides`` applied."""
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
        "TRANSCRIPT": TRANSCRIPT_FIXTURE,
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
