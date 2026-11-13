#!/usr/bin/env python3
"""Tests for infra/scripts/check-schema-doc.py (P2-11 gate)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-schema-doc.py")
SPEC = importlib.util.spec_from_file_location("check_schema_doc", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load check-schema-doc.py")
check_schema_doc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_schema_doc
SPEC.loader.exec_module(check_schema_doc)


def make_repo(root: Path, migrations: dict[str, str]) -> Path:
    directory = root / "infra" / "migrations" / "postgres"
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in migrations.items():
        (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return root


def make_doc(root: Path, body: str, name: str = "DATABASE_SCHEMA.md") -> Path:
    path = root / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@dataclass(frozen=True)
class DocCase:
    """One doc and the verdict the gate must reach on it.

    ``needle`` is the table the problems must name; ``None`` means the doc is in
    sync and the gate must pass it with an ``OK:`` summary.
    """

    name: str
    body: str
    needle: str | None = None


# The migrations fixture is `ibex_core.a` and `ibex_core.b`, so each row states one
# drift shape: complete, a migration table the doc omits, a doc table no migration
# creates, and a sketch the planning marker exempts.
DOC_CASES = (
    DocCase(
        name="every migration table is documented",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```

            ##### `ibex_core.b` (migration `000001`)

            **Purpose.** B.

            ### ClickHouse Schema
            """,
    ),
    DocCase(
        name="a migration table the doc never names fails",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```

            ### ClickHouse Schema
            """,
        needle="ibex_core.b",
    ),
    DocCase(
        name="a doc table no migration creates fails",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);
            CREATE TABLE ibex_core.ghost (id UUID);
            ```

            ### ClickHouse Schema
            """,
        needle="ibex_core.ghost",
    ),
    DocCase(
        name="the planning marker exempts a sketch",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);

            -- schema-doc: not-migrated — planning sketch.
            CREATE TABLE ibex_core.sketch (id UUID);
            ```

            ### ClickHouse Schema
            """,
    ),
)


