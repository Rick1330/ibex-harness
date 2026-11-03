#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TEST_MODULES = (
    "test_benchmark_ingest",
    "test_regression_gate",
    "test_build_benchmark_data",
    "test_validate_published_data",
    "test_go_bench_gate",
)


def main() -> int:
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
