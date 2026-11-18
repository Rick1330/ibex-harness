#!/usr/bin/env python3
"""The comparison: one vocabulary, one status per capability, no unaccounted row.

These cases cover the findings the guard reports rather than the parsing: a label
missing from a surface, a class moved under another label, a capability whose
surfaces disagree, a status outside the vocabulary, and a row no capability
declares.
"""

from __future__ import annotations

import unittest

from status_vocabulary import (
    CAPABILITIES,
    compare_capabilities,
    compare_rows,
    compare_vocabulary,
    read_status,
)
from status_vocabulary_fixtures import CLASS_BY_LABEL

DECLARED_LABELS = ("IMPLEMENTED", "PROVISIONAL")

# What `statusMeta` and the docs vocabulary table state when they agree on every
# label's ledger class. A case starts here and departs from it on the one point it
# is about, so no case restates the vocabulary it is not testing.
AGREED_CLASSES = {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"}


class VocabularyTests(unittest.TestCase):
    def assert_one_finding_naming(
        self, site: dict[str, str], docs: dict[str, str], *fragments: str
    ) -> None:
        """Exactly one vocabulary finding, and it names every `fragment`.

        Naming each fragment is the assertion: a finding that fires without saying
        which label, surface, or class disagrees does not tell the reader what to
        fix, and a broad "it failed" would pass while the detail was lost.
        """
        problems = compare_vocabulary(DECLARED_LABELS, site, docs, DECLARED_LABELS)
        self.assertEqual(len(problems), 1, problems)
        for fragment in fragments:
            self.assertIn(fragment, problems[0])

    def test_a_label_missing_from_a_surface_names_the_label_and_the_surface(self) -> None:
        # `statusMeta` declares no class for PROVISIONAL at all.
        self.assert_one_finding_naming(
            {"IMPLEMENTED": "shipped-local"},
            AGREED_CLASSES,
            "PROVISIONAL",
            "`statusMeta`",
        )

    def test_a_class_moved_under_another_label_is_named(self) -> None:
        self.assert_one_finding_naming(
            AGREED_CLASSES,
            {**AGREED_CLASSES, "PROVISIONAL": "deferred"},
            "PROVISIONAL",
            "provisional",
            "deferred",
        )

    def test_a_label_the_docs_use_but_the_type_does_not_declare_is_named(self) -> None:
        problems = compare_vocabulary(
            ["IMPLEMENTED"],
            {"IMPLEMENTED": "shipped-local"},
            {"IMPLEMENTED": "shipped-local"},
            ["IMPLEMENTED", "UNKNOWN"],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("UNKNOWN", problems[0])

    def test_agreement_reports_nothing(self) -> None:
        # The input every case above departs from one point at a time, compared
        # unmodified: `AGREED_CLASSES` is only worth starting from if it agrees.
        self.assertEqual(
            compare_vocabulary(DECLARED_LABELS, AGREED_CLASSES, AGREED_CLASSES, DECLARED_LABELS),
            [],
        )


class StatusCellTests(unittest.TestCase):
    def test_a_ledger_class_cell_is_translated_through_the_vocabulary(self) -> None:
        self.assertEqual(
            read_status("`shipped-local` / profile-dependent", True, CLASS_BY_LABEL),
            "IMPLEMENTED",
        )

    def test_the_first_class_token_is_the_row_status(self) -> None:
        # "`provisional`: target ratified; PR gate `shipped-local`" states the row
        # status first and the gate class second.
        self.assertEqual(
            read_status(
                "`provisional`: target ratified; PR gate `shipped-local`", True, CLASS_BY_LABEL
            ),
            "PROVISIONAL",
        )

    def test_a_cell_naming_no_known_class_is_unreadable(self) -> None:
        self.assertIsNone(read_status("target ratified", True, CLASS_BY_LABEL))

    def test_a_label_cell_loses_its_backticks(self) -> None:
        self.assertEqual(
            read_status("`PROVISIONAL`", False, CLASS_BY_LABEL),
            "PROVISIONAL",
        )

    def test_a_label_the_vocabulary_does_not_declare_is_unreadable(self) -> None:
        # A typo or a new label must be a finding, not a value compared against
        # the other surfaces.
        self.assertIsNone(read_status("DONE", False, CLASS_BY_LABEL))


class CapabilityTests(unittest.TestCase):
    CLASS_SURFACES = frozenset({"engineering"})

    def rows(self) -> dict[str, dict[str, str]]:
        """Every declared capability, present and in agreement, surface by surface."""
        rows: dict[str, dict[str, str]] = {
            key: {} for key in ("engineering", "docs", "ledger", "mirror")
        }
        for names in CAPABILITIES.values():
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
        return compare_capabilities(rows, CLASS_BY_LABEL, self.CLASS_SURFACES)

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
        problems = compare_capabilities(rows, CLASS_BY_LABEL, self.CLASS_SURFACES)
        self.assertEqual(len(problems), 1)
        self.assertIn("auth-proxy", problems[0])
        self.assertIn("no such row", problems[0])

    def test_a_status_outside_the_vocabulary_is_named(self) -> None:
        problems = self.problems("`provisional`", "DONE", "PROVISIONAL")
        self.assertEqual(len(problems), 1)
        self.assertIn("auth-proxy", problems[0])
        self.assertIn("not a declared status", problems[0])

    def test_a_row_no_capability_declares_is_reported(self) -> None:
        problems = compare_rows(
            {"ledger": {"Auth and proxy foundations": "IMPLEMENTED", "New capability": "DEFERRED"}}
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("New capability", problems[0])


if __name__ == "__main__":
    unittest.main()
