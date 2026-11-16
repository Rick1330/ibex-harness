#!/usr/bin/env python3
"""Mechanism cases: the real scripts, and what they do when PITR cannot run.

The report writer is only half of the honesty boundary: the producer decides
what it observed. These cases drive `restore-drill.sh` and
`pgbackrest-restore.sh` themselves, with a stubbed container engine, so the
mechanism guard, the target comparison, the exit trap and the report write are
the ones that ship.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess  # nosec B404 - the drill tests must run the real scripts; argv is fixed and there is no shell
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

from restore_drill_test_support import DRILL_SH, PITR_RESTORE_SH

# A local throwaway database that is never connected to: the mechanism guard and
# the refusal path both fire before any database access. Not a credential.
_DSN_FIXTURE = "postgres://drill:drill@127.0.0.1:1/drill?sslmode=disable"

# Commands the drill needs before it reaches the mechanism guard. pgbackrest is
# deliberately absent from the directory, which is the condition under test;
# nothing here is a stub of the script's own logic.
_DRILL_PATH_COMMANDS = (
    "bash",
    "cat",
    "date",
    "dirname",
    "grep",
    "mkdir",
    "python3",
    "seq",
    "sleep",
    "tail",
    "tee",
    "tr",
)

# Container-engine stub for the scratch PITR path. Every psql answer is matched
# on the SQL the script actually issues, so a query this stub does not know
# returns nothing — which the script must treat as unmeasured, not as a pass.
# The values are fixtures: none is a credential and none is real cluster data.
_ENGINE_STUB = r"""#!/usr/bin/env bash
set -u
first="${1:-}"
shift || true
case "$first" in
  volume | rm | logs | run) exit 0 ;;
  inspect) printf '%s\n' "${STUB_NETWORK:-stubnet}"; exit 0 ;;
  compose)
    case " $* " in
      *" stop "*) exit 1 ;;
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


class RestoreRequest(NamedTuple):
    """One scratch restore: where, to which target, and where the report goes."""

    root: Path
    target: str
    replay_us: int
    report: Path
    scratch: str | None = "stubvol"