# The fence and literal shapes, each row one structural case the scanner must
# read the same way a Markdown renderer and the PostgreSQL lexer do: a tilde
# fence documents a table, a fence-like body line does not close its fence, a
# CREATE TABLE inside a doc string literal is not DDL, and a heading inside a
# non-sql fence documents nothing (so `ibex_core.b` stays undocumented).
FENCE_CASES = (
    DocCase(
        name="a tilde fence documents a table",
        body="""
            ### PostgreSQL Schema

            ~~~sql
            CREATE TABLE ibex_core.a (id UUID);
            ~~~

            ##### `ibex_core.b` (migration `000001`)

            ### ClickHouse Schema
            """,
    ),
    DocCase(
        name="a fence-like body line does not close the fence",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```python
            CREATE TABLE ibex_core.b (id UUID);
            ```

            ### ClickHouse Schema
            """,
    ),
    DocCase(
        name="a CREATE TABLE inside a doc literal adds no table",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);
            INSERT INTO ibex_core.a (note)
            VALUES ('CREATE TABLE ibex_core.ghost (id UUID);');
            ```

            ### ClickHouse Schema
            """,
    ),
    DocCase(
        name="a heading inside a fence does not document a table",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```

            ```text
            ##### `ibex_core.b` (migration `000001`)
            ```

            ### ClickHouse Schema
            """,
        needle="ibex_core.b",
    ),
    DocCase(
        name="a literal with a backslash does not hide the table after it",
        body="""
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            INSERT INTO ibex_core.a (path) VALUES ('C:\\');
            CREATE TABLE ibex_core.b (id UUID);
            ```

            ### ClickHouse Schema
            """,
    ),
)


class TableKeyTests(unittest.TestCase):
    def test_qualified_and_unqualified(self) -> None:
        keys = check_schema_doc.table_keys(
            "CREATE TABLE ibex_core.a (id UUID);\nCREATE TABLE b (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.a", "b"])

    def test_if_not_exists_and_unlogged(self) -> None:
        keys = check_schema_doc.table_keys(
            "CREATE TABLE IF NOT EXISTS ibex_core.a (id UUID);\n"
            "CREATE UNLOGGED TABLE ibex_core.b (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.a", "ibex_core.b"])

    def test_comments_are_ignored(self) -> None:
        keys = check_schema_doc.table_keys(
            "-- CREATE TABLE ibex_core.ghost (id UUID);\n"
            "/* CREATE TABLE ibex_core.ghost2 (id UUID); */\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_quoted_qualified_identifiers(self) -> None:
        keys = check_schema_doc.table_keys(
            'CREATE TABLE "ibex_core"."quoted_table" (id UUID);'
        )
        self.assertEqual(keys, ["ibex_core.quoted_table"])

    def test_quoted_unqualified_identifier(self) -> None:
        keys = check_schema_doc.table_keys('CREATE TABLE "standalone" (id UUID);')
        self.assertEqual(keys, ["standalone"])

    def test_apostrophe_inside_a_quoted_identifier_is_not_a_string(self) -> None:
        keys = check_schema_doc.table_keys(
            'CREATE TABLE "it\'s" (id UUID);\nCREATE TABLE ibex_core.after (id UUID);'
        )
        self.assertEqual(keys, ["it's", "ibex_core.after"])

    def test_unparsable_create_table_is_a_structural_error(self) -> None:
        with self.assertRaises(check_schema_doc.DocError):
            check_schema_doc.table_keys("CREATE TABLE (id UUID);")

    def test_create_table_inside_a_string_literal_is_ignored(self) -> None:
        keys = check_schema_doc.table_keys(
            "INSERT INTO ibex_core.a (note) VALUES ('CREATE TABLE ibex_core.ghost (id UUID);');\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_a_backslash_in_an_ordinary_string_does_not_hide_the_next_table(
        self,
    ) -> None:
        # standard_conforming_strings is on by default, so the backslash is a
        # literal and the string closes at the quote after it. Treating the
        # backslash as an escape runs the string to end of file and loses the
        # CREATE TABLE that follows.
        keys = check_schema_doc.table_keys(
            "INSERT INTO ibex_core.a (path) VALUES ('C:\\');\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_a_backslash_in_an_escape_string_still_escapes(self) -> None:
        # `E'…'` is the one string form where a backslash escapes, so the quote
        # after it does not close the string and the keyword stays data.
        keys = check_schema_doc.table_keys(
            "SELECT E'it\\'s CREATE TABLE ibex_core.ghost (id UUID);';\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_create_table_inside_a_do_body_is_detected(self) -> None:
        # A DO block is plpgsql that runs, so the table it creates exists.
        keys = check_schema_doc.table_keys(
            "DO $body$ BEGIN CREATE TABLE ibex_core.dynamic (id UUID); END $body$;\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.dynamic", "ibex_core.real"])

    def test_create_table_inside_an_inert_dollar_quoted_body_is_ignored(self) -> None:
        keys = check_schema_doc.table_keys(
            "SELECT $body$ CREATE TABLE ibex_core.ghost (id UUID); $body$;\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_dynamic_sql_inside_an_execute_literal_is_scanned(self) -> None:
        # `EXECUTE '…'` runs its literal, so the table it creates exists.
        keys = check_schema_doc.table_keys(
            "DO $body$ BEGIN EXECUTE 'CREATE TABLE ibex_core.dynamic (id UUID);'; END $body$;\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.dynamic", "ibex_core.real"])

    def test_a_non_execute_string_inside_a_do_body_is_still_data(self) -> None:
        keys = check_schema_doc.table_keys(
            "DO $body$ BEGIN RAISE NOTICE 'CREATE TABLE ibex_core.ghost (id UUID);'; "
            "END $body$;\nCREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_dynamic_sql_built_by_format_is_not_scanned(self) -> None:
        # `EXECUTE format(…)` is a call, not a literal, so it stays data; the
        # scanner must not try to parse a format string as DDL.
        keys = check_schema_doc.table_keys(
            "DO $body$ BEGIN EXECUTE format('CREATE TABLE %I (id UUID)', 'ghost'); "
            "END $body$;\nCREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_every_accepted_qualifier_parses(self) -> None:
        qualifiers = ["", *sorted(check_schema_doc.CREATE_TABLE_QUALIFIERS)]
        for qualifier in qualifiers:
            for spelling in (qualifier.upper(), qualifier.lower(), qualifier.title()):
                prefix = f"CREATE {spelling} TABLE" if spelling else "CREATE TABLE"
                with self.subTest(prefix=prefix):
                    keys = check_schema_doc.table_keys(
                        f"{prefix} ibex_core.t (id UUID);"
                    )
                    self.assertEqual(keys, ["ibex_core.t"])

    def test_a_word_that_is_not_a_qualifier_is_not_a_create_table(self) -> None:
        keys = check_schema_doc.table_keys(
            "CREATE FOO TABLE ibex_core.a (id UUID);\n"
            "CREATE UNLOGGEDX TABLE ibex_core.b (id UUID);\n"
            "CREATE MATERIALIZED VIEW mv AS SELECT 1;"
        )
        self.assertEqual(keys, [])

    def test_a_table_named_table_parses_as_the_unqualified_form(self) -> None:
        keys = check_schema_doc.table_keys(
            "CREATE TABLE table (id UUID);\nCREATE TEMP TABLE table (id UUID);"
        )
        self.assertEqual(keys, ["table", "table"])

    def test_a_unicode_dollar_tag_is_a_tag(self) -> None:
        # PostgreSQL tags follow the unquoted-identifier rules, so `$café$` is a
        # delimiter and the statement inside it is data.
        keys = check_schema_doc.table_keys(
            "SELECT $café$ CREATE TABLE ibex_core.ghost (id UUID); $café$;\n"
            "CREATE TABLE ibex_core.real (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.real"])

    def test_dollar_tag_forms(self) -> None:
        cases = {
            "$$": "$$",
            "$tag$": "$tag$",
            "$_x1$": "$_x1$",
            "$café$": "$café$",
        }
        for sql, want in cases.items():
            with self.subTest(sql=sql):
                self.assertEqual(check_schema_doc._dollar_tag(sql, 0), want)

    def test_dollar_tag_rejects_a_digit_start_and_stops_at_a_dollar(self) -> None:
        # `$1` is a parameter in PostgreSQL, not a tag; a tag may not contain `$`.
        self.assertIsNone(check_schema_doc._dollar_tag("$1$", 0))
        self.assertEqual(check_schema_doc._dollar_tag("$a$b$", 0), "$a$")

    def test_ends_with_keyword_matches_a_whole_word(self) -> None:
        self.assertFalse(check_schema_doc._ends_with_keyword(["SELECT caféDO"], "DO"))
        self.assertTrue(check_schema_doc._ends_with_keyword(["DO"], "DO"))
        self.assertTrue(
            check_schema_doc._ends_with_keyword(["BEGIN EXECUTE"], "EXECUTE")
        )

    def test_a_quoted_identifier_keeps_its_case(self) -> None:
        keys = check_schema_doc.table_keys(
            'CREATE TABLE ibex_core."Users" (id UUID);\n'
            "CREATE TABLE ibex_core.users (id UUID);"
        )
        self.assertEqual(keys, ["ibex_core.Users", "ibex_core.users"])

    def test_an_unquoted_identifier_folds_to_lower_case(self) -> None:
        keys = check_schema_doc.table_keys(
            "CREATE TABLE IBEX_CORE.Users (id UUID);\n"
            'CREATE TABLE "ibex_core"."Users" (id UUID);'
        )
        self.assertEqual(keys, ["ibex_core.users", "ibex_core.Users"])

    def test_a_doubled_quote_inside_a_quoted_identifier_is_one_quote(self) -> None:
        keys = check_schema_doc.table_keys('CREATE TABLE "we""ird" (id UUID);')
        self.assertEqual(keys, ['we"ird'])


class FenceScannerTests(unittest.TestCase):
    def test_fence_opener_shapes(self) -> None:
        cases = {
            "```sql": ("```", "sql"),
            "````sql": ("````", "sql"),
            "~~~sql": ("~~~", "sql"),
            "~~~~ postgresql": ("~~~~", "postgresql"),
            "  ~~~": ("~~~", ""),
            "\t```sql": ("```", "sql"),
            "``` not a closer": ("```", "not a closer"),
            "```py`x": None,
            "```` `": None,
            "``": None,
            "~~": None,
            "CREATE TABLE ibex_core.a (id UUID);": None,
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(check_schema_doc._fence_opener(line), expected)

    def test_tilde_fence_is_sql(self) -> None:
        lines = ["~~~sql", "CREATE TABLE ibex_core.a (id UUID);", "~~~"]
        self.assertEqual(
            check_schema_doc.fenced_sql_blocks(lines),
            [(1, "CREATE TABLE ibex_core.a (id UUID);")],
        )

    def test_longer_opener_ignores_a_shorter_run(self) -> None:
        lines = ["````sql", "```", "CREATE TABLE ibex_core.a (id UUID);", "````"]
        self.assertEqual(
            check_schema_doc.fenced_sql_blocks(lines),
            [(1, "```\nCREATE TABLE ibex_core.a (id UUID);")],
        )

    def test_a_different_marker_does_not_close(self) -> None:
        lines = ["~~~sql", "```", "CREATE TABLE ibex_core.a (id UUID);", "~~~"]
        blocks = check_schema_doc.fenced_sql_blocks(lines)
        self.assertEqual(len(blocks), 1)
        self.assertIn("CREATE TABLE", blocks[0][1])

    def test_trailing_text_does_not_close(self) -> None:
        lines = [
            "```sql",
            "CREATE TABLE ibex_core.a (id UUID);",
            "``` not a closer",
            "```",
        ]
        blocks = check_schema_doc.fenced_sql_blocks(lines)
        self.assertEqual(len(blocks), 1)
        self.assertIn("not a closer", blocks[0][1])


class CoveredTests(unittest.TestCase):
    def test_bare_key_matches_any_schema(self) -> None:
        self.assertTrue(
            check_schema_doc.covered("organizations", {"ibex_core.organizations"})
        )

    def test_qualified_key_requires_exact_schema(self) -> None:
        self.assertFalse(
            check_schema_doc.covered("ibex_audit.tokens", {"ibex_core.tokens"})
        )

    def test_exact_match(self) -> None:
        self.assertTrue(
            check_schema_doc.covered("ibex_core.tokens", {"ibex_core.tokens"})
        )

    def test_a_quoted_identity_is_not_its_unquoted_neighbour(self) -> None:
        # PostgreSQL folds `users` to lower case and keeps `"Users"` as written,
        # so the two names are two tables, not one.
        self.assertFalse(
            check_schema_doc.covered("ibex_core.Users", {"ibex_core.users"})
        )
        self.assertFalse(
            check_schema_doc.covered("ibex_core.users", {"ibex_core.Users"})
        )


class CheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_repo(
            self.root,
            {
                "000001_init.up.sql": """
                    CREATE TABLE ibex_core.a (id UUID);
                    CREATE TABLE ibex_core.b (id UUID);
                """,
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_gate_reaches_the_recorded_verdict_for_each_doc(self) -> None:
        for case in DOC_CASES:
            with self.subTest(case.name):
                problems, summary = self._check(case.body)
                self._assert_verdict(case, problems, summary)

    def test_the_gate_reaches_the_recorded_verdict_for_each_fence_shape(self) -> None:
        for case in FENCE_CASES:
            with self.subTest(case.name):
                problems, summary = self._check(case.body)
                self._assert_verdict(case, problems, summary)

    def _check(self, body: str) -> tuple[list[str], str]:
        return check_schema_doc.check(self.root, make_doc(self.root, body))

    def _assert_verdict(self, case: DocCase, problems: list[str], summary: str) -> None:
        """An in-sync doc passes with a summary; a drifting one names the table at fault."""
        if case.needle is None:
            self.assertEqual(problems, [])
            self.assertTrue(summary.startswith("OK:"), summary)
            return
        self.assertTrue(any(case.needle in line for line in problems), problems)

    def test_planning_marker_does_not_leak_to_the_next_statement(self) -> None:
        doc = make_doc(
            self.root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);

            -- schema-doc: not-migrated — planning sketch.
            CREATE TABLE ibex_core.sketch (id UUID);

            CREATE TABLE ibex_core.unmarked (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, _ = check_schema_doc.check(self.root, doc)
        self.assertTrue(
            any("ibex_core.unmarked" in line for line in problems), problems
        )
        self.assertFalse(any("ibex_core.sketch" in line for line in problems), problems)

    def test_quoted_table_a_migration_creates_is_not_skipped(self) -> None:
        root = Path(self._tmp.name) / "quoted-missing"
        make_repo(
            root, {"000001_init.up.sql": 'CREATE TABLE "ibex_core"."quoted" (id UUID);'}
        )
        doc = make_doc(root, "### PostgreSQL Schema\n\n### ClickHouse Schema\n")
        problems, _ = check_schema_doc.check(root, doc)
        self.assertTrue(any("ibex_core.quoted" in line for line in problems), problems)

    def test_quoted_table_documented_with_the_same_key(self) -> None:
        root = Path(self._tmp.name) / "quoted-documented"
        make_repo(
            root, {"000001_init.up.sql": 'CREATE TABLE "ibex_core"."quoted" (id UUID);'}
        )
        doc = make_doc(
            root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE "ibex_core"."quoted" (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, summary = check_schema_doc.check(root, doc)
        self.assertEqual(problems, [])
        self.assertTrue(summary.startswith("OK:"), summary)

    def test_create_table_inside_a_migration_literal_adds_no_table(self) -> None:
        root = Path(self._tmp.name) / "literal-migration"
        make_repo(
            root,
            {
                "000001_init.up.sql": """
                    CREATE TABLE ibex_core.a (id UUID);
                    CREATE TABLE ibex_core.b (id UUID);
                    INSERT INTO ibex_core.a (note)
                    VALUES ('CREATE TABLE ibex_core.ghost (id UUID);');
                """,
            },
        )
        doc = make_doc(
            root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, _ = check_schema_doc.check(root, doc)
        self.assertEqual(problems, [])

    def test_missing_heading_is_a_structural_error(self) -> None:
        doc = make_doc(self.root, "# Title\n\nNo headings here.\n")
        with self.assertRaises(check_schema_doc.DocError):
            check_schema_doc.check(self.root, doc)

    def test_empty_migration_set_is_a_structural_error(self) -> None:
        empty = Path(self._tmp.name) / "empty"
        make_repo(empty, {})
        doc = make_doc(
            self.root,
            "### PostgreSQL Schema\n\n### ClickHouse Schema\n",
            name="empty.md",
        )
        with self.assertRaises(check_schema_doc.DocError):
            check_schema_doc.check(empty, doc)


if __name__ == "__main__":
    unittest.main()
