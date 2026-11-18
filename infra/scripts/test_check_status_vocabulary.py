#!/usr/bin/env python3
"""Run every status-vocabulary test, split by subject into siblings.

The cases live in the ``test_status_vocabulary_*.py`` modules beside this file, so
no single file carries the whole suite: reading a surface and comparing four of
them are different subjects, and the guard itself is split along the same seams.
This module is the runner, which keeps

    python3 infra/scripts/test_check_status_vocabulary.py

the command that executes all of them, and ``python3 -m unittest`` over this file
collects the whole suite through the ``load_tests`` protocol.

The suite is discovered by the shared file prefix rather than imported by name.
Discovery puts this directory on ``sys.path`` before it imports a module, which is
what lets each sibling import the guard package beside it, and it collects every
sibling exactly once.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PATTERN = "test_status_vocabulary_*.py"
VERBOSE_FLAGS = frozenset({"-v", "--verbose"})


def load_suite() -> unittest.TestSuite:
    """Every sibling module's cases, discovered beside this file."""
    directory = Path(__file__).resolve().parent
    return unittest.TestLoader().discover(start_dir=str(directory), pattern=PATTERN)


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """The sibling modules' cases `python3 -m unittest <this file>` collects (77 cases today).

    This module defines no case of its own, so the default collection finds none;
    the protocol is how a runner module hands unittest the suite instead.
    """
    return load_suite()


def main(argv: list[str] | None = None) -> int:
    """Run the suite, honouring the verbose flag `unittest.main` would parse."""
    args = sys.argv[1:] if argv is None else argv
    verbosity = 2 if VERBOSE_FLAGS & set(args) else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(load_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
