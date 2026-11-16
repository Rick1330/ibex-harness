#!/usr/bin/env python3
"""Branch cases: the destructive Compose path and the host data-directory path.

`pgbackrest-restore.sh` restores through three branches, and each one has to
prove the same things: that the cluster left recovery, that the requested
recovery target was reached, and that the recovery facts were read from *that*
cluster. The scratch branch is covered in `test_restore_drill_mechanism`; this
module drives the other two with the same stub-engine style, so a branch cannot
regress to reporting a success it never proved.

A host restore records `restore_target: host`. The PITR producer never measures
tenant isolation, so its report records `tenant_isolation_post_restore: null`
with a residual rather than a failure it never observed, and the run exits zero
once the restore, the target and the frontier are proven.
"""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from restore_drill_test_support import PITR_RESTORE_SH
from test_restore_drill_mechanism import (
    RestoreRequest,
    command_path,
    restore_env,
    run_bash,
    utc_micros,
)

# The host branch runs `pgbackrest`, `pg_ctl` and `psql` from PATH. These stubs
# answer exactly the queries the script issues and log every psql argv, so a test
# can prove the script executed `psql` and not one of psql's own options. The
# values are fixtures: no credential and no real cluster data.
_HOST_PATH_COMMANDS = (
    "awk",
    "bash",
    "cat",
    "chmod",
    "date",
    "dirname",
    "grep",
    "head",
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
    "tr",
)

_PSQL_STUB = r"""#!/usr/bin/env bash
printf 'PSQL %s\n' "$*" >>"${STUB_LOG:-/dev/null}"
case "$*" in
  *pg_is_in_recovery*) printf 'f\n' ;;
  *"show data_directory"*) printf '%s\n' "${STUB_DATA_DIR:?}" ;;
  *"FROM pg_database"*) printf '1\n' ;;
  *pg_last_xact_replay_timestamp*) printf '%s|12345678\n' "${STUB_REPLAY_US:--1}" ;;
  *ibex_core.organizations*) printf '2\n' ;;
  *ibex_core.memories*) printf '9\n' ;;
  *) : ;;
esac
exit 0
"""

# `pg_ctl` and `pgbackrest`: log the argv under the name they were invoked as and
# succeed. Neither is the behaviour under test; the facts query is.
_TOOL_STUB = r"""#!/usr/bin/env bash
printf '%s %s\n' "${0##*/}" "$*" >>"${STUB_LOG:-/dev/null}"
exit 0
"""

# The Compose branch: `compose stop postgres` has to succeed, and the volume and
# network have to resolve, so the restore reaches its verification step.
_COMPOSE_ENGINE_STUB = r"""#!/usr/bin/env bash
set -u
first="${1:-}"
shift || true
case "$first" in
  volume | rm | logs | run) exit 0 ;;
  inspect) printf '%s\n' "${STUB_NETWORK:-stubnet}"; exit 0 ;;
  compose)
    case " $* " in
      *" stop "*) exit 0 ;;
      *" start "*) exit 0 ;;
      *" ps -q postgres "*) printf 'pgcid\n' ;;
      *" ps -q objectstore "*) printf 'objectcid\n' ;;
      *" config "*) printf '%s\n' "${STUB_COMPOSE_CONFIG:-}" ;;
      *) : ;;
    esac
    exit 0
    ;;
  exec)
    printf 'EXEC %s\n' "$*" >>"${STUB_LOG:-/dev/null}"
    case " $* " in
      *pg_is_in_recovery*) printf 'f\n' ;;
      *pg_last_xact_replay_timestamp*) printf '%s|12345678\n' "${STUB_REPLAY_US:--1}" ;;
      *ibex_core.organizations*) printf '2\n' ;;
      *ibex_core.memories*) printf '9\n' ;;
      *) : ;;
    esac
    exit 0
    ;;
esac
exit 0
"""


def write_stub(directory: Path, name: str, body: str) -> Path:
    """Write one executable stub into a PATH directory."""
    stub = directory / name
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    return stub


