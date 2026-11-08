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


if __name__ == "__main__":
    unittest.main()
