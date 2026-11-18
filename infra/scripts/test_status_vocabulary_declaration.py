#!/usr/bin/env python3
"""Which declaration of ``capabilityRows`` is the one the site exports.

The name can appear in a comment, in a longer identifier, in a string, in a
template, or inside a function body, and only the module-level declaration is the
array the export reads. Every case here is the lexer's answer to that question, or
a rejection when the text cannot be placed at all.
"""

from __future__ import annotations

import unittest

from status_vocabulary import InputError, parse_site_rows


class DeclarationTests(unittest.TestCase):
    def test_the_declaration_is_found_at_statement_position_not_in_a_comment(self) -> None:
        # Searching for the name alone returned its first occurrence, which can sit
        # inside a comment: a commented-out copy of the array above the real one was
        # then the array compared, so the guard read a row the site does not render
        # -- here a stale IMPLEMENTED where the live array states PROVISIONAL.
        commented = (
            "/* capabilityRows used to be:\n"
            "const capabilityRows = [\n"
            "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
            "]\n"
            "*/\n"
        )
        self.assertEqual(
            parse_site_rows(
                commented
                + "const capabilityRows: readonly CapabilityRow[] = [\n"
                + "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                + "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_comment_line_naming_the_declaration_is_not_the_declaration(self) -> None:
        # A `//` mention is not a declaration, so the file holds no array the guard
        # can read: it fails rather than reads the comment's rows as the site's.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "// moved here from: const capabilityRows = [\n"
                "  ['Memory substrate', 'IMPLEMENTED', 'Detail.', '/x'],\n"
                "]\n"
            )
        self.assertIn("no `capabilityRows` array", str(caught.exception))

    def test_an_exported_declaration_is_read(self) -> None:
        # The declaration is matched with or without `export`, because the rows may
        # be exported: the shape is the statement, not the modifier.
        self.assertEqual(
            parse_site_rows(
                "export const capabilityRows: readonly CapabilityRow[] = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_longer_identifier_beginning_with_the_name_is_not_the_declaration(self) -> None:
        # `\b` matched between `s` and `$`, so `capabilityRows$archive` was accepted as
        # the declaration and its rows were compared while the export read the real
        # binding below. An ECMAScript identifier continues with `$`, `_`, a letter, or
        # a digit, so the name must be followed by none of them.
        self.assertEqual(
            parse_site_rows(
                "const capabilityRows$archive = [\n"
                "  ['Memory substrate', 'DEFERRED', 'Detail.', '/x'],\n"
                "]\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_an_equals_inside_a_line_comment_is_not_the_assignment(self) -> None:
        # `str.find('=')` selected the `=` inside the comment, so the `[` at the end of
        # that comment opened an array the declaration never assigns, and the rows of
        # dead code below were compared. A declaration that assigns nothing is an input
        # error, not a declaration to read.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const capabilityRows // = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("states no initializer", message)

    def test_a_commented_assignment_does_not_hide_the_real_one(self) -> None:
        # The same `find` took the `=` inside a block comment and then read the `[`
        # inside it, rejecting a declaration whose initializer is a plain array. The
        # assignment is found by scanning, so the comment is text and the second `=`
        # is the token.
        self.assertEqual(
            parse_site_rows(
                "const capabilityRows /* = [ archived */ = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_block_comment_closed_by_a_line_comment_is_still_a_comment(self) -> None:
        # Counting `/*` and `*/` separately read the `*/` inside the `//` comment as a
        # block closer, so the commented-out copy below it looked live: its stale
        # DEFERRED row was compared while the page rendered the row after the comment.
        self.assertEqual(
            parse_site_rows(
                "// Block comments end with */\n"
                "/*\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'DEFERRED', 'Detail.', '/x'],\n"
                "]\n"
                "*/\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_reassignable_binding_is_rejected(self) -> None:
        # A `let` binding can be handed a different array after the one the guard
        # reads: here the export renders nothing, while the initial rows were
        # compared and the guard reported agreement over them. Only `const` is
        # accepted, because a `let` holding a literal that never changes is not a
        # shape worth reading; the rejection names the line and the kind it found.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "let capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
                "capabilityRows = []\n"
            )
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("`let`", message)
        self.assertIn("must be `const`", message)

    def test_a_var_binding_is_rejected_the_same_way(self) -> None:
        # `var` is reassignable for the same reason, so the same rule rejects it.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "var capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        self.assertIn("`var`", str(caught.exception))

    def test_a_regular_expression_literal_is_rejected_rather_than_counted(self) -> None:
        # `/[}]/` inside a helper: the regex's `}` was counted as the helper's end, so
        # the helper's local declaration read as module level and its DEFERRED rows
        # were compared while the export read the PROVISIONAL array below it. Telling a
        # regex from a division needs the previous significant token, which this scan
        # does not carry, so a `/` in code is rejected rather than guessed at.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "function helper() {\n"
                "  const pattern = /[}]/\n"
                "  const capabilityRows = [\n"
                "    ['Memory substrate', 'DEFERRED', 'Detail.', '/x'],\n"
                "  ]\n"
                "}\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 2", message)
        self.assertIn("regular expression", message)

    def test_a_slash_in_a_string_or_a_comment_is_still_text(self) -> None:
        # The rejection is for a `/` in code. A rendered path and a `//` comment are
        # text, so the real ledger -- every detail is a `/docs/...` href -- is read.
        self.assertEqual(
            parse_site_rows(
                "// /docs/architecture/status-and-evidence states the claim rules\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/docs/memory/overview'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_function_local_declaration_is_not_the_exported_one(self) -> None:
        # The export reads the module-level binding, so a declaration inside a function,
        # an arrow body, a class body, or a bare block is a different array: selecting
        # it compared rows the page never renders.
        for scope, prefix, indent, suffix in (
            ("function body", "function helper() {\n", "  ", "}\n"),
            ("arrow body", "const helper = () => {\n", "  ", "}\n"),
            ("class body", "class Ledger {\n  build() {\n", "    ", "  }\n}\n"),
            ("bare block", "if (ready) {\n", "  ", "}\n"),
        ):
            with self.subTest(scope=scope):
                self.assertEqual(
                    parse_site_rows(
                        prefix
                        + f"{indent}const capabilityRows = [\n"
                        + f"{indent}  ['Memory substrate', 'DEFERRED', 'Detail.', '/x'],\n"
                        + f"{indent}]\n"
                        + suffix
                        + "const capabilityRows = [\n"
                        + "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                        + "]\n"
                    ),
                    {"Memory substrate": "PROVISIONAL"},
                )

    def test_a_declaration_inside_an_unclosed_block_comment_is_not_read(self) -> None:
        # The scan stays inside a comment that never closes, so the only declaration is
        # comment text and the file holds no array the guard can read.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "/*\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        self.assertIn("no `capabilityRows` array", str(caught.exception))

    def test_a_template_literal_without_substitution_is_skipped(self) -> None:
        # Template text is not code, so a literal above the declaration neither opens a
        # scope nor hides the declaration.
        self.assertEqual(
            parse_site_rows(
                "const banner = `rows follow { here`\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_a_template_substitution_before_the_declaration_is_rejected(self) -> None:
        # `${...}` is code, and code in a template can open a scope the scan would not
        # see: the declaration could then be read as module level while it is not.
        # Rejected rather than guessed at, naming the line.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const banner = `${ { a: 1 } }`\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("template literal", message)

    def test_an_escaped_quote_before_the_declaration_does_not_end_the_string(self) -> None:
        # A backslash escapes the next character, so the quote after it is text. A
        # brace inside a string or a template is text too: counting it would open a
        # scope that hides the module-level declaration.
        self.assertEqual(
            parse_site_rows(
                "const banner = 'it\\'s { not a scope'\n"
                "const note = `a \\` b { c`\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            ),
            {"Memory substrate": "PROVISIONAL"},
        )

    def test_an_unclosed_string_before_the_declaration_is_rejected(self) -> None:
        # A quote that never closes makes every following token ambiguous, so the
        # declaration cannot be placed: it is an input error naming the line.
        with self.assertRaises(InputError) as caught:
            parse_site_rows(
                "const banner = 'oops\n"
                "const capabilityRows = [\n"
                "  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/x'],\n"
                "]\n"
            )
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("not closed", message)


if __name__ == "__main__":
    unittest.main()
