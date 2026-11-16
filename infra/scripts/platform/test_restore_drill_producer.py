#!/usr/bin/env python3
"""Producer cases: what the drill reads, and from which server.

`restore-drill.sh` reads the replayed transaction of the cluster a pgBackRest
restore produced. The convenient way to read it — `psql_cmd` — is not that
cluster: `psql_cmd` talks to `POSTGRES_DSN`, the default localhost DSN, or the
container named by `POSTGRES_CONTAINER`, while the restore writes into the
Compose volume or `PGBACKREST_PGDATA`. A live primary reached that way has no
replayed transaction at all, so reading it there leaves an untargeted RPO bound
unmeasured and fails a targeted restore that worked.

These cases drive the shipped scripts from a temporary repository root (the
pgBackRest branch needs `infra/backup/pgbackrest/pgbackrest.conf`, which is
gitignored) with two `psql` servers behind one stub: the connection the restore
builds from the restored `postmaster.pid`, and the DSN connection the drill uses
for everything else. The stub answers `-1` for a replayed transaction on the DSN
side — a live primary — so a drill that read the wrong server cannot pass.
"""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from restore_drill_test_support import PLATFORM_DIR
from test_restore_drill_branches import host_data_dir, write_stub
from test_restore_drill_mechanism import command_path, run_bash

# The real repository root, and the shipped files the drill executes. They are
# symlinked into a temporary root so the scripts under test are the ones that
# ship, byte for byte.
REPO_ROOT = PLATFORM_DIR.parents[2]
_REPO_FILES = (
    "infra/scripts/lib/pitr_time.sh",
    "infra/scripts/platform/pgbackrest-backup.sh",
    "infra/scripts/platform/pgbackrest-restore.sh",
    "infra/scripts/platform/pitr_report.sh",
    "infra/scripts/platform/restore-drill.sh",
    "infra/scripts/platform/restore_drill_report.py",
)

# Commands the three scripts need before they reach a stub of their own.
_PATH_COMMANDS = (
    "awk",
    "bash",
    "cat",
    "chmod",
    "date",
    "dirname",
    "grep",
    "head",
    "id",
    "mkdir",
    "mktemp",
    "mv",
    "python3",
    "rm",
    "sed",
    "seq",
    "sha256sum",
    "sleep",
    "tail",
    "tee",
    "tr",
)

# A local throwaway DSN that is never connected to: the stub answers every query.
# Not a credential.
_DSN_FIXTURE = "postgres://drill:drill@127.0.0.1:1/drill?sslmode=disable"

# Two servers behind one `psql`. The restore script connects with `-p 55432` to
# the port it read from the restored postmaster.pid, and that side answers with
# the restored cluster's replayed transaction. Every other call is the drill's
# `psql_cmd`, which reaches the DSN: a live primary, so no replayed transaction.
_PSQL_STUB = r"""#!/usr/bin/env bash
printf 'PSQL %s\n' "$*" >>"${STUB_LOG:-/dev/null}"
case "$*" in
  *"-p 55432"*)
    case "$*" in
      *pg_is_in_recovery*) printf 'f\n' ;;
      *"show data_directory"*) printf '%s\n' "${STUB_DATA_DIR:?}" ;;
      *"FROM pg_database"*) printf '1\n' ;;
      *pg_last_xact_replay_timestamp*) printf '%s|12345678\n' "${STUB_RESTORED_REPLAY_US:?}" ;;
      *ibex_core.organizations*) printf '2\n' ;;
      *ibex_core.memories*) printf '9\n' ;;
      *) : ;;
    esac
    ;;
  *)
    case "$*" in
      *pg_is_in_recovery*) printf 'f\n' ;;
      *pg_last_xact_replay_timestamp*) printf -- '-1\n' ;;
      *pg_database_size*) printf '4096\n' ;;
      *ibex_core.organizations*) printf '2\n' ;;
      *ibex_core.memories*) printf '9\n' ;;
      *) : ;;
    esac
    ;;
esac
exit 0
"""

# `pgbackrest` and `pg_ctl`: log the argv and succeed. Neither is the behaviour
# under test; which server the replay fact came from is.
_TOOL_STUB = r"""#!/usr/bin/env bash
printf '%s %s\n' "${0##*/}" "$*" >>"${STUB_LOG:-/dev/null}"
exit 0
"""


def fake_repo(root: Path) -> Path:
    """A repository root holding symlinks to the shipped scripts and a conf.

    The drill's pgBackRest branch requires
    `infra/backup/pgbackrest/pgbackrest.conf` relative to its own root. That file
    is gitignored, so a checkout may not have one; creating it under a temporary
    root keeps the test portable and leaves the real tree untouched.
    """
    for relative in _REPO_FILES:
        link = root / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(REPO_ROOT / relative)
    conf = root / "infra" / "backup" / "pgbackrest" / "pgbackrest.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text("[global]\nrepo1-type=s3\n", encoding="utf-8")
    return root


