"""The guard's command line: argv handling, the report, and the exit code.

Exit 1 on drift, 2 when a surface cannot be read or parsed, 0 otherwise. The
interface is unchanged from the single-file version of this guard, because
``.github/workflows/ci.yml`` and ``dev-tool.sh`` invoke it by path and read both
the exit code and the stderr text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .collect import collect
from .compare import compare_capabilities, compare_rows
from .contract import ROOT, SURFACES, InputError


def main(argv: list[str] | None = None, description: str | None = None) -> int:
    """Run the guard over a checkout and return its exit code."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)

    try:
        rows_by_surface, site_vocabulary, vocabulary_problems = collect(args.root)
    except InputError as error:
        print(f"check-status-vocabulary: {error}", file=sys.stderr)
        return 2

    class_surfaces = frozenset(surface.key for surface in SURFACES if surface.states_ledger_class)
    problems = [
        *vocabulary_problems,
        *compare_capabilities(rows_by_surface, site_vocabulary, class_surfaces),
        *compare_rows(rows_by_surface),
    ]
    if problems:
        print(f"check-status-vocabulary: {len(problems)} disagreement(s)", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(
        "check-status-vocabulary: the four surfaces state one vocabulary and "
        "one status per capability"
    )
    return 0