def utc_micros(iso: str) -> int:
    """Integer microseconds for an ISO8601 UTC timestamp, without float rounding."""
    parsed = datetime.datetime.fromisoformat(iso)
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
    delta = parsed - epoch
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def run_bash(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    """Run a repository script with a fixed argv and no shell."""
    # Fixed argv, no shell: the only variable is the script path this test owns.
    return subprocess.run(  # nosec B603
        ["/bin/bash", str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def command_path(directory: Path, commands: tuple[str, ...]) -> Path:
    """A PATH holding only ``commands``, so pgbackrest is deliberately absent."""
    directory.mkdir(exist_ok=True)
    for name in commands:
        found = shutil.which(name)
        if found:
            os.symlink(found, directory / name)
    return directory


def drill_env(root: Path, *, mechanism: str | None) -> dict[str, str]:
    """The drill's environment, with pgbackrest missing from PATH.

    ``mechanism`` is how the caller requests pgBackRest: ``None`` leaves
    ``IBEX_DRILL_MECHANISM`` unset for the flag form, and a value sets it for the
    environment form.
    """
    env = {
        **os.environ,
        "PATH": str(command_path(root / "bin", _DRILL_PATH_COMMANDS)),
        "RESTORE_DRILL_REPORT_DIR": str(root / "reports"),
        "IBEX_DRILL_METRICS_PATH": str(root / "metrics.prom"),
        "IBEX_DRILL_ENVIRONMENT_CLASS": "test-harness",
        "SKIP_COMPOSE": "1",
        "POSTGRES_DSN": _DSN_FIXTURE,
    }
    env.pop("IBEX_DRILL_MECHANISM", None)
    env.pop("POSTGRES_CONTAINER", None)
    if mechanism is not None:
        env["IBEX_DRILL_MECHANISM"] = mechanism
    return env


def restore_env(request: RestoreRequest) -> dict[str, str]:
    """The environment `pgbackrest-restore.sh` runs a scratch restore under."""
    root = request.root
    bindir = root / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "stub-engine"
    stub.write_text(_ENGINE_STUB, encoding="utf-8")
    stub.chmod(0o755)
    conf = root / "pgbackrest.conf"
    conf.write_text("[global]\nrepo1-type=s3\n", encoding="utf-8")
    compose = root / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env = {
        **os.environ,
        # Fixtures for a throwaway local repository: nothing here reaches a
        # network and no credential is real. Bandit B105 reads the names.
        "PGBACKREST_REPO1_CIPHER_PASS": "fixture-cipher",  # nosec B105
        "PGBACKREST_REPO1_S3_KEY": "fixture-key",
        "PGBACKREST_REPO1_S3_KEY_SECRET": "fixture-secret",  # nosec B105
        "PGBACKREST_CONF": str(conf),
        "PGBACKREST_STANZA": "ibex-main",
        "COMPOSE_FILE": str(compose),
        "IBEX_CONTAINER_CLI": str(stub),
        "PGBACKREST_RESTORE_TARGET": request.target,
        "PGBACKREST_RESTORE_REPORT": str(request.report),
        # A host data directory that does not exist, so the destructive branch
        # refuses deterministically when no scratch volume is given.
        "PGBACKREST_PGDATA": str(root / "no-such-datadir"),
        "STUB_REPLAY_US": str(request.replay_us),
        "STUB_LOG": str(root / "engine.log"),
        # Compose metadata for the profile: what a stopped primary still
        # answers, and the identity a recovery must connect with.
        "STUB_COMPOSE_CONFIG": (
            '{"services": {"postgres": {"environment": '
            '{"POSTGRES_USER": "ibex", "POSTGRES_DB": "ibex"}}}}'
        ),
        "TMPDIR": str(root),
    }
    if request.scratch is None:
        env.pop("PGBACKREST_RESTORE_SCRATCH_VOLUME", None)
    else:
        env["PGBACKREST_RESTORE_SCRATCH_VOLUME"] = request.scratch
    return env


def run_restore(request: RestoreRequest) -> subprocess.CompletedProcess:
    """Drive the shipped restore script through its scratch branch."""
    return run_bash(PITR_RESTORE_SH, restore_env(request))


class DrillMechanismFallbackTests(unittest.TestCase):
    """`--mechanism=pgbackrest` must fail, not degrade into pg_dump."""

    def test_pgbackrest_mechanism_fails_loudly_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = run_bash(DRILL_SH, drill_env(root, mechanism=None), "--mechanism=pgbackrest")
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("refusing to fall back to pg_dump", output)
            self.assertIn("pgbackrest binary is not installed", output)
            # It failed before touching a database: no seeding, no data loss.
            self.assertNotIn("seeding org markers", output)
            written = json.loads((root / "reports" / "restore-drill-report.json").read_text())
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")
            self.assertTrue(written["blocked_by"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertFalse(written["evidence_eligible"])
            self.assertEqual(written["environment_class"], "test-harness")

    def test_env_equivalent_selects_the_same_path(self) -> None:
        # The env form and the flag form must select the same mechanism.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = run_bash(DRILL_SH, drill_env(root, mechanism="pgbackrest"))
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("refusing to fall back to pg_dump", output)
            written = json.loads((root / "reports" / "restore-drill-report.json").read_text())
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")


class PitrRestoreScriptTests(unittest.TestCase):
    """End-to-end cases against the real restore script, with a stubbed engine.

    The report writer is only half of the honesty boundary: the producer decides
    what it observed. These cases drive `pgbackrest-restore.sh` through its
    scratch branch so the comparison, the exit trap and the report write are the
    ones that ship.
    """

    def test_replay_fractionally_before_the_target_passes(self) -> None:
        # The defect: replay .800 against target .900. PostgreSQL rounds the
        # replay epoch to 49 and `date +%s` truncates the target to 48, so the
        # whole-second comparison failed a restore that was correct.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48.900Z",
                    replay_us=utc_micros("2026-11-16T07:42:48.800Z"),
                    report=report,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("recovery target reached", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])
            self.assertEqual(
                written["postgres"]["recovery_replay_timestamp"],
                "2026-11-16T07:42:48.800000Z",
            )
            self.assertTrue(written["postgres"]["restore_ok"])

    def test_replay_fractionally_after_the_target_fails(self) -> None:
        # The other half of the same comparison: rounding must not hide a miss.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48.100Z",
                    replay_us=utc_micros("2026-11-16T07:42:48.900Z"),
                    report=report,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("replayed past the target", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(written["postgres"]["recovery_target_reached"])
            self.assertFalse(written["postgres"]["restore_ok"])
            self.assertTrue(written["blocked_by"])

    def test_unproven_target_fails_a_targeted_restore(self) -> None:
        # psql failing, a malformed row, or replay == -1 leaves the result empty.
        # A targeted restore with an unproven target is not a success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=-1,
                    report=report,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("did not prove the requested target", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertIsNone(written["postgres"]["recovery_target_reached"])
            self.assertFalse(written["postgres"]["restore_ok"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertFalse(written["evidence_eligible"])
            self.assertTrue(written["blocked_by"])

    def test_offline_primary_uses_the_profile_identity(self) -> None:
        # The live primary is stopped — the exact state of a real recovery. The
        # restored cluster is bootstrapped with the profile's `ibex` role, so a
        # verification that connected as `postgres` would fail every query for
        # 120 s and fail a restore that worked.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=utc_micros("2026-11-16T07:42:47Z"),
                    report=report,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            calls = (root / "engine.log").read_text(encoding="utf-8")
            self.assertIn("-U ibex -d ibex", calls)
            self.assertNotIn("-U postgres", calls)
            written = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(written["postgres"]["recovery_target_reached"])

    def test_unexplained_failure_replaces_a_stale_success(self) -> None:
        # A run that dies before any caller records a reason must still leave a
        # report saying why — and must not leave the previous run's success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "pitr-report.json"
            report.write_text(
                # Field names, not credentials: Bandit B105 reads the "_pass"
                # suffix as a password-like literal.
                json.dumps({"evidence_eligible": True, "postgres": {"rpo_pass": True}}),  # nosec B105
                encoding="utf-8",
            )
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=utc_micros("2026-11-16T07:42:47Z"),
                    report=report,
                    scratch=None,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("refused: could not stop Postgres", output)
            written = json.loads(report.read_text(encoding="utf-8"))
            # The stale success is gone: this is the current run's report.
            self.assertFalse(written["evidence_eligible"])
            self.assertFalse(written["postgres"]["rpo_pass"])
            self.assertEqual(written["postgres"]["mechanism"], "unavailable")
            self.assertTrue(written["blocked_by"])
            self.assertIn("exited with status", written["blocked_by"])
            self.assertFalse(written["evidence_eligible"])

    def test_report_write_failure_fails_a_successful_restore(self) -> None:
        # The restore and its verification succeed, then the report cannot be
        # written. A run that cannot produce evidence must not exit zero.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_dir = root / "report-is-a-directory"
            report_dir.mkdir()
            proc = run_restore(
                RestoreRequest(
                    root=root,
                    target="2026-11-16T07:42:48Z",
                    replay_us=utc_micros("2026-11-16T07:42:47Z"),
                    report=report_dir,
                )
            )
            output = proc.stdout + proc.stderr
            self.assertIn("scratch restore ok", output)
            self.assertNotEqual(proc.returncode, 0, output)
            self.assertIn("could not write the PITR report", output)


if __name__ == "__main__":
    unittest.main()
