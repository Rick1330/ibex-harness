#!/usr/bin/env python3
"""How a markdown surface is read: pipe tables, the baseline table, the vocabulary.

Every case here is about the reader finding the right table and refusing a row it
cannot place, so the whole module shares one fixture and one `baseline` helper.
"""

from __future__ import annotations

import textwrap
import unittest

from status_vocabulary import (
    InputError,
    parse_baseline_table,
    parse_docs_vocabulary,
)
from status_vocabulary_fixtures import BASELINE, ENGINEERING_BASELINE


def baseline(table: str = BASELINE, columns=("Area", "Status")) -> dict[str, str]:
    return parse_baseline_table(textwrap.dedent(table), columns[0], columns[1], "test")


class TableTests(unittest.TestCase):
    def test_rows_are_read_by_header_not_by_position(self) -> None:
        found = baseline()
        self.assertEqual(found["Memory substrate"], "IMPLEMENTED")

    def test_a_section_without_the_table_is_an_input_error(self) -> None:
        with self.assertRaises(InputError):
            baseline("| Area | Boundary |\n| --- | --- |\n| x | y |\n")

    def test_a_table_whose_second_column_differs_is_not_read(self) -> None:
        # The engineering ledger's column is "Current documented status"; reading
        # it with the site's header would silently match nothing or the wrong
        # table, so the columns are compared, not the position.
        with self.assertRaises(InputError):
            baseline(ENGINEERING_BASELINE)

    def test_a_row_shorter_than_the_header_is_an_input_error(self) -> None:
        with self.assertRaises(InputError):
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
        with self.assertRaises(InputError) as caught:
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


class DocsVocabularyTests(unittest.TestCase):
    def test_a_conflicting_duplicate_label_is_an_input_error_naming_the_lines(self) -> None:
        # The table is read into a map, so a duplicate would keep the last class
        # and drop the earlier row from the comparison while both rows stayed
        # visible to a reader: a stale row above the correct one would pass.
        with self.assertRaises(InputError) as caught:
            parse_docs_vocabulary(
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
        with self.assertRaises(InputError) as caught:
            parse_docs_vocabulary(
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


if __name__ == "__main__":
    unittest.main()
