#!/usr/bin/env python3
"""Compare committed benchmark-data.json with the workflow artifact."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_published_data import fail, load_payload, resolve_benchmark_data_path  # noqa: E402

COMMITTED_PATH = "web/public/benchmarks/benchmark-data.json"
ARTIFACT_PATH = "benchmarks/output/benchmark-data.json"


def main() -> int:
    committed = load_payload(resolve_benchmark_data_path(COMMITTED_PATH))
    artifact = load_payload(resolve_benchmark_data_path(ARTIFACT_PATH))
    if committed != artifact:
        fail(
            "web/public/benchmarks/benchmark-data.json was edited on this PR "
            "but does not match the workflow artifact. Remove manual edits and let "
            "publish-benchmark-data update the file."
        )
    print("Committed benchmark data matches workflow artifact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
