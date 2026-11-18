#!/usr/bin/env python3
"""Which array the guard reads: a direct initializer that ends at its bracket.

The rows the site renders are the rows of one array, so the guard accepts only a
direct array initializer and only a closing bracket that ends the declaration.
Everything that could hand the page a different array -- a fallback initializer, a
trailing operation, an index or call on the next line, an entry on the
declaration's own line -- is rejected here.
"""

from __future__ import annotations

import unittest

from status_vocabulary import InputError, parse_site_rows


class ArrayBoundaryTests(unittest.TestCase):
    def test_an_initializer_selecting_another_array_is_rejected(self) -> None:
        # The fallback is what a `find('[')` reader compared, while the site renders
        # `publishedRows` whenever it is defined: agreement about an array the page
        # does not use. Only a direct array initializer is accepted.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows: readonly CapabilityRow[] = publishedRows ?? [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("direct array initializer", message)
        self.assertIn("publishedRows", message)

    def test_a_trailing_array_operation_is_rejected(self) -> None:
        # A trailing operation hands the site rows this text does not contain, so the
        # comparison would cover a different array than the page renders. Evaluating
        # it would mean interpreting TypeScript, so the shape is rejected instead.
        for suffix in (".map(row => row)", ".concat(hostedRows)", ".filter(Boolean)",
                       ".flat()", " as const"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(InputError) as caught:
                    parse_site_rows(
                        "const capabilityRows = [\n"
                        "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                        f"]{suffix}\n"
                    )
                message = str(caught.exception)
                self.assertIn("line 3", message)
                self.assertIn("must end at its ']'", message)
        # The same operation on the following line is the same defect.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
                "  .map(row => row)\n"
            )
        self.assertIn(".map", str(caught.exception))

    def test_a_statement_terminator_after_the_array_is_rejected(self) -> None:
        # Only whitespace or a `//` comment may follow the closing bracket. A `;` does
        # not change the rows, but it is a form the guard does not read, and
        # `ledger.ts` is written without statement terminators: it fails naming the
        # line rather than passing as a shape nobody decided on.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "];\n"
            )
        self.assertIn("line 3", str(caught.exception))
        self.assertIn(";", str(caught.exception))

    def test_a_comment_after_the_opening_bracket_is_accepted(self) -> None:
        # Whitespace or a `//` comment may follow the real opening bracket: it holds
        # no entry, and the site's own formatting allows it there.
        self.assertEqual(
            parse_site_rows(
                "const capabilityRows: readonly CapabilityRow[] = [ // the rows rendered\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_bracket_inside_a_trailing_comment_is_not_the_opening_bracket(self) -> None:
        # A check on the line's last character accepted `= oldRows // [`, and the
        # entries below were then read from a bracket that opened nothing the site
        # renders.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows: readonly CapabilityRow[] = oldRows // [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        self.assertIn("direct array initializer", str(caught.exception))

    def test_an_entry_sharing_the_declaration_line_is_rejected(self) -> None:
        # No line reader ever sees an entry on the declaration's line, so it could
        # not be accounted for; the declaration must end at its opening bracket.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows = [['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        self.assertIn("must end at its opening '['", str(caught.exception))

    def test_an_initializer_continuation_after_the_bracket_is_rejected(self) -> None:
        # `]` followed on the next line by `[`, `(`, `.`, `?`, or a template literal is
        # one expression to TypeScript: an index and a call, a call, a method, optional
        # chaining, a tagged template. `['filter'](...)` drops a row the guard still
        # counted, and `?.map(...)` hands the page the mapped rows, so the comparison
        # covered rows the site does not render. `?` joined the set after `?.map` was
        # accepted: every other continuation was rejected, this one was not.
        for continuation in (
            "['filter'](row => row[0])",
            "(rows => rows)",
            ".flat()",
            "?.map(row => row)",
            "`x`",
        ):
            with self.subTest(continuation=continuation):
                with self.assertRaises(InputError) as caught:
                    parse_site_rows(
                        "const capabilityRows = [\n"
                        "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                        "]\n"
                        f"{continuation}\n"
                    )
                self.assertIn("must end at its ']'", str(caught.exception))

    def test_a_statement_after_the_array_is_not_a_continuation(self) -> None:
        # The continuation check must not reject the shape the file actually has: the
        # next statement starts with a keyword, so the array is complete.
        self.assertEqual(
            parse_site_rows(
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
                "export const capabilities = capabilityRows.map(row => row)\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )


if __name__ == "__main__":
    unittest.main()