def host_data_dir(root: Path) -> Path:
    """A stopped-cluster data directory the host branch will accept.

    `postmaster.pid` carries the port and socket directory the script reads, so
    the connection it builds points at this directory and nowhere else.
    """
    pgdata = root / "pgdata"
    pgdata.mkdir()
    (pgdata / "PG_VERSION").write_text("16\n", encoding="utf-8")
    socket = root / "socket"
    socket.mkdir()
    pid = ("4242", str(pgdata), "1700000000", "55432", str(socket), "127.0.0.1", "0", "ready")
    (pgdata / "postmaster.pid").write_text("\n".join(pid) + "\n", encoding="utf-8")
    return pgdata


def host_restore_env(request: RestoreRequest) -> dict[str, str]:
    """The environment for the host branch: stubbed tools, and a data directory."""
    root = request.root
    env = restore_env(request)
    bindir = command_path(root / "tools", _HOST_PATH_COMMANDS)
    write_stub(bindir, "psql", _PSQL_STUB)
    write_stub(bindir, "pg_ctl", _TOOL_STUB)
    write_stub(bindir, "pgbackrest", _TOOL_STUB)
    pgdata = host_data_dir(root)
    env.pop("PGBACKREST_RESTORE_SCRATCH_VOLUME", None)
    env.update(
        {
            "PATH": str(bindir),
            "PGBACKREST_PGDATA": str(pgdata),
            "STUB_DATA_DIR": str(pgdata),
            "STUB_REPLAY_US": str(request.replay_us),
            "STUB_LOG": str(root / "tools.log"),
        }
    )
    return env


def compose_restore_env(request: RestoreRequest) -> dict[str, str]:
    """The environment for the destructive Compose branch."""
    root = request.root
    env = restore_env(request)
    env.pop("PGBACKREST_RESTORE_SCRATCH_VOLUME", None)
    env.pop("PGBACKREST_PGDATA", None)
    write_stub(root / "bin", "stub-engine", _COMPOSE_ENGINE_STUB)
    env.update(
        {
            "STUB_LOG": str(root / "engine.log"),
            "STUB_COMPOSE_CONFIG": (
                '{"services": {"postgres": {"environment": '
                '{"POSTGRES_USER": "ibex", "POSTGRES_DB": "ibex"}}}, '
                '"volumes": {"ibex_postgres_data": {}}}'
            ),
        }
    )
    return env


def assert_unproven_target_fails(
    test: unittest.TestCase, env: dict[str, str], report: Path
) -> None:
    """Run a targeted restore and prove it refused to claim the target.

    Shared by the host and Compose paths: both must exit non-zero and leave the
    report with no target, no restore, and no RPO claim.
    """
    proc = run_bash(PITR_RESTORE_SH, env)
    output = proc.stdout + proc.stderr
    test.assertNotEqual(proc.returncode, 0, output)
    test.assertIn("did not prove the requested target", output)
    written = json.loads(report.read_text(encoding="utf-8"))
    test.assertIsNone(written["postgres"]["recovery_target_reached"])
    test.assertFalse(written["postgres"]["restore_ok"])
    test.assertFalse(written["postgres"]["rpo_pass"])


class HostRestoreTargetTests(unittest.TestCase):
    """The host branch must prove the target through the connection it built.

    The facts query runs `psql`, not the connection options on their own: the
    branch used to pass `-p <port> -h <socket>` as the *command*, so every query
    failed silently, the target stayed unproven, and a successful host recovery
    failed the affirmative target check.
    """

    def test_host_restore_passes_the_target_through_psql(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_bash(
                PITR_RESTORE_SH,
                host_restore_env(
                    RestoreRequest(
                        root=root,
                        target="2026-11-16T07:42:48Z",
                        replay_us=utc_micros("2026-11-16T07:42:47Z"),
                        report=report,
                    )
                ),
            )
            output = proc.stdout + proc.stderr
            # The restore and its target proof succeed. Isolation was never
            # measured, so the report says so and the run still exits zero.
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("recovery target reached", output)
            calls = (root / "tools.log").read_text(encoding="utf-8")
            # The executable is psql and the connection options are its arguments.
            self.assertIn("PSQL -p 55432 -h ", calls)
            self.assertIn("-d postgres -tAc SELECT 1 FROM pg_database", calls)
            self.assertIn("-d ibex -tAc", calls)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])
            self.assertTrue(written["postgres"]["restore_ok"])
            self.assertEqual(written["postgres"]["restore_target"], "host")
            self.assertEqual(written["postgres"]["restored_row_counts"]["memories"], 9)
            self.assertIsNone(written["tenant_isolation_post_restore"])
            self.assertEqual(
                written["residual"], "tenant_isolation_not_measured_pitr"
            )

    def test_host_restore_with_an_unproven_target_fails(self) -> None:
        # psql answers nothing usable, so no replayed transaction was read. A
        # targeted host restore that cannot prove its target is not a success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            env = host_restore_env(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=-1,
                    report=report,
                )
            )
            assert_unproven_target_fails(self, env, report)


