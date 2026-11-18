#!/usr/bin/env python3
"""The guard end to end: against this checkout, and against mutated copies of it.

A unit that passes on a fixture proves the parser; only the real surfaces prove the
claims they make, and only a mutated copy proves the guard still fails when a
surface drifts. Every case here runs ``main`` and reads its exit code and stderr.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from status_vocabulary import (
    DOCS_LEDGER,
    DOCS_MIRROR,
    DOCS_VOCABULARY,
    ENGINEERING_LEDGER,
    ROOT,
    SITE_LEDGER,
    main,
)


class RepositoryTests(unittest.TestCase):
    """The guard against this checkout, and against a mutated copy of it."""

    FILES = (
        ENGINEERING_LEDGER,
        SITE_LEDGER,
        DOCS_LEDGER,
        DOCS_VOCABULARY,
        DOCS_MIRROR,
    )

    def test_the_repository_agrees(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 0)

    def copy(self, directory: Path) -> Path:
        for relative in self.FILES:
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        return directory

    def run_against(self, root: Path) -> tuple[int, str]:
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = main(["--root", str(root)])
        return code, stderr.getvalue()

    def test_a_status_changed_in_one_surface_fails_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            ledger = root / SITE_LEDGER
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

    def test_a_reassignable_declaration_fails_naming_the_line(self) -> None:
        # `let` can be reassigned after the array the guard reads, so the rows compared
        # need not be the rows rendered. Only `const` is read, and the whole file fails
        # with the declaration's line rather than reporting agreement over an array the
        # export may have replaced.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            ledger = root / SITE_LEDGER
            mutated = ledger.read_text(encoding="utf-8").replace(
                "const capabilityRows:", "let capabilityRows:"
            )
            expected = mutated[: mutated.index("let capabilityRows")].count("\n") + 1
            ledger.write_text(mutated, encoding="utf-8")
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn(f"line {expected}", stderr)
        self.assertIn("must be `const`", stderr)

    def test_a_row_without_the_outer_pipes_is_compared(self) -> None:
        # GFM renders a row that omits the outer pipes, and the block ended before it,
        # so the row was never compared: this file passed while it listed a capability
        # no surface declares. It is now read, and `compare_rows` accounts for it.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            engineering = root / ENGINEERING_LEDGER
            last_row = "| Graph/A2A/marketplace/sandbox | `deferred` | These are not current dependencies. |"
            engineering.write_text(
                engineering.read_text(encoding="utf-8").replace(
                    last_row,
                    last_row + "\nNew capability | provisional | No hosted HA |",
                ),
                encoding="utf-8",
            )
            code, stderr = self.run_against(root)
        self.assertEqual(code, 1)
        self.assertIn("New capability", stderr)
        self.assertIn("no declared capability accounts for", stderr)

    def test_a_label_added_to_one_surface_fails_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            concepts = root / DOCS_VOCABULARY
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
            (root / DOCS_LEDGER).unlink()
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn(DOCS_LEDGER, stderr)

    def test_a_conflicting_stale_vocabulary_row_above_the_correct_one_fails(self) -> None:
        # The row a reader would see first must not be dropped from the comparison
        # merely because a later row states the same label: before the duplicate was
        # rejected, this file passed with the stale class silently discarded.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            docs = root / DOCS_LEDGER
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
            ledger = root / SITE_LEDGER
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

    def test_a_spread_capability_entry_fails_instead_of_reporting_agreement(self) -> None:
        # The spread renders on the site and was invisible to the guard, which then
        # reported agreement: the rows it held were never in `compare_rows`. This is
        # the defect the check exists to prevent, so the file must fail with the
        # spread's line rather than pass.
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy(Path(temporary))
            ledger = root / SITE_LEDGER
            mutated = ledger.read_text(encoding="utf-8").replace(
                "const capabilityRows: readonly CapabilityRow[] = [\n",
                "const capabilityRows: readonly CapabilityRow[] = [\n  ...hostedRows,\n",
            )
            # The expected line is derived from the mutated text: a blank line added
            # above the declaration moves the spread, and the guard is still right.
            expected = mutated[: mutated.index("...hostedRows")].count("\n") + 1
            ledger.write_text(mutated, encoding="utf-8")
            code, stderr = self.run_against(root)
        self.assertEqual(code, 2)
        self.assertIn(f"line {expected}", stderr)
        self.assertIn("hostedRows", stderr)


if __name__ == "__main__":
    unittest.main()
