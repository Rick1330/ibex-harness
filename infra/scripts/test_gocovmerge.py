"""Unit tests for infra/scripts/gocovmerge.py (_merge semantics)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().with_name("gocovmerge.py")
_SPEC = importlib.util.spec_from_file_location("gocovmerge", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
gocovmerge = importlib.util.module_from_spec(_SPEC)
sys.modules["gocovmerge"] = gocovmerge
_SPEC.loader.exec_module(gocovmerge)


def _write_profile(path: Path, mode: str, rows: list[str]) -> Path:
    path.write_text("mode: " + mode + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


class MergeTests(unittest.TestCase):
    def test_merge_set_mode_or_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_profile(
                root / "a.out",
                "set",
                ["foo.go:1.1,2.1 1 1", "foo.go:3.1,4.1 1 0"],
            )
            b = _write_profile(
                root / "b.out",
                "set",
                ["foo.go:1.1,2.1 1 0", "foo.go:3.1,4.1 1 1", "foo.go:5.1,6.1 1 1"],
            )
            mode, blocks = gocovmerge._merge([a, b])
            self.assertEqual(mode, "set")
            self.assertEqual(blocks["foo.go:1.1,2.1"], (1, 1))
            self.assertEqual(blocks["foo.go:3.1,4.1"], (1, 1))
            self.assertEqual(blocks["foo.go:5.1,6.1"], (1, 1))

    def test_merge_count_sums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_profile(root / "a.out", "count", ["foo.go:1.1,2.1 2 3"])
            b = _write_profile(root / "b.out", "count", ["foo.go:1.1,2.1 2 4"])
            mode, blocks = gocovmerge._merge([a, b])
            self.assertEqual(mode, "count")
            self.assertEqual(blocks["foo.go:1.1,2.1"], (2, 7))

    def test_merge_atomic_sums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_profile(root / "a.out", "atomic", ["foo.go:1.1,2.1 2 3"])
            b = _write_profile(root / "b.out", "atomic", ["foo.go:1.1,2.1 2 4"])
            mode, blocks = gocovmerge._merge([a, b])
            self.assertEqual(mode, "atomic")
            self.assertEqual(blocks["foo.go:1.1,2.1"], (2, 7))

    def test_merge_mode_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_profile(root / "a.out", "set", ["foo.go:1.1,2.1 1 1"])
            b = _write_profile(root / "b.out", "count", ["foo.go:1.1,2.1 1 1"])
            with self.assertRaisesRegex(SystemExit, "mode mismatch"):
                gocovmerge._merge([a, b])

    def test_merge_missing_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.out"
            bad.write_text("foo.go:1.1,2.1 1 1\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "missing mode"):
                gocovmerge._merge([bad])

    def test_merge_empty_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.out"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "empty"):
                gocovmerge._merge([empty])

    def test_merge_no_profiles(self) -> None:
        with self.assertRaisesRegex(SystemExit, "no cover profiles"):
            gocovmerge._merge([])

    def test_merge_statement_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_profile(root / "a.out", "count", ["foo.go:1.1,2.1 1 1"])
            b = _write_profile(root / "b.out", "count", ["foo.go:1.1,2.1 2 1"])
            with self.assertRaisesRegex(SystemExit, "statement count mismatch"):
                gocovmerge._merge([a, b])

    def test_merge_malformed_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.out"
            bad.write_text("mode: set\nnot-a-valid-block\n", encoding="utf-8")
            with self.assertRaises((SystemExit, ValueError)):
                gocovmerge._merge([bad])


if __name__ == "__main__":
    unittest.main()
