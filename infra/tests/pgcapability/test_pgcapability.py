"""Unit tests for capability-login DSN assembly in infra/testing/pgcapability.py.

A verifier with ``%``, ``@``, ``:`` or ``/`` used to be interpolated raw and
produced a DSN that could not be parsed, so the capability login silently failed
to connect. These tests pin percent-encoding for both the Python helper and its
shell twin.
"""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

INFRA = Path(__file__).resolve().parents[2]
MODULE_PATH = INFRA / "testing" / "pgcapability.py"
SHELL_LIB = INFRA / "scripts" / "lib" / "pgcapability.sh"

spec = importlib.util.spec_from_file_location("ibex_pgcapability", MODULE_PATH)
pgcapability = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pgcapability)

_OWNER_DSN = "postgresql+asyncpg://ibex:ibex@db.example:5432/ibex?sslmode=disable"
_HOSTILE_PASSWORD = "p%a@ss:w/rd"
_LOGIN = "ibex_runtime"


class CapabilityDsnTests(unittest.TestCase):
    def test_fixed_verifier_is_used_by_default(self):
        parts = urlsplit(pgcapability.capability_dsn(_OWNER_DSN, _LOGIN))
        self.assertEqual(unquote(parts.username), _LOGIN)
        self.assertEqual(unquote(parts.password), "capability-test-only-runtime")
        self.assertEqual(parts.hostname, "db.example")
        self.assertEqual(parts.port, 5432)
        self.assertEqual(parts.path, "/ibex")
        self.assertEqual(parts.query, "sslmode=disable")

    def test_special_characters_in_the_password_are_percent_encoded(self):
        dsn = pgcapability.capability_dsn(_OWNER_DSN, _LOGIN, password=_HOSTILE_PASSWORD)
        netloc = dsn.split("://", 1)[1].split("/", 1)[0]
        self.assertIn(f":{quote(_HOSTILE_PASSWORD, safe='')}@", netloc)
        self.assertNotIn(_HOSTILE_PASSWORD, netloc)
        self.assertEqual(unquote(urlsplit(dsn).password), _HOSTILE_PASSWORD)

    def test_special_characters_in_the_login_are_percent_encoded(self):
        dsn = pgcapability.capability_dsn(_OWNER_DSN, "ibex@runtime", password="pw")
        self.assertEqual(unquote(urlsplit(dsn).username), "ibex@runtime")

    def test_unknown_login_without_override_is_rejected(self):
        with self.assertRaises(ValueError):
            pgcapability.capability_dsn(_OWNER_DSN, "ibex_unknown")


class ShellCapabilityDsnTests(unittest.TestCase):
    """The shell twin must encode exactly like the Python helper."""

    def _run(self, password: str) -> str:
        script = (
            'source "$1" >/dev/null 2>&1; '
            'capability_dsn "$2" ibex_runtime "$3"'
        )
        result = subprocess.run(
            ["bash", "-c", script, "_", str(SHELL_LIB), _OWNER_DSN, password],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def test_shell_percent_encodes_the_password(self):
        dsn = self._run(_HOSTILE_PASSWORD)
        self.assertEqual(unquote(urlsplit(dsn).password), _HOSTILE_PASSWORD)

    def test_shell_and_python_agree(self):
        self.assertEqual(
            self._run(_HOSTILE_PASSWORD),
            pgcapability.capability_dsn(_OWNER_DSN, _LOGIN, password=_HOSTILE_PASSWORD),
        )