class HostRestoreFrontierTests(unittest.TestCase):
    """A destructive restore records the frontier it demonstrated.

    The quiesce instant is written only after the stop returned, and the replay
    instant is read from the restored cluster for every successful restore. An
    untargeted run is the only one that can carry an RPO upper bound, and these
    cases drive the shipped script to prove it does.
    """

    def _restore(self, root: Path, *, target: str, replay: datetime.datetime):
        report = root / "pitr-report.json"
        facts = root / "facts.env"
        replay = replay.replace(microsecond=0)
        replay_us = int(replay.timestamp()) * 1_000_000
        env = host_restore_env(
            RestoreRequest(root=root, target=target, replay_us=replay_us, report=report)
        )
        env["PGBACKREST_RESTORE_FACTS_FILE"] = str(facts)
        return run_bash(PITR_RESTORE_SH, env), report, facts, replay

    def test_untargeted_host_restore_claims_a_demonstrated_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=60)
            proc, report, facts, replay = self._restore(root, target="", replay=replay)
            output = proc.stdout + proc.stderr
            # The bound is demonstrated and written; isolation is recorded as
            # not measured, and the run exits zero.
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("WAL archiving quiesced at", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertIsNone(written["postgres"]["target_timestamp"])
            self.assertIsNotNone(written["postgres"]["wal_archive_quiesced_at"])
            self.assertEqual(
                written["postgres"]["recovery_replay_timestamp"],
                replay.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            # The bound is the gap the restore demonstrated: ~60 s of it is the
            # fixture, the rest is this run's own runtime.
            self.assertGreaterEqual(written["postgres"]["rpo_upper_bound_sec"], 60)
            self.assertLessEqual(written["postgres"]["rpo_upper_bound_sec"], 300)
            self.assertTrue(written["postgres"]["rpo_pass"])
            self.assertEqual(written["postgres"]["restore_target"], "host")
            self.assertIsNone(written["tenant_isolation_post_restore"])
            self.assertEqual(
                written["residual"], "tenant_isolation_not_measured_pitr"
            )
            # The facts file is what a parent shell can read, and it carries no
            # credential: only timestamps and counts.
            facts_text = facts.read_text(encoding="utf-8")
            self.assertIn("wal_archive_quiesced_at=", facts_text)
            for secret in ("fixture-cipher", "fixture-key", "fixture-secret"):
                self.assertNotIn(secret, facts_text)

    def test_targeted_host_restore_carries_no_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc, report, _facts, _replay = self._restore(
                root,
                target="2026-11-16T07:42:48Z",
                replay=datetime.datetime(2026, 11, 16, 7, 42, 47, tzinfo=datetime.UTC),
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])
            self.assertEqual(written["postgres"]["restore_target"], "host")
            self.assertIsNone(written["tenant_isolation_post_restore"])
            self.assertIsNone(written["postgres"]["rpo_upper_bound_sec"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertEqual(
                written["postgres_rpo_residual"],
                "targeted_restore_proves_target_not_rpo",
            )


class ComposeRestoreTargetTests(unittest.TestCase):
    """The destructive Compose branch makes the same target claim, and needs the same proof."""

    def test_compose_restore_with_an_unproven_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            env = compose_restore_env(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=-1,
                    report=report,
                    scratch=None,
                )
            )
            assert_unproven_target_fails(self, env, report)