def drill_env(root: Path, *, restored_replay_us: int, target: str) -> dict[str, str]:
    """The drill's environment, with the restored cluster behind its own psql."""
    bindir = command_path(root / "bin", _PATH_COMMANDS)
    write_stub(bindir, "psql", _PSQL_STUB)
    write_stub(bindir, "pg_ctl", _TOOL_STUB)
    write_stub(bindir, "pgbackrest", _TOOL_STUB)
    pgdata = host_data_dir(root)
    return {
        "PATH": str(bindir),
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "RESTORE_DRILL_REPORT_DIR": str(root / "reports"),
        "IBEX_DRILL_METRICS_PATH": str(root / "metrics.prom"),
        "IBEX_DRILL_ENVIRONMENT_CLASS": "test-harness",
        "IBEX_BACKUP_STATE_DIR": str(root / "backup-state"),
        "IBEX_DRILL_TARGET": target,
        "SKIP_COMPOSE": "1",
        "POSTGRES_DSN": _DSN_FIXTURE,
        # The isolation check is not this module's subject, and a drill that
        # never ran it may only be written as a smoke run.
        "ALLOW_NO_DB": "1",
        "PGBACKREST_CONF": str(root / "infra" / "backup" / "pgbackrest" / "pgbackrest.conf"),
        "PGBACKREST_STANZA": "ibex-main",
        "PGBACKREST_PGDATA": str(pgdata),
        "COMPOSE_FILE": str(root / "no-compose.yml"),
        "STUB_DATA_DIR": str(pgdata),
        "STUB_RESTORED_REPLAY_US": str(restored_replay_us),
        "STUB_LOG": str(root / "tools.log"),
    }


def utc_micros(moment: datetime.datetime) -> int:
    """Integer microseconds since the epoch, without float rounding."""
    return int(moment.timestamp()) * 1_000_000


class RestoredClusterReplayTests(unittest.TestCase):
    """The drill grades the restore with the restored cluster's own frontier."""

    def _run(self, root: Path, *, target: str, replay: datetime.datetime):
        fake_repo(root)
        env = drill_env(root, restored_replay_us=utc_micros(replay), target=target)
        proc = run_bash(root / "infra" / "scripts" / "platform" / "restore-drill.sh", env)
        report = json.loads(
            (root / "reports" / "restore-drill-report.json").read_text(encoding="utf-8")
        )
        return proc, report, (root / "tools.log").read_text(encoding="utf-8")

    def test_untargeted_drill_measures_the_bound_from_the_restored_cluster(self) -> None:
        # The defect: the DSN server answers -1 for a replayed transaction, so a
        # drill that read it there left the bound unmeasured.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=60)
            proc, report, calls = self._run(root, target="", replay=replay)
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertEqual(report["postgres"]["mechanism"], "pgbackrest_wal")
            self.assertTrue(report["postgres"]["restore_ok"])
            self.assertEqual(
                report["postgres"]["recovery_replay_timestamp"],
                replay.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            # The bound is the gap the restore demonstrated: ~60 s of it is the
            # fixture, the rest is this run's own runtime.
            self.assertGreaterEqual(report["postgres"]["rpo_upper_bound_sec"], 60)
            self.assertLessEqual(report["postgres"]["rpo_upper_bound_sec"], 300)
            self.assertTrue(report["postgres"]["rpo_pass"])
            # Both servers were asked, and they answered differently: the two
            # are not the same server, which is what makes the read matter.
            self.assertIn(f"PSQL {_DSN_FIXTURE} -Atc", calls)
            self.assertIn("pg_last_xact_replay_timestamp", calls)

    def test_targeted_drill_proves_the_target_from_the_restored_cluster(self) -> None:
        # The same defect's other half: a DSN server with no replay timestamp
        # cannot prove a target, so a targeted restore that worked was reported
        # as a miss.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = datetime.datetime(2026, 11, 16, 7, 42, 47, tzinfo=datetime.UTC)
            proc, report, _calls = self._run(
                root, target="2026-11-16T07:42:48Z", replay=replay
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("recovery target reached", output)
            self.assertTrue(report["postgres"]["restore_ok"])
            self.assertTrue(report["postgres"]["recovery_target_reached"])
            self.assertEqual(
                report["postgres"]["recovery_replay_timestamp"],
                "2026-11-16T07:42:47Z",
            )
            # A targeted run proves the target, not an RPO.
            self.assertIsNone(report["postgres"]["rpo_upper_bound_sec"])
            self.assertFalse(report["postgres"]["rpo_pass"])


if __name__ == "__main__":
    unittest.main()
