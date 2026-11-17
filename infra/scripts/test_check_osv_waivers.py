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
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_a_bare_date_is_kept_as_a_date(self) -> None:
        # Not datetime: datetime subclasses date, and a stored datetime breaks the
        # date-only comparison the expiry check performs.
        found = waivers(
            """
            [[IgnoredVulns]]
            id = "GHSA-aaaa-bbbb-cccc"
            ignoreUntil = 2027-03-01
            reason = "bare"
            """
        )
        self.assertEqual(found[0].expires, datetime.date(2027, 3, 1))
        self.assertIs(type(found[0].expires), datetime.date)

    def test_a_midnight_datetime_is_refused(self) -> None:
        # `2027-03-01T00:00:00Z` parses to datetime.datetime, which isinstance
        # reads as a date; truncating it would record a value the operator did
        # not write, so it is refused with the expected form.
        with self.assertRaises(check_osv_waivers.InputError) as caught:
            waivers(
                """
                [[IgnoredVulns]]
                id = "GHSA-aaaa-bbbb-cccc"
                ignoreUntil = 2027-03-01T00:00:00Z
                reason = "midnight datetime"
                """
            )
        message = str(caught.exception)
        self.assertIn("GHSA-aaaa-bbbb-cccc", message)
        self.assertIn("YYYY-MM-DD", message)

    def test_a_datetime_with_a_time_component_is_refused(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError) as caught:
            waivers(
                """
                [[IgnoredVulns]]
                id = "GHSA-aaaa-bbbb-cccc"
                ignoreUntil = 2027-03-01T12:30:00Z
                reason = "datetime with a time"
                """
            )
        self.assertIn("GHSA-aaaa-bbbb-cccc", str(caught.exception))

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

    def test_an_emptied_ignored_vulns_array_is_valid(self) -> None:
        # The fully-remediated state keeps the key and empties the array; reading
        # it as a broken document would fail the gate on the one state the
        # renewal procedure asks for.
        self.assertEqual(waivers("IgnoredVulns = []\n"), [])

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

    def test_an_empty_table_with_a_header_is_valid(self) -> None:
        # Every waiver removed leaves the header and the separator behind. That
        # is a complete record, not a parse failure.
        self.assertEqual(
            rows(
                """
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Severity | Reachability | Disposition | Expires |
                | --- | --- | --- | --- | --- | --- |
                """
            ),
            [],
        )

    def test_a_section_without_a_header_row_is_an_input_error(self) -> None:
        # The section exists but carries no table, so there is no column
        # position to read. This must stay distinct from an empty table.
        with self.assertRaises(check_osv_waivers.InputError):
            rows(
                """
                ### 9.0.1a Active SCA waivers

                No waivers are recorded in a table any more.
                """
            )

    def test_a_reordered_expiry_column_is_read_by_name(self) -> None:
        # Reading the last cell made a correct row fail once `Expires` moved
        # earlier: the date was there and the parser looked past it.
        found = rows(
            """
            ### 9.0.1a Active SCA waivers

            | Advisory | Expires | Package |
            | --- | --- | --- |
            | GHSA-aaaa-bbbb-cccc | 2027-03-01 | `a` |
            """
        )
        self.assertEqual(found[0].expires, datetime.date(2027, 3, 1))

    def test_a_row_shorter_than_the_expiry_column_is_an_input_error(self) -> None:
        with self.assertRaises(check_osv_waivers.InputError):
            rows(
                """
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Expires |
                | --- | --- | --- |
                | GHSA-aaaa-bbbb-cccc | `a` |
                """
            )

    def test_duplicate_rows_for_one_advisory_are_refused(self) -> None:
        # setdefault kept the first row and dropped the second, so a matching
        # first row hid a stale renewal.
        with self.assertRaises(check_osv_waivers.InputError) as caught:
            rows(
                """
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Expires |
                | --- | --- | --- |
                | GHSA-aaaa-bbbb-cccc | `a` | 2027-03-01 |
                | GHSA-aaaa-bbbb-cccc | `a` | 2026-01-01 |
                """
            )
        self.assertIn("GHSA-AAAA-BBBB-CCCC", str(caught.exception))
        self.assertIn("already has a waiver row", str(caught.exception))

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
        with (
            # The fixtures live in a scratch tree, so that tree is the checkout
            # for the containment rule; the real repository is not written to.
            patch.object(check_osv_waivers, "REPO_ROOT", Path(self._tmp.name)),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
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

    def test_a_datetime_waiver_exits_two(self) -> None:
        # Before the type check was tightened this reached check_expiry and raised
        # TypeError, so the gate crashed instead of reporting an input error.
        self._write(
            TOML_IN_AGREEMENT.replace(
                "ignoreUntil = 2027-03-01", "ignoreUntil = 2027-03-01T00:00:00Z"
            )
        )
        code, _, err = self._run("--today", "2026-11-17")
        self.assertEqual(code, 2, err)
        self.assertIn("expected a bare date (YYYY-MM-DD)", err)

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

    def test_a_fully_remediated_record_exits_zero(self) -> None:
        # The state the renewal procedure asks for: no waiver in the TOML and no
        # row in the table. It must pass, or removing the last waiver turns the
        # gate into the outage it exists to prevent.
        self._write(
            toml="IgnoredVulns = []\n",
            table="""
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Severity | Reachability | Disposition | Expires |
                | --- | --- | --- | --- | --- | --- |
                """,
        )
        code, out, err = self._run("--today", "2026-11-17")
        self.assertEqual(code, 0, err)
        self.assertIn("every expiry is beyond the window", out)

    def test_a_duplicate_row_exits_two(self) -> None:
        self._write(
            table="""
                ### 9.0.1a Active SCA waivers

                | Advisory | Package | Expires |
                | --- | --- | --- |
                | GHSA-aaaa-bbbb-cccc | `a` | 2027-03-01 |
                | GHSA-aaaa-bbbb-cccc | `a` | 2027-03-01 |
                """,
        )
        code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("already has a waiver row", err)

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

    def test_a_path_outside_the_checkout_is_refused(self) -> None:
        # The containment rule is what stops a CLI argument from reading an
        # arbitrary file; validate-release-manifest.py applies the same one.
        self._write()
        with tempfile.TemporaryDirectory() as outside:
            code, _, err = self._run("--table", str(Path(outside) / "DEPENDENCIES.md"))
        self.assertEqual(code, 2, err)
        self.assertIn("must resolve inside", err)

    def test_the_default_date_is_the_utc_date(self) -> None:
        # A date-based gate read from local time fires a day early or a day late
        # depending on the runner, so the default must come from UTC. The stub
        # clock records the timezone it is asked for, which is the claim; the
        # wide window makes the report print the date it actually used.
        self._write()
        fixed = datetime.datetime(2026, 11, 17, 23, 30, tzinfo=datetime.UTC)
        asked: list[datetime.tzinfo] = []

        class _Clock:
            # A class, not an instance: the script type-checks `ignoreUntil`
            # against `datetime.datetime`, and `isinstance(value, instance)`
            # raises TypeError.
            @staticmethod
            def now(tz: datetime.tzinfo) -> datetime.datetime:
                asked.append(tz)
                return fixed

        with patch.object(
            check_osv_waivers,
            "datetime",
            SimpleNamespace(datetime=_Clock, date=datetime.date, UTC=datetime.UTC),
        ):
            code, _, err = self._run("--lead-days", "200")

        self.assertEqual(code, 1)
        self.assertEqual(asked, [datetime.UTC])
        self.assertIn("(2026-11-17)", err)

    def test_the_today_override_agrees_with_the_default(self) -> None:
        # `--today` must stay the same type and meaning as the default, or the
        # window would be computed from two different kinds of value.
        parsed = check_osv_waivers._parse_args(["--today", "2026-11-17"]).today
        self.assertIs(type(parsed), datetime.date)
        self._write()
        code, _, err = self._run("--today", "2026-11-17", "--lead-days", "200")
        self.assertEqual(code, 1)
        self.assertIn("(2026-11-17)", err)


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
