#!/usr/bin/env python3
"""Tests for infra/scripts/check-osv-waivers.py."""

from __future__ import annotations

import datetime
import importlib.util
import io
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-osv-waivers.py")
SPEC = importlib.util.spec_from_file_location("check_osv_waivers", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load check-osv-waivers.py")
check_osv_waivers = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_osv_waivers
SPEC.loader.exec_module(check_osv_waivers)

TODAY = datetime.date(2026, 11, 17)

# A policy and a table that agree. `GHSA-aaaa-bbbb-cccc` expires inside the
# 21-day window, so the expiry tests use a later `today` to keep it out of the
# way; `GHSA-dddd-eeee-ffff` is the far one.
TOML_IN_AGREEMENT = """
    [[IgnoredVulns]]
    id = "GHSA-aaaa-bbbb-cccc"
    ignoreUntil = 2027-03-01
    reason = "first"

    [[IgnoredVulns]]
    id = "GHSA-dddd-eeee-ffff"
    ignoreUntil = 2027-06-01
    reason = "second"

    [[IgnoredVulns]]
    id = "GHSA-dddd-eeee-0000"
    ignoreUntil = 2027-06-01
    reason = "second package, same advisory family"
"""

TABLE_IN_AGREEMENT = """
    ### 9.0.1a Active SCA waivers

    Some prose that names GHSA-9999-9999-9999 and must not be read as a waiver.

    | Advisory | Package | Severity | Reachability | Disposition | Expires |
    | --- | --- | --- | --- | --- | --- |
    | GHSA-aaaa-bbbb-cccc (first) | `a` | Low | Build only | reason | 2027-03-01 |
    | GHSA-dddd-eeee-ffff, GHSA-dddd-eeee-0000 (second) | `b`, `c` | Low | Build only | reason | 2027-06-01 |

    ### 9.0.2 Later section

    | GHSA-7777-7777-7777 | not a waiver row | 2027-01-01 |
"""


def waivers(toml: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "osv-scanner.toml"
        path.write_text(textwrap.dedent(toml), encoding="utf-8")
        return check_osv_waivers.load_toml_waivers(path)


def rows(table: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "DEPENDENCIES.md"
        path.write_text(textwrap.dedent(table), encoding="utf-8")
        return check_osv_waivers.parse_table(path)


class TomlWaiverTests(unittest.TestCase):
    def test_every_entry_yields_its_id_and_date(self) -> None:
        found = waivers(TOML_IN_AGREEMENT)
        self.assertEqual(
            [(waiver.advisory, waiver.expires) for waiver in found],
            [
                ("GHSA-AAAA-BBBB-CCCC", datetime.date(2027, 3, 1)),
                ("GHSA-DDDD-EEEE-FFFF", datetime.date(2027, 6, 1)),
                ("GHSA-DDDD-EEEE-0000", datetime.date(2027, 6, 1)),
            ],
        )

    def test_an_unquoted_date_is_read_as_a_date(self) -> None:
        # TOML bare dates parse to datetime.date; a quoted one parses to str and
        # would silently make the entry permanent, so it is refused.
        with self.assertRaises(check_osv_waivers.InputError):
            waivers(
                """
                [[IgnoredVulns]]
                id = "GHSA-aaaa-bbbb-cccc"
                ignoreUntil = "2027-03-01"
                reason = "quoted"
                """
            )

    def test_an_entry_without_an_id_is_refused(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError):
            waivers(
                """
                [[IgnoredVulns]]
                ignoreUntil = 2027-03-01
                """
            )

    def test_no_entries_is_an_empty_list(self) -> None:
        self.assertEqual(waivers("# nothing ignored here\n"), [])

    def test_unparseable_toml_is_an_input_error(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError):
            waivers("[[IgnoredVulns]\nid = 1\n")


class TableTests(unittest.TestCase):
    def test_rows_carry_every_id_and_the_recorded_date(self) -> None:
        found = rows(TABLE_IN_AGREEMENT)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].advisories, ("GHSA-AAAA-BBBB-CCCC",))
        self.assertEqual(found[0].expires, datetime.date(2027, 3, 1))
        self.assertEqual(
            found[1].advisories, ("GHSA-DDDD-EEEE-FFFF", "GHSA-DDDD-EEEE-0000")
        )

    def test_prose_and_later_sections_are_not_read_as_waivers(self) -> None:
        # The prose names a GHSA id and a later section holds another table; a
        # parser that scanned the whole file would report both as waivers.
        found = rows(TABLE_IN_AGREEMENT)
        ids = {advisory for row in found for advisory in row.advisories}
        self.assertNotIn("GHSA-9999-9999-9999", ids)
        self.assertNotIn("GHSA-7777-7777-7777", ids)

    def test_a_missing_section_is_an_input_error(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError):
            rows("## Dependencies\n\nno waiver table here\n")

    def test_a_table_without_the_expiry_column_is_an_input_error(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError):
            rows(
                """
                ### 9.0.1a Active SCA waivers

                | Advisory | Package |
                | --- | --- |
                | GHSA-aaaa-bbbb-cccc | `a` |
                """
            )

    def test_a_row_naming_no_advisory_is_an_input_error(self) -> None:
        # A renamed column would land a package name where the advisory goes,
        # and reading on would compare the wrong column.
        with self.assertRaises(check_osv_waivers.InputError):
            rows(
                """
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Expires |
                | --- | --- | --- |
                | not-an-id | `a` | 2027-03-01 |
                """
            )

    def test_a_non_iso_expiry_is_kept_as_none(self) -> None:
        found = rows(
            """
            ### 9.0.1a Active SCA waivers

            | Advisory | Package | Expires |
            | --- | --- | --- |
            | GHSA-aaaa-bbbb-cccc | `a` | TBD |
            """
        )
        self.assertIsNone(found[0].expires)


class ParityTests(unittest.TestCase):
    def test_matching_sets_pass(self) -> None:
        notes, problems = check_osv_waivers.check_parity(
            waivers(TOML_IN_AGREEMENT), rows(TABLE_IN_AGREEMENT)
        )
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 1)

    def test_an_id_only_in_the_toml_names_the_missing_row(self) -> None:
        # The whole row is dropped, not blanked: a blank row is a different
        # defect (no advisory at all) and the parser refuses it.
        table = "\n".join(
            line
            for line in TABLE_IN_AGREEMENT.splitlines()
            if "GHSA-dddd-eeee-ffff" not in line
        )
        _, problems = check_osv_waivers.check_parity(waivers(TOML_IN_AGREEMENT), rows(table))
        self.assertEqual(len(problems), 2, problems)
        joined = " ".join(problems)
        for fragment in ("GHSA-DDDD-EEEE-FFFF", "GHSA-DDDD-EEEE-0000", "no row"):
            self.assertIn(fragment, joined)

    def test_an_id_only_in_the_table_names_its_line(self) -> None:
        toml = """
            [[IgnoredVulns]]
            id = "GHSA-aaaa-bbbb-cccc"
            ignoreUntil = 2027-03-01
        """
        _, problems = check_osv_waivers.check_parity(waivers(toml), rows(TABLE_IN_AGREEMENT))
        self.assertEqual(len(problems), 2, problems)
        joined = " ".join(problems)
        for fragment in ("GHSA-DDDD-EEEE-FFFF", "no longer ignored", "DEPENDENCIES.md:"):
            self.assertIn(fragment, joined)


