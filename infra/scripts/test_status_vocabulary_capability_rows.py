#!/usr/bin/env python3
"""What the array holds: one single-quoted tuple per line, and none skipped.

Every element between the brackets is either compared or rejected. These cases are
the entry rules: a spread, a second entry sharing a line, a tuple the matcher does
not handle, and a duplicate all fail rather than being dropped from the comparison,
while the two shapes that hold no entry -- a blank line and a ``//`` comment --
stay readable. The line terminators belong here too, because they decide which
lines the entries are read from.
"""

from __future__ import annotations

import unittest

from status_vocabulary import InputError, parse_site_rows
from status_vocabulary_fixtures import SITE_LEDGER


class CapabilityRowTests(unittest.TestCase):
    def test_capability_rows_carry_their_name_and_status(self) -> None:
        self.assertEqual(
            parse_site_rows(SITE_LEDGER),
            {
                "Auth and proxy foundations": "IMPLEMENTED",
                "Memory substrate": "PROVISIONAL",
            },
        )

    def test_a_row_carrying_a_detail_string_with_a_comma_is_still_read(self) -> None:
        # The detail is the third field; reading the whole tuple as a pair would
        # take the detail for the status.
        found = parse_site_rows(
            "const capabilityRows = [\n"
            "  ['Memory substrate', 'PROVISIONAL', 'Storage, dedup, and cache.', '/x'],\n"
            "]\n"
        )
        self.assertEqual(found, {"Memory substrate": "PROVISIONAL"})

    def test_an_entry_the_reader_cannot_parse_is_an_input_error_naming_the_row(self) -> None:
        # A skipped entry never reaches compare_rows, so a capability written in a
        # form the matcher does not handle would satisfy the "no unaccounted row"
        # contract without ever being compared against the other surfaces.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
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
        with self.assertRaises(InputError):
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['New capability', 'PROVISIONAL', 'Detail.', '/y'],\n"
                "  ['Memory substrate', \"IMPLEMENTED\", 'Detail.', '/x'],\n"
                "]\n"
            )

    def test_a_spread_element_is_rejected_rather_than_skipped(self) -> None:
        # A spread renders on the site and never reached compare_rows, so the guard
        # reported agreement over a row it had not read. The array it spreads is not
        # in this text, so the element cannot be interpreted: it fails naming the line.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
                "  ...hostedRows,\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 3", message)
        self.assertIn("...hostedRows", message)

    def test_two_entries_sharing_a_line_are_rejected_rather_than_half_read(self) -> None:
        # The line matcher read the first tuple and left the second uncounted, so a
        # capability could sit in the array and never be compared. The whole line is
        # matched, so the unreadable second entry fails the check.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
                "  ['Hosted HA Console', 'PROVISIONAL', 'Detail.', '/y'], "
                "['Graph, A2A', 'DEFERRED', 'Detail.', '/z'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 3", message)
        self.assertIn("Hosted HA Console", message)
        self.assertIn("Graph, A2A", message)

    def test_a_comment_and_a_blank_line_inside_the_array_are_passed_over(self) -> None:
        # The line set is exhaustive, so the two shapes that hold no entry must stay
        # readable: a rejection of trivia would fail the guard on the layout it
        # accepts, and a silent skip is what the other two tests forbid.
        self.assertEqual(
            parse_site_rows(
                "const capabilityRows = [\n"
                "  // Auth is owned by the proxy package.\n"
                "\n"
                "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "IMPLEMENTED"},
        )

    def test_a_non_terminator_does_not_split_a_typescript_line(self) -> None:
        # `str.splitlines` splits on a form feed, a vertical tab, and U+0085, which are
        # whitespace but not line terminators. Splitting there left
        # `['Retired capability', ...]` as its own line, which was parsed as a row --
        # while TypeScript keeps it inside the comment, so nothing renders it.
        for terminator in ("\f", "\v", "\u0085"):
            with self.subTest(terminator=repr(terminator)):
                self.assertEqual(
                    parse_site_rows(
                        "const capabilityRows = [\n"
                        f"  // retired{terminator}"
                        "['Retired capability', 'DEFERRED', 'x', '/y'],\n"
                        "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                        "]\n"
                    ),
                    {"Memory substrate": "PROVISIONAL"},
                )

    def test_a_line_separator_ends_the_comment_and_the_row_is_read(self) -> None:
        # U+2028 LINE SEPARATOR and U+2029 PARAGRAPH SEPARATOR are line terminators in
        # ECMAScript, so the `//` comment ends at one and the tuple after it is live:
        # the page renders it. Treating them as text inside the line kept the tuple in
        # the comment, dropped it, and reported agreement about a row the site renders.
        for terminator in ("\u2028", "\u2029"):
            with self.subTest(terminator=repr(terminator)):
                self.assertEqual(
                    parse_site_rows(
                        "const capabilityRows = [\n"
                        f"  // retired{terminator}"
                        "['Retired capability', 'DEFERRED', 'x', '/y'],\n"
                        "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                        "]\n"
                    ),
                    {"Retired capability": "DEFERRED", "Memory substrate": "PROVISIONAL"},
                )

    def test_a_crlf_ledger_is_read_with_the_same_line_numbers(self) -> None:
        # CRLF is one TypeScript terminator, so it numbers one line: a rejection must
        # name line 3 here, not line 6.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [\r\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\r\n"
                "  ...hostedRows,\r\n"
                "]\r\n"
            )
        self.assertIn("line 3", str(caught.exception))
        self.assertIn("hostedRows", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
