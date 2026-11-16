#!/usr/bin/env python3
"""Tests for infra/scripts/check-osv-waiver-floor.py."""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-osv-waiver-floor.py")
SPEC = importlib.util.spec_from_file_location("check_osv_waiver_floor", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load check-osv-waiver-floor.py")
check_osv_waiver_floor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_osv_waiver_floor
SPEC.loader.exec_module(check_osv_waiver_floor)

# A lock shaped like pnpm 9: importer ranges, package records, and snapshot
# records with peer suffixes. `nuxt` resolves 4.6.4 in both sections.
LOCK_AT_FLOOR = """
    lockfileVersion: '9.0'

    importers:

      .:
        dependencies:
          nuxt:
            specifier: ^4.6.4
            version: 4.6.4

    packages:

      '@nuxt/nitro-server@4.6.4':
        resolution: {integrity: sha512-x}

      nuxt@4.6.4:
        resolution: {integrity: sha512-y}

    snapshots:

      '@nuxt/nitro-server@4.6.4(tnwh27lbj7gh4dedmnyo7k537e)':
        dependencies:
          nuxt: 4.6.4

      nuxt@4.6.4(@babel/core@7.29.7):
        dependencies:
          '@nuxt/nitro-server': 4.6.4
"""


def resolutions(lock: str) -> dict[str, set[str]]:
    return check_osv_waiver_floor.lock_resolutions(textwrap.dedent(lock))


class LockResolutionsTests(unittest.TestCase):
    def test_a_peer_suffixed_record_key_yields_its_version(self) -> None:
        found = resolutions(LOCK_AT_FLOOR)
        self.assertEqual(found["nuxt"], {"4.6.4"})
        self.assertEqual(found["@nuxt/nitro-server"], {"4.6.4"})

    def test_a_snapshot_key_with_scoped_peers_is_read_as_its_own_version(self) -> None:
        # The peer suffix carries `@` of its own, so splitting at the last `@`
        # of the whole key would read the peer's version. This fixture has no
        # `packages:` record to fall back on: the snapshot key is the only
        # evidence of what is installed.
        lock = """
            snapshots:

              nuxt@3.25.0(@babel/core@7.29.7)(@types/node@26.4.1):
                dependencies: {}

              '@nuxt/nitro-server@4.6.4(tnwh27lbj7gh4dedmnyo7k537e)':
                dependencies: {}
        """
        found = resolutions(lock)
        self.assertEqual(found["nuxt"], {"3.25.0"})
        self.assertEqual(found["@nuxt/nitro-server"], {"4.6.4"})

    def test_a_range_is_not_a_resolution(self) -> None:
        # `nuxt: ^4.6.4` is what the importer asked for. Treating it as a
        # resolution would compare a range against a floor.
        lock = """
            importers:

              .:
                dependencies:
                  nuxt:
                    specifier: ^4.6.4
                    version: 4.6.4
                  '@nuxt/nitro-server': ^3.25.0

            packages:

              nuxt@4.6.4:
                resolution: {integrity: sha512-y}
        """
        self.assertEqual(resolutions(lock), {"nuxt": {"4.6.4"}})

    def test_a_quoted_scoped_record_key_parses(self) -> None:
        lock = """
            packages:

              '@nuxt/nitro-server@4.6.4':
                resolution: {integrity: sha512-x}
        """
        self.assertEqual(resolutions(lock)["@nuxt/nitro-server"], {"4.6.4"})

    def test_a_non_version_resolution_is_skipped(self) -> None:
        lock = """
            packages:

              left-pad@file:../left-pad:
                resolution: {directory: ../left-pad, type: directory}
        """
        self.assertEqual(resolutions(lock), {})

    def test_several_resolutions_of_one_package_are_all_kept(self) -> None:
        lock = """
            packages:

              nuxt@3.25.0:
                resolution: {integrity: sha512-a}

            snapshots:

              nuxt@4.6.4:
                dependencies: {}
        """
        self.assertEqual(resolutions(lock)["nuxt"], {"3.25.0", "4.6.4"})


class VersionKeyTests(unittest.TestCase):
    def test_a_prerelease_sorts_below_its_release(self) -> None:
        key = check_osv_waiver_floor.version_key
        self.assertLess(key("4.6.4-rc.1"), key("4.6.4"))
        self.assertLess(key("4.6.4"), key("4.6.5"))

    def test_a_non_version_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            check_osv_waiver_floor.version_key("^4.6.4")


class CheckTests(unittest.TestCase):
    def test_every_package_at_its_floor_passes(self) -> None:
        notes, problems = check_osv_waiver_floor.check(resolutions(LOCK_AT_FLOOR))
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 2)

    def test_a_version_below_the_floor_names_the_package_version_floor_and_waiver(
        self,
    ) -> None:
        lock = LOCK_AT_FLOOR.replace("nuxt@4.6.4:", "nuxt@3.25.0:")
        _, problems = check_osv_waiver_floor.check(resolutions(lock))
        self.assertEqual(len(problems), 1)
        for fragment in ("nuxt", "3.25.0", "4.6.4", "GHSA-f3x9-2chm-73c8"):
            self.assertIn(fragment, problems[0])

    def test_a_snapshot_only_below_floor_resolution_still_fails(self) -> None:
        # Regression: a scoped peer suffix (`(@babel/core@7.29.7)`) made the
        # parser split at the peer's `@`, drop the record, and pass a 3.x lock.
        lock = """
            packages:

              '@nuxt/nitro-server@4.6.4':
                resolution: {integrity: sha512-c}

            snapshots:

              nuxt@3.25.0(@babel/core@7.29.7):
                dependencies: {}
        """
        _, problems = check_osv_waiver_floor.check(resolutions(lock))
        self.assertEqual(len(problems), 1)
        self.assertIn("nuxt 3.25.0", problems[0])

    def test_the_two_packages_are_checked_independently(self) -> None:
        # Only nuxt drops; @nuxt/nitro-server still resolves at the floor. The
        # passing package must not mask the failing one, or vice versa.
        nuxt_below = LOCK_AT_FLOOR.replace("nuxt@4.6.4:", "nuxt@3.25.0:")
        _, problems = check_osv_waiver_floor.check(resolutions(nuxt_below))
        self.assertEqual(len(problems), 1)
        self.assertIn("nuxt 3.25.0", problems[0])

        nitro_below = LOCK_AT_FLOOR.replace(
            "'@nuxt/nitro-server@4.6.4':", "'@nuxt/nitro-server@3.20.0':"
        )
        _, problems = check_osv_waiver_floor.check(resolutions(nitro_below))
        self.assertEqual(len(problems), 1)
        self.assertIn("@nuxt/nitro-server 3.20.0", problems[0])
        self.assertIn("GHSA-hf59-9xwc-2g4p", problems[0])

    def test_one_affected_resolution_fails_even_when_another_is_at_the_floor(
        self,
    ) -> None:
        lock = """
            packages:

              nuxt@3.25.0:
                resolution: {integrity: sha512-a}

              nuxt@4.6.4:
                resolution: {integrity: sha512-b}

              '@nuxt/nitro-server@4.6.4':
                resolution: {integrity: sha512-c}
        """
        _, problems = check_osv_waiver_floor.check(resolutions(lock))
        self.assertEqual(len(problems), 1)
        self.assertIn("nuxt 3.25.0", problems[0])

    def test_an_absent_package_passes_with_a_note(self) -> None:
        lock = """
            packages:

              nuxt@4.6.4:
                resolution: {integrity: sha512-y}
        """
        notes, problems = check_osv_waiver_floor.check(resolutions(lock))
        self.assertEqual(problems, [])
        self.assertTrue(
            any("@nuxt/nitro-server" in note and "absent" in note for note in notes),
            notes,
        )


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "pnpm-lock.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check_osv_waiver_floor.main(["--lockfile", str(self.path)])
        return code, out.getvalue(), err.getvalue()

    def test_the_gate_exits_zero_at_the_floor(self) -> None:
        self.path.write_text(textwrap.dedent(LOCK_AT_FLOOR), encoding="utf-8")
        code, out, err = self._run()
        self.assertEqual(code, 0, err)
        self.assertIn("every waived package resolves at or above", out)

    def test_the_gate_exits_one_below_the_floor(self) -> None:
        self.path.write_text(
            textwrap.dedent(LOCK_AT_FLOOR).replace("nuxt@4.6.4:", "nuxt@3.25.0:"),
            encoding="utf-8",
        )
        code, _, err = self._run()
        self.assertEqual(code, 1)
        self.assertIn("nuxt 3.25.0", err)
        self.assertIn("4.6.4 floor", err)

    def test_a_missing_lockfile_exits_two(self) -> None:
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_a_lockfile_with_no_records_exits_two(self) -> None:
        # Fail closed: a format change must not look like "nothing to waive".
        self.path.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("no package resolutions found", err)

    def test_an_unsupported_lockfile_version_exits_two(self) -> None:
        # A new record layout the parser has not been taught must fail loudly,
        # not read nothing and report a pass.
        self.path.write_text(
            textwrap.dedent(LOCK_AT_FLOOR).replace(
                "lockfileVersion: '9.0'", "lockfileVersion: '8.0'"
            ),
            encoding="utf-8",
        )
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("unsupported lockfileVersion 8", err)


if __name__ == "__main__":
    unittest.main()
