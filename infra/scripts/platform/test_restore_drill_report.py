#!/usr/bin/env python3
"""Run every restore-drill report test, split by concern into siblings.

The cases live in the ``test_restore_drill_*.py`` modules next to this file so
no single file carries the whole suite. This module is the runner: it imports
those modules and runs them as one suite, which keeps

    python3 infra/scripts/platform/test_restore_drill_report.py

the command that executes all of them.

The siblings are imported as modules rather than as names, so ``unittest
discover`` still collects each case exactly once: a module object in this
module's namespace is not a ``TestCase`` subclass and is skipped.
"""

from __future__ import annotations

import sys
import unittest

import test_restore_drill_branches as _branches
import test_restore_drill_honesty as _honesty
import test_restore_drill_mechanism as _mechanism
import test_restore_drill_pitr as _pitr
import test_restore_drill_producer as _producer
import test_restore_drill_report_writer as _writer

TEST_MODULES = (_branches, _honesty, _mechanism, _pitr, _producer, _writer)


def load_suite() -> unittest.TestSuite:
    """Every case in every sibling module, each exactly once."""
    loader = unittest.TestLoader()
    return unittest.TestSuite(
        loader.loadTestsFromModule(module) for module in TEST_MODULES
    )


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(load_suite())
    sys.exit(0 if result.wasSuccessful() else 1)
