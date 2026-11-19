"""Unit tests for infra/scripts/lib/dotenv.py.

The deployment scripts derive the browser origin and the edge probe URL from
this reader, so a silent change here can break `make v1-up` or trust the wrong
origin. These tests pin the Docker Compose semantics that matter to the profile.
"""

from __future__ import annotations

import importlib.util
import io
import os
import unittest
from pathlib import Path
from unittest import mock

INFRA = Path(__file__).resolve().parents[2]
MODULE_PATH = INFRA / "scripts" / "lib" / "dotenv.py"

spec = importlib.util.spec_from_file_location("ibex_dotenv", MODULE_PATH)
dotenv = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(dotenv)


def read(text: str, key: str) -> str:
    return dotenv.read_value(io.StringIO(text), key)


class ParseTests(unittest.TestCase):
    def test_plain_value(self):
        self.assertEqual(read("A=1\n", "A"), "1")

    def test_missing_key_is_empty(self):
        self.assertEqual(read("A=1\n", "B"), "")

    def test_inline_comment_is_stripped(self):
        self.assertEqual(read("PORT=9443 # HTTPS\n", "PORT"), "9443")

    def test_quoted_value_keeps_hash(self):
        self.assertEqual(read('A="keep # this"\n', "A"), "keep # this")

    def test_single_quoted_value(self):
        self.assertEqual(read("A='literal # value'\n", "A"), "literal # value")

    def test_whitespace_around_assignment(self):
        self.assertEqual(read("  A  =  spaced  \n", "A"), "spaced")

    def test_last_assignment_wins(self):
        self.assertEqual(read("A=first\nA=second\n", "A"), "second")

    def test_comment_lines_are_ignored(self):
        self.assertEqual(read("# A=commented\nA=real\n", "A"), "real")

    def test_export_prefix_is_ignored(self):
        self.assertEqual(read("export A=exported\n", "A"), "exported")

    def test_value_containing_equals(self):
        self.assertEqual(read("A=redis://x:6379/0?a=b\n", "A"), "redis://x:6379/0?a=b")

    def test_hash_without_space_is_data(self):
        self.assertEqual(read("A=http://x#fragment\n", "A"), "http://x#fragment")

    def test_missing_trailing_newline(self):
        self.assertEqual(read("A=last", "A"), "last")


