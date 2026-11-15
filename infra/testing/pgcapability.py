"""Provision capability logins and build their DSNs for integration tests.

The v1 profile connects ``services/api`` and ``services/memory`` on
``ibex_runtime`` and ``services/worker`` on ``ibex_worker``. A wrong *password*
fails loudly when the pool connects, but a wrong *login* starts silently and
re-enables the RLS bypass the tenancy guarantee rests on (the migration owner
``ibex`` is a superuser, and ``FORCE ROW LEVEL SECURITY`` does not cover
superusers). Each service therefore asserts its connection login at startup and
refuses to boot on the owner.

The integration harnesses give themselves two identities:

* the **app under test** connects on the capability login, so startup passes and
  RLS is exercised for real;
* the **test** seeds and asserts as the owner, so fixtures are not blocked by
  RLS (and destructive helpers such as ``TRUNCATE`` stay possible).

The role secrets below must match ``infra/testing/testcreds/creds.go``: roles
and their verifiers are cluster-global, so the Go integration packages and the
Python suites must provision the same values or invalidate each other's
connections.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

RUNTIME_LOGIN = "ibex_runtime"
WORKER_LOGIN = "ibex_worker"

# Capability-login secrets shared with infra/testing/testcreds/creds.go.
CAPABILITY_PASSWORDS: Mapping[str, str] = {
    RUNTIME_LOGIN: "capability-test-only-runtime",
    WORKER_LOGIN: "capability-test-only-worker",
    "ibex_bootstrap": "capability-test-only-bootstrap",
    "ibex_auth": "capability-test-only-auth",
}

_ENV_BY_LOGIN: Mapping[str, str] = {
    RUNTIME_LOGIN: "IBEX_RUNTIME_DB_PASSWORD",
    WORKER_LOGIN: "IBEX_WORKER_DB_PASSWORD",
    "ibex_bootstrap": "IBEX_BOOTSTRAP_DB_PASSWORD",
    "ibex_auth": "IBEX_AUTH_DB_PASSWORD",
}

_PROVISION_TIMEOUT_SECONDS = 300


def capability_dsn(owner_dsn: str, login: str) -> str:
    """Return ``owner_dsn`` with the userinfo replaced by a capability login.

    The scheme, host, port, database and query string are preserved, so a
    ``postgresql+asyncpg://`` URL stays async and ``sslmode`` survives.
    """
    if login not in CAPABILITY_PASSWORDS:
        msg = f"unknown capability login {login!r}"
        raise ValueError(msg)
    parts = urlsplit(owner_dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    password = quote(CAPABILITY_PASSWORDS[login], safe="")
    netloc = f"{login}:{password}@{host}{port}"
    return urlunsplit(parts._replace(netloc=netloc))


def libpq_dsn(dsn: str) -> str:
    """Return a DSN the Go migration CLI (lib/pq) can open.

    The memory harness converts ``POSTGRES_TEST_DSN`` to SQLAlchemy's
    ``postgresql+asyncpg://`` form for the app; the provisioner runs as a Go
    process, so the driver suffix has to come back off.
    """
    for async_scheme, sync_scheme in (
        ("postgresql+asyncpg://", "postgresql://"),
        ("postgres+asyncpg://", "postgres://"),
    ):
        if dsn.startswith(async_scheme):
            return sync_scheme + dsn[len(async_scheme) :]
    return dsn


def _require_go(which: Callable[[str], str | None]) -> str:
    go = which("go")
    if go is None:
        msg = (
            "go is required to provision the capability logins "
            "(migrate provision); install Go or run the Go migration tests first"
        )
        raise RuntimeError(msg)
    return go


def _provision_env(owner_dsn: str) -> dict[str, str]:
    """Environment for ``migrate provision``, pinned to the test database.

    Both names the migration CLI reads are set: an inherited
    ``POSTGRES_MIGRATE_DSN`` would otherwise redirect provisioning away from
    the database the suite is about to use.
    """
    env = dict(os.environ)
    target = libpq_dsn(owner_dsn)
    env["POSTGRES_DSN"] = target
    env["POSTGRES_MIGRATE_DSN"] = target
    for login, env_name in _ENV_BY_LOGIN.items():
        env[env_name] = CAPABILITY_PASSWORDS[login]
    return env


def _run_provision(
    go: str,
    repo_root: Path,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    try:
        runner(
            [go, "run", "./infra/migrations/postgres/cmd/migrate", "-command", "provision"],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=_PROVISION_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"migrate provision failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("migrate provision timed out") from exc


def provision_capability_logins(
    owner_dsn: str,
    repo_root: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Set the capability-login passwords with ``migrate provision``.

    Migration 000064 creates the logins with no password and
    ``CONNECTION LIMIT 0``; ``provision`` sets the verifier and lifts the
    connection limit in one transaction. It is idempotent, so a suite may call
    it once per session even when another suite already provisioned the cluster.

    Raises ``RuntimeError`` with a redacted message on failure; the caller
    decides whether that is a skip or a failure.
    """
    go = _require_go(which)
    _run_provision(go, repo_root, _provision_env(owner_dsn), runner)


__all__ = [
    "CAPABILITY_PASSWORDS",
    "RUNTIME_LOGIN",
    "WORKER_LOGIN",
    "capability_dsn",
    "libpq_dsn",
    "provision_capability_logins",
]