class ExpiryTests(unittest.TestCase):
    def test_a_waiver_beyond_the_window_is_a_note(self) -> None:
        notes, problems = check_osv_waivers.check_expiry(
            waivers(TOML_IN_AGREEMENT), datetime.date(2026, 11, 17)
        )
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 3)


    def test_a_waiver_inside_the_window_names_the_advisory_and_date(self) -> None:
        _, problems = check_osv_waivers.check_expiry(
            waivers(TOML_IN_AGREEMENT), datetime.date(2027, 2, 20)
        )
        self.assertEqual(len(problems), 1)
        for fragment in ("GHSA-AAAA-BBBB-CCCC", "2027-03-01", "9 days"):
            self.assertIn(fragment, problems[0])

    def test_the_window_boundary_is_inclusive(self) -> None:
        # Exactly 21 days out is inside the window: the alarm must fire on the
        # lead day, not the day after it.
        _, problems = check_osv_waivers.check_expiry(
            waivers(TOML_IN_AGREEMENT),
            datetime.date(2027, 3, 1) - datetime.timedelta(days=21),
        )
        self.assertEqual(len(problems), 1)

    def test_a_passed_deadline_is_reported_as_expired(self) -> None:
        _, problems = check_osv_waivers.check_expiry(
            waivers(TOML_IN_AGREEMENT), datetime.date(2027, 3, 5)
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("expired on 2027-03-01", problems[0])


class RecordedDateTests(unittest.TestCase):
    def test_matching_dates_pass(self) -> None:
        notes, problems = check_osv_waivers.check_recorded_dates(
            waivers(TOML_IN_AGREEMENT), rows(TABLE_IN_AGREEMENT)
        )
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 1)

    def test_a_renewed_toml_and_a_stale_table_fail(self) -> None:
        toml = TOML_IN_AGREEMENT.replace("2027-03-01", "2027-09-01")
        _, problems = check_osv_waivers.check_recorded_dates(
            waivers(toml), rows(TABLE_IN_AGREEMENT)
        )
        self.assertEqual(len(problems), 1)
        for fragment in ("GHSA-AAAA-BBBB-CCCC", "2027-03-01", "2027-09-01"):
            self.assertIn(fragment, problems[0])


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "osv-scanner.toml"
        self.table = Path(self._tmp.name) / "DEPENDENCIES.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check_osv_waivers.main(
                [
                    "--config",
                    str(self.config),
                    "--table",
                    str(self.table),
                    *extra,
                ]
            )
        return code, out.getvalue(), err.getvalue()

    def _write(self, toml: str = TOML_IN_AGREEMENT, table: str = TABLE_IN_AGREEMENT) -> None:
        self.config.write_text(textwrap.dedent(toml), encoding="utf-8")
        self.table.write_text(textwrap.dedent(table), encoding="utf-8")

    def test_a_clean_record_exits_zero(self) -> None:
        self._write()
        code, out, err = self._run("--today", "2026-11-17")
        self.assertEqual(code, 0, err)
        self.assertIn("every expiry is beyond the window", out)

    def test_a_missing_row_exits_one_and_prints_the_renewal_path(self) -> None:
        self._write(
            table="\n".join(
                line
                for line in TABLE_IN_AGREEMENT.splitlines()
                if "GHSA-dddd-eeee-ffff" not in line
            )
        )
        code, _, err = self._run("--today", "2026-11-17")
        self.assertEqual(code, 1)
        self.assertIn("GHSA-DDDD-EEEE-FFFF", err)
        self.assertIn("renewed by editing, not by code", err)
        self.assertIn("osv-scanner.toml", err)

    def test_a_waiver_inside_the_window_exits_one(self) -> None:
        self._write()
        code, _, err = self._run("--today", "2027-02-20")
        self.assertEqual(code, 1)
        self.assertIn("GHSA-AAAA-BBBB-CCCC", err)
        self.assertIn("2027-03-01", err)

    def test_a_missing_config_exits_two(self) -> None:
        self.table.write_text(textwrap.dedent(TABLE_IN_AGREEMENT), encoding="utf-8")
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_a_missing_table_section_exits_two(self) -> None:
        self._write(table="## Dependencies\n")
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("no '### 9.0.1a", err)


class RepositoryRecordTests(unittest.TestCase):
    """The committed policy and table must satisfy the checks, not only fixtures."""

    def test_the_committed_waiver_record_is_consistent(self) -> None:
        config = check_osv_waivers.DEFAULT_CONFIG
        table = check_osv_waivers.DEFAULT_TABLE
        found = check_osv_waivers.load_toml_waivers(config)
        recorded = check_osv_waivers.parse_table(table)
        _, parity_problems = check_osv_waivers.check_parity(found, recorded)
        _, date_problems = check_osv_waivers.check_recorded_dates(found, recorded)
        self.assertEqual(parity_problems, [])
        self.assertEqual(date_problems, [])


if __name__ == "__main__":
    unittest.main()