class InterpolationTests(unittest.TestCase):
    def test_dollar_name_from_earlier_assignment(self):
        self.assertEqual(read("BASE=https://localhost\nORIGIN=$BASE\n", "ORIGIN"), "https://localhost")

    def test_braced_name_from_earlier_assignment(self):
        self.assertEqual(read("PORT=9443\nORIGIN=https://localhost:${PORT}\n", "ORIGIN"), "https://localhost:9443")

    def test_default_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING:-443}\n", "A"), "443")

    def test_default_with_single_dash(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING-443}\n", "A"), "443")

    def test_colon_default_applies_when_value_is_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("PORT=\nA=${PORT:-443}\n", "A"), "443")

    def test_single_dash_keeps_empty_value(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("PORT=\nA=${PORT-443}\n", "A"), "")

    def test_environment_wins_over_default(self):
        with mock.patch.dict(os.environ, {"IBEX_TEST_PORT": "8443"}, clear=False):
            self.assertEqual(read("A=${IBEX_TEST_PORT:-443}\n", "A"), "8443")

    def test_environment_wins_over_seen_value(self):
        with mock.patch.dict(os.environ, {"PORT": "8443"}, clear=False):
            self.assertEqual(read("PORT=443\nA=${PORT}\n", "A"), "8443")

    def test_required_operator_returns_value_when_present(self):
        self.assertEqual(read("PORT=8443\nA=${PORT:?missing}\n", "A"), "8443")

    def test_alternate_operator_returns_fallback_when_present(self):
        self.assertEqual(read("PORT=8443\nA=${PORT:+ready}\n", "A"), "ready")

    def test_alternate_operator_is_empty_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING:+ready}\n", "A"), "")

    def test_escaped_quote_inside_double_quotes(self):
        self.assertEqual(read('A="say \\"hi\\""\n', "A"), 'say "hi"')

    def test_escaped_quote_does_not_end_the_value(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read('A="8443${MISSING:+\\"x\\"}"\n', "A"), "8443")

    def test_escaped_dollar_is_not_interpolated(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read('A="\\$MISSING"\n', "A"), "$MISSING")

    def test_escaped_tab_becomes_a_control_character(self):
        self.assertEqual(read('A="a\\tb"\n', "A"), "a\tb")

    def test_escaped_newline_becomes_a_control_character(self):
        self.assertEqual(read('A="a\\nb"\n', "A"), "a\nb")

    def test_required_empty_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(dotenv.DotenvError):
                read("PORT=\nA=${PORT:?set PORT}\n", "A")

    def test_required_unset_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(dotenv.DotenvError):
                read("A=${MISSING?set it}\n", "A")

    def test_required_returns_value_when_set(self):
        self.assertEqual(read("PORT=8443\nA=${PORT:?set PORT}\n", "A"), "8443")

    def test_double_dollar_is_literal(self):
        self.assertEqual(read("A=pa$$word\n", "A"), "pa$word")

    def test_unknown_dollar_kept_as_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=prefix-$MISSING\n", "A"), "prefix-")

    def test_interpolation_applies_to_quoted_values(self):
        self.assertEqual(read('PORT=9443\nORIGIN="https://localhost:${PORT}"\n', "ORIGIN"), "https://localhost:9443")

    def test_single_quotes_preserve_literal_dollar(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A='$MISSING'\n", "A"), "$MISSING")

    # --- positional syntax -------------------------------------------------
    #
    # `$1` is shell positional syntax, not Compose interpolation. Compose reads a
    # bare `$NAME` only when the name starts with a letter or underscore, so it
    # exports `p$1` unchanged; the reader used to take `1` as a variable name and
    # delete it. An operator-supplied password is the real case: the generator
    # writes it back escaped (`\$1`), and the two readers must agree on the value.

    def test_positional_parameter_is_literal(self):
        self.assertEqual(read("A=prefix-$1\n", "A"), "prefix-$1")

    def test_bare_dollar_followed_by_digit_is_literal(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=$1\n", "A"), "$1")

    def test_positional_parameter_after_an_escaped_dollar(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read('A="p\\$1"\n', "A"), "p$1")

    def test_positional_parameter_inside_a_default_operand_is_literal(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING:-pre-$1-post}\n", "A"), "pre-$1-post")

    def test_braced_positional_is_empty_not_an_error(self):
        # A choice, not parity: Compose refuses to start on `${1}` ("Invalid
        # template"), while this reader resolves the unknown name to empty. The
        # reader extracts one value for a script; it is not a second config
        # validator, and a file Compose rejects cannot produce a running profile,
        # so turning this into an error would only add a failure mode that a
        # working deployment never reaches.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${1}\n", "A"), "")

    # --- nested defaults ---------------------------------------------------
    #
    # `${NAME:-${OTHER:-fallback}}` nests, and Compose resolves the operand as an
    # expression before applying the operator. The reader used to close the outer
    # expression at the first `}`, so the value became the literal text
    # `${OTHER:-fallback}`.

    def test_nested_default_resolves_the_innermost(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING:-${OTHER:-c}}\n", "A"), "c")

    def test_nested_default_uses_an_earlier_assignment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("OTHER=deep\nA=${MISSING:-${OTHER:-c}}\n", "A"), "deep")

    def test_nested_default_does_not_see_a_later_assignment(self):
        # Compose resolves values in file order, so an assignment below the
        # reference is not visible yet. This pins that order, not just nesting.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${MISSING:-${OTHER}}\nOTHER=later\n", "A"), "")

    def test_nested_default_is_skipped_when_the_outer_value_is_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("SET=outer\nA=${SET:-${MISSING:-c}}\n", "A"), "outer")

    def test_outer_default_keeps_the_nested_default_when_it_is_needed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("SET=\nA=${SET:-${MISSING:-c}}\n", "A"), "c")

    # --- operands are evaluated lazily -------------------------------------
    #
    # Compose evaluates only the branch an operator selects. The reader
    # interpolated the operand before the operator ran, so an unselected branch
    # was evaluated too, and `${SET:-${MISSING:?error}}` raised with `SET` set:
    # the reader rejected an environment Compose accepts. `read_value` feeds the
    # secret generator and the profile tooling, so that aborted a valid install
    # before any key was read.

    def test_unselected_default_branch_is_not_evaluated(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                read("SET=present\nA=${SET:-${IBEX_NOT_SET_923:?error}}\n", "A"), "present"
            )

    def test_selected_default_branch_is_still_evaluated(self):
        # The other half of the fix: laziness must not disable the error that a
        # selected branch is supposed to raise.
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(dotenv.DotenvError):
            read("A=${IBEX_NOT_SET_924:-${IBEX_NOT_SET_925:?error}}\n", "A")

    def test_unselected_alternate_branch_is_not_evaluated(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("SET=\nA=${SET:+${IBEX_NOT_SET_926:?error}}\n", "A"), "")

    def test_selected_alternate_branch_is_still_evaluated(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(dotenv.DotenvError):
            read("SET=present\nA=${SET:+${IBEX_NOT_SET_927:?error}}\n", "A")

    def test_selected_alternate_branch_interpolates_its_operand(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                read("SET=present\nA=${SET:+${IBEX_NOT_SET_928:-chosen}}\n", "A"), "chosen"
            )

    def test_single_dash_operand_is_skipped_when_the_value_is_set_but_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("SET=\nA=${SET-${IBEX_NOT_SET_929:?error}}\n", "A"), "")

    def test_plain_alternate_operand_is_skipped_when_the_value_is_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=${IBEX_NOT_SET_930+${IBEX_NOT_SET_931:?error}}\n", "A"), "")

    def test_error_operand_is_skipped_when_the_value_is_non_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                read("SET=present\nA=${SET:?${IBEX_NOT_SET_932:?error}}\n", "A"), "present"
            )

    def test_error_operand_is_skipped_when_the_value_is_set_but_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("SET=\nA=${SET?${IBEX_NOT_SET_933:?error}}\n", "A"), "")

    # --- escapes Compose does not define -----------------------------------
    #
    # Compose decodes `\\`, `\"`, `\$`, `\n`, `\t` and `\r`. Any other escape is
    # left as the backslash plus the character; the reader used to drop the
    # backslash, so `a\qb` read here as `aqb` while Compose exported `a\qb`.

    def test_unknown_escape_keeps_its_backslash(self):
        self.assertEqual(read('A="a\\qb"\n', "A"), "a\\qb")

    def test_unknown_escape_keeps_the_following_character(self):
        self.assertEqual(read('A="path\\dto"\n', "A"), "path\\dto")

    def test_known_escapes_still_decode(self):
        self.assertEqual(read('A="a\\\\b"\n', "A"), "a\\b")


class MatchingBraceTests(unittest.TestCase):
    """Depth counting decides where an expression ends, so pin its shape."""

    def test_nested_expression_closes_at_the_outer_brace(self):
        value = "${A:-${B:-c}}"
        self.assertEqual(dotenv._matching_brace(value, 0), len(value) - 1)

    def test_sibling_expressions_close_independently(self):
        value = "${A:-${B:-c}}${D:-e}"
        self.assertEqual(dotenv._matching_brace(value, 0), value.index("}${D"))
        self.assertEqual(dotenv._matching_brace(value, value.index("${D")), len(value) - 1)

    def test_unterminated_expression_returns_minus_one(self):
        self.assertEqual(dotenv._matching_brace("${A:-${B:-c}", 0), -1)

    def test_brace_outside_an_expression_is_ignored(self):
        # The `}` before the opening `${` and the one after the closing brace are
        # ordinary text, not depth counting.
        value = "}x${A:-b}}"
        self.assertEqual(dotenv._matching_brace(value, 2), 8)

    def test_brace_outside_an_expression_survives_interpolation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read("A=}x${MISSING:-b}}\n", "A"), "}xb}")


if __name__ == "__main__":
    unittest.main()
