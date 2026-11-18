#!/usr/bin/env python3
"""Tests for infra/scripts/check-status-vocabulary.py."""

from __future__ import annotations

import importlib.util
import io
import shutil
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-status-vocabulary.py")
SPEC = importlib.util.spec_from_file_location("check_status_vocabulary", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load check-status-vocabulary.py")
check_status_vocabulary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_status_vocabulary
SPEC.loader.exec_module(check_status_vocabulary)

BASELINE = """
    | Area | Status | Must not be inferred |
    | --- | --- | --- |
    | Auth and proxy foundations | IMPLEMENTED | Hosted HA. |
    | Memory substrate | IMPLEMENTED | Deletion certification. |
"""

ENGINEERING_BASELINE = """
    | Area | Current documented status | What must not be inferred |
    | --- | --- | --- |
    | Auth/proxy foundations | `shipped-local` / profile-dependent | Hosted HA. |
"""

VOCABULARY = """
    | Label | Ledger class | Meaning |
    | --- | --- | --- |
    | IMPLEMENTED | `shipped-local` | Implemented and locally evidenced. |
    | PROVISIONAL | `provisional` | A seam exists; evidence is open. |
"""

SITE_LEDGER = """
export type Status = 'IMPLEMENTED' | 'PROVISIONAL'

export const statusMeta: Record<Status, StatusMeta> = {
  IMPLEMENTED: {
    label: 'Implemented',
    ledgerClass: 'shipped-local',
    description: 'Implemented and locally evidenced.',
  },
  PROVISIONAL: {
    label: 'Provisional',
    ledgerClass: 'provisional',
    description: 'A seam exists; evidence is open.',
  },
}

const capabilityRows: readonly CapabilityRow[] = [
  ['Auth and proxy foundations', 'IMPLEMENTED', 'Detail.', '/docs/security/authentication'],
  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/docs/memory/overview'],
]
"""

CONCEPTS_LIST = """
Status vocabulary in these docs:

- **IMPLEMENTED** — implemented and locally evidenced.
- **PROVISIONAL** — a seam or contract exists.
"""


def baseline(table: str = BASELINE, columns=("Area", "Status")) -> dict[str, str]:
    return check_status_vocabulary.parse_baseline_table(
        textwrap.dedent(table), columns[0], columns[1], "test"
    )


class TableTests(unittest.TestCase):
    def test_rows_are_read_by_header_not_by_position(self) -> None:
        found = baseline()
        self.assertEqual(found["Memory substrate"], "IMPLEMENTED")

    def test_a_section_without_the_table_is_an_input_error(self) -> None:
        with self.assertRaises(check_status_vocabulary.InputError):
            baseline("| Area | Boundary |\n| --- | --- |\n| x | y |\n")

    def test_a_table_whose_second_column_differs_is_not_read(self) -> None:
        # The engineering ledger's column is "Current documented status"; reading
        # it with the site's header would silently match nothing or the wrong
        # table, so the columns are compared, not the position.
        with self.assertRaises(check_status_vocabulary.InputError):
            baseline(ENGINEERING_BASELINE)

    def test_a_row_shorter_than_the_header_is_an_input_error(self) -> None:
        with self.assertRaises(check_status_vocabulary.InputError):
            baseline(
                """
                | Area | Status | Must not be inferred |
                | --- | --- | --- |
                | Memory substrate | IMPLEMENTED |
                """
            )

    def test_a_capability_listed_twice_is_an_input_error(self) -> None:
        # A duplicate would keep whichever row was read last, so a corrected row
        # could sit beside a stale one and pass.
        with self.assertRaises(check_status_vocabulary.InputError) as caught:
            baseline(
                """
                | Area | Status | Must not be inferred |
                | --- | --- | --- |
                | Memory substrate | IMPLEMENTED | a |
                | Memory substrate | PROVISIONAL | b |
                """
            )
        self.assertIn("Memory substrate", str(caught.exception))

    def test_prose_between_tables_does_not_join_them(self) -> None:
        found = baseline(
            """
            | Area | Status | Must not be inferred |
            | --- | --- | --- |
            | Memory substrate | IMPLEMENTED | a |

            Some prose.

            | Area | Status | Must not be inferred |
            | --- | --- | --- |
            | Auth and proxy foundations | PROVISIONAL | b |
            """
        )
        self.assertEqual(found, {"Memory substrate": "IMPLEMENTED"})


class SiteLedgerTests(unittest.TestCase):
    def test_the_declared_labels_are_read_from_the_union(self) -> None:
        self.assertEqual(
            check_status_vocabulary.parse_status_union(SITE_LEDGER),
            ["IMPLEMENTED", "PROVISIONAL"],
        )

    def test_the_label_to_class_map_is_read_from_status_meta(self) -> None:
        self.assertEqual(
            check_status_vocabulary.parse_site_vocabulary(SITE_LEDGER),
            {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
        )

    def test_a_meta_entry_without_a_class_is_an_input_error(self) -> None:
        with self.assertRaises(check_status_vocabulary.InputError):
            check_status_vocabulary.parse_site_vocabulary(
                "export const statusMeta = {\n  IMPLEMENTED: {\n    label: 'x',\n  },\n}\n"
            )

    def test_capability_rows_carry_their_name_and_status(self) -> None:
        self.assertEqual(
            check_status_vocabulary.parse_site_rows(SITE_LEDGER),
            {
                "Auth and proxy foundations": "IMPLEMENTED",
                "Memory substrate": "PROVISIONAL",
            },
        )

    def test_a_row_carrying_a_detail_string_with_a_comma_is_still_read(self) -> None:
        # The detail is the third field; reading the whole tuple as a pair would
        # take the detail for the status.
        found = check_status_vocabulary.parse_site_rows(
            "const capabilityRows = [\n"
            "  ['Memory substrate', 'PROVISIONAL', 'Storage, dedup, and cache.', '/x'],\n"
            "]\n"
        )
        self.assertEqual(found, {"Memory substrate": "PROVISIONAL"})

    def test_an_entry_the_reader_cannot_parse_is_an_input_error_naming_the_row(self) -> None:
        # A skipped entry never reaches compare_rows, so a capability written in a
        # form the matcher does not handle would satisfy the "no unaccounted row"
        # contract without ever being compared against the other surfaces.
        with self.assertRaises(check_status_vocabulary.InputError) as caught:
            check_status_vocabulary.parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
                '  ["New capability", "PROVISIONAL", "Detail.", "/y"],\n'
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 3", message)
        self.assertIn('["New capability", "PROVISIONAL", "Detail.", "/y"]', message)

    def test_a_readable_entry_after_an_unreadable_one_does_not_hide_it(self) -> None:
        # The scan must not read the rows it can and quietly return them: the
        # readable neighbour would then account for its own capability while the
        # unreadable entry went unreported.
        with self.assertRaises(check_status_vocabulary.InputError):
            check_status_vocabulary.parse_site_rows(
                "const capabilityRows = [\n"
                "  ['New capability', 'PROVISIONAL', 'Detail.', '/y'],\n"
                "  ['Memory substrate', \"IMPLEMENTED\", 'Detail.', '/x'],\n"
                "]\n"
            )


class DocsVocabularyTests(unittest.TestCase):
    def test_a_conflicting_duplicate_label_is_an_input_error_naming_the_lines(self) -> None:
        # The table is read into a map, so a duplicate would keep the last class
        # and drop the earlier row from the comparison while both rows stayed
        # visible to a reader: a stale row above the correct one would pass.
        with self.assertRaises(check_status_vocabulary.InputError) as caught:
            check_status_vocabulary.parse_docs_vocabulary(
                textwrap.dedent(
                    """
                    | Label | Ledger class | Meaning |
                    | --- | --- | --- |
                    | IMPLEMENTED | `provisional` | Stale row. |
                    | IMPLEMENTED | `shipped-local` | Correct row. |
                    | PROVISIONAL | `provisional` | A seam exists. |
                    """
                )
            )
        message = str(caught.exception)
        self.assertIn("IMPLEMENTED", message)
        self.assertIn("lines 4 and 5", message)

    def test_a_duplicate_hidden_by_decoration_is_still_an_input_error(self) -> None:
        # The label is compared after the backticks and whitespace a table cell may
        # carry are stripped, so `IMPLEMENTED` and IMPLEMENTED are one label and a
        # decorated duplicate cannot pass as a second entry.
        with self.assertRaises(check_status_vocabulary.InputError) as caught:
            check_status_vocabulary.parse_docs_vocabulary(
                textwrap.dedent(
                    """
                    | Label | Ledger class | Meaning |
                    | --- | --- | --- |
                    | `PROVISIONAL` | `provisional` | A seam exists. |
                    | PROVISIONAL | `shipped-local` | Conflicting. |
                    """
                )
            )
        self.assertIn("PROVISIONAL", str(caught.exception))


class VocabularyTests(unittest.TestCase):
    def test_a_label_missing_from_a_surface_names_the_label_and_the_surface(self) -> None:
        problems = check_status_vocabulary.compare_vocabulary(
            ["IMPLEMENTED", "PROVISIONAL"],
            {"IMPLEMENTED": "shipped-local"},
            {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
            ["IMPLEMENTED", "PROVISIONAL"],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("PROVISIONAL", problems[0])
        self.assertIn("`statusMeta`", problems[0])

    def test_a_class_moved_under_another_label_is_named(self) -> None:
        problems = check_status_vocabulary.compare_vocabulary(
            ["IMPLEMENTED", "PROVISIONAL"],
            {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
            {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "deferred"},
            ["IMPLEMENTED", "PROVISIONAL"],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("PROVISIONAL", problems[0])
        self.assertIn("provisional", problems[0])
        self.assertIn("deferred", problems[0])

    def test_a_label_the_docs_use_but_the_type_does_not_declare_is_named(self) -> None:
        problems = check_status_vocabulary.compare_vocabulary(
            ["IMPLEMENTED"],
            {"IMPLEMENTED": "shipped-local"},
            {"IMPLEMENTED": "shipped-local"},
            ["IMPLEMENTED", "UNKNOWN"],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("UNKNOWN", problems[0])

    def test_agreement_reports_nothing(self) -> None:
        self.assertEqual(
            check_status_vocabulary.compare_vocabulary(
                ["IMPLEMENTED", "PROVISIONAL"],
                {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
                {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
                ["IMPLEMENTED", "PROVISIONAL"],
            ),
            [],
        )


VOCABULARY = {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"}


class StatusCellTests(unittest.TestCase):
    def test_a_ledger_class_cell_is_translated_through_the_vocabulary(self) -> None:
        self.assertEqual(
            check_status_vocabulary.read_status(
                "`shipped-local` / profile-dependent", True, VOCABULARY
            ),
            "IMPLEMENTED",
        )

    def test_the_first_class_token_is_the_row_status(self) -> None:
        # "`provisional`: target ratified; PR gate `shipped-local`" states the row
        # status first and the gate class second.
        self.assertEqual(
            check_status_vocabulary.read_status(
                "`provisional`: target ratified; PR gate `shipped-local`", True, VOCABULARY
            ),
            "PROVISIONAL",
        )

    def test_a_cell_naming_no_known_class_is_unreadable(self) -> None:
        self.assertIsNone(check_status_vocabulary.read_status("target ratified", True, VOCABULARY))

    def test_a_label_cell_loses_its_backticks(self) -> None:
        self.assertEqual(
            check_status_vocabulary.read_status("`PROVISIONAL`", False, VOCABULARY),
            "PROVISIONAL",
        )

    def test_a_label_the_vocabulary_does_not_declare_is_unreadable(self) -> None:
        # A typo or a new label must be a finding, not a value compared against
        # the other surfaces.
        self.assertIsNone(check_status_vocabulary.read_status("DONE", False, VOCABULARY))


class CapabilityTests(unittest.TestCase):
    CLASS_SURFACES = frozenset({"engineering"})

    def rows(self) -> dict[str, dict[str, str]]:
        """Every declared capability, present and in agreement, surface by surface."""
        rows: dict[str, dict[str, str]] = {
            key: {} for key in ("engineering", "docs", "ledger", "mirror")
        }
        for names in check_status_vocabulary.CAPABILITIES.values():
            for surface, name in names.items():
                if name is not None:
                    rows[surface][name] = (
                        "`provisional`" if surface in self.CLASS_SURFACES else "PROVISIONAL"
                    )
        return rows

    def problems(self, engineering: str, docs: str, ledger: str) -> list[str]:
        """The findings when auth-proxy states these three values and all else agrees."""
        rows = self.rows()
        rows["engineering"]["Auth/proxy foundations"] = engineering
        rows["docs"]["Auth and proxy foundations"] = docs
        rows["ledger"]["Auth and proxy foundations"] = ledger
        return check_status_vocabulary.compare_capabilities(rows, VOCABULARY, self.CLASS_SURFACES)

    def test_a_disagreement_names_the_capability_and_every_value(self) -> None:
        problems = self.problems("`shipped-local`", "PROVISIONAL", "PROVISIONAL")
        self.assertEqual(len(problems), 1)
        self.assertIn("auth-proxy", problems[0])
        self.assertIn("engineering says IMPLEMENTED", problems[0])
        self.assertIn("docs says PROVISIONAL", problems[0])
        self.assertIn("ledger says PROVISIONAL", problems[0])

    def test_agreement_reports_nothing(self) -> None:
        self.assertEqual(self.problems("`provisional`", "PROVISIONAL", "PROVISIONAL"), [])

    def test_a_row_a_surface_does_not_have_is_reported_rather_than_skipped(self) -> None:
        rows = self.rows()
        del rows["docs"]["Auth and proxy foundations"]
        problems = check_status_vocabulary.compare_capabilities(
            rows, VOCABULARY, self.CLASS_SURFACES
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("auth-proxy", problems[0])
        self.assertIn("no such row", problems[0])

    def test_a_status_outside_the_vocabulary_is_named(self) -> None:
        problems = self.problems("`provisional`", "DONE", "PROVISIONAL")
        self.assertEqual(len(problems), 1)
        self.assertIn("auth-proxy", problems[0])
        self.assertIn("not a declared status", problems[0])

    def test_a_row_no_capability_declares_is_reported(self) -> None:
        problems = check_status_vocabulary.compare_rows(
            {"ledger": {"Auth and proxy foundations": "IMPLEMENTED", "New capability": "DEFERRED"}}
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("New capability", problems[0])


class RepositoryTests(unittest.TestCase):
    """The guard against this checkout, and against a mutated copy of it."""

    FILES = (
        check_status_vocabulary.ENGINEERING_LEDGER,
        check_status_vocabulary.SITE_LEDGER,
        check_status_vocabulary.DOCS_LEDGER,
        check_status_vocabulary.DOCS_VOCABULARY,
        check_status_vocabulary.DOCS_MIRROR,
    )

    def test_the_repository_agrees(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(check_status_vocabulary.main([]), 0)

    def copy(self, directory: Path) -> Path:
        for relative in self.FILES:
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(check_status_vocabulary.ROOT / relative, target)
        return directory

    def run_against(self, root: Path) -> tuple[int, str]:
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = check_status_vocabulary.main(["--root", str(root)])
        return code, stderr.getvalue()

    def test_a_status_changed_in_one_surface_fails_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            ledger = root / check_status_vocabulary.SITE_LEDGER
            ledger.write_text(
                ledger.read_text(encoding="utf-8").replace(
                    "['Memory substrate', 'IMPLEMENTED'", "['Memory substrate', 'PROVISIONAL'"
                ),
                encoding="utf-8",
            )
            code, stderr = self.run_against(root)
        self.assertEqual(code, 1)
        self.assertIn("capability memory", stderr)
        self.assertIn("ledger says PROVISIONAL", stderr)

    def test_a_label_added_to_one_surface_fails_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            concepts = root / check_status_vocabulary.DOCS_VOCABULARY
            concepts.write_text(
                concepts.read_text(encoding="utf-8").replace(
                    "- **PROVISIONAL**",
                    "- **DRAFT** — not a declared status.\n- **PROVISIONAL**",
                ),
                encoding="utf-8",
            )
            code, stderr = self.run_against(root)
        self.assertEqual(code, 1)
        self.assertIn("DRAFT", stderr)

    def test_a_missing_surface_is_an_input_error_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            (root / check_status_vocabulary.DOCS_LEDGER).unlink()
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn(check_status_vocabulary.DOCS_LEDGER, stderr)

    def test_a_conflicting_stale_vocabulary_row_above_the_correct_one_fails(self) -> None:
        # The row a reader would see first must not be dropped from the comparison
        # merely because a later row states the same label: before the duplicate was
        # rejected, this file passed with the stale class silently discarded.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            docs = root / check_status_vocabulary.DOCS_LEDGER
            docs.write_text(
                docs.read_text(encoding="utf-8").replace(
                    "| IMPLEMENTED | `shipped-local` |",
                    "| IMPLEMENTED | `provisional` | Stale row. |\n| IMPLEMENTED | `shipped-local` |",
                ),
                encoding="utf-8",
            )
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn("IMPLEMENTED", stderr)
        self.assertIn("listed twice", stderr)

    def test_an_unreadable_capability_entry_fails_instead_of_passing_unscanned(self) -> None:
        # The entry is a capability no surface declares, written in a form the reader
        # does not handle. Skipping it left `compare_rows` with nothing to report, so
        # the row passed without ever being checked.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            ledger = root / check_status_vocabulary.SITE_LEDGER
            ledger.write_text(
                ledger.read_text(encoding="utf-8").replace(
                    "  ['Memory substrate', 'IMPLEMENTED'",
                    "  [\"Hosted HA Console\", \"IMPLEMENTED\", 'Detail.', '/x'],\n"
                    "  ['Memory substrate', 'IMPLEMENTED'",
                ),
                encoding="utf-8",
            )
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn("cannot be read", stderr)
        self.assertIn("Hosted HA Console", stderr)


if __name__ == "__main__":
    unittest.main()
