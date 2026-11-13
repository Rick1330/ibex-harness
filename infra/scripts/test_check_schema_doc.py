#!/usr/bin/env python3
"""Tests for infra/scripts/check-schema-doc.py (P2-11 gate)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
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


class CoveredTests(unittest.TestCase):
    def test_bare_key_matches_any_schema(self) -> None:
        self.assertTrue(check_schema_doc.covered("organizations", {"ibex_core.organizations"}))

    def test_qualified_key_requires_exact_schema(self) -> None:
        self.assertFalse(check_schema_doc.covered("ibex_audit.tokens", {"ibex_core.tokens"}))

    def test_exact_match(self) -> None:
        self.assertTrue(check_schema_doc.covered("ibex_core.tokens", {"ibex_core.tokens"}))


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

    def test_passes_when_doc_covers_every_table(self) -> None:
        doc = make_doc(
            self.root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```

            ##### `ibex_core.b` (migration `000001`)

            **Purpose.** B.

            ### ClickHouse Schema
            """,
        )
        problems, summary = check_schema_doc.check(self.root, doc)
        self.assertEqual(problems, [])
        self.assertTrue(summary.startswith("OK:"), summary)

    def test_fails_when_a_migration_table_is_missing(self) -> None:
        doc = make_doc(
            self.root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, _ = check_schema_doc.check(self.root, doc)
        self.assertTrue(any("ibex_core.b" in line for line in problems), problems)

    def test_fails_when_doc_names_an_unmigrated_table(self) -> None:
        doc = make_doc(
            self.root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);
            CREATE TABLE ibex_core.ghost (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, _ = check_schema_doc.check(self.root, doc)
        self.assertTrue(any("ibex_core.ghost" in line for line in problems), problems)

    def test_planning_marker_exempts_a_sketch(self) -> None:
        doc = make_doc(
            self.root,
            """
            ### PostgreSQL Schema

            ```sql
            CREATE TABLE ibex_core.a (id UUID);
            CREATE TABLE ibex_core.b (id UUID);

            -- schema-doc: not-migrated — planning sketch.
            CREATE TABLE ibex_core.sketch (id UUID);
            ```

            ### ClickHouse Schema
            """,
        )
        problems, summary = check_schema_doc.check(self.root, doc)
        self.assertEqual(problems, [])
        self.assertTrue(summary.startswith("OK:"), summary)

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
        self.assertTrue(any("ibex_core.unmarked" in line for line in problems), problems)
        self.assertFalse(any("ibex_core.sketch" in line for line in problems), problems)

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
