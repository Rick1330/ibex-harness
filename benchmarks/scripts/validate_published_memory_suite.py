#!/usr/bin/env python3
"""Validate published memory-suite benchmark JSON (ranking-quality, write-pipeline)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from published_suite_validate import (
    fail,
    resolve_published_data_path,
    validate_published_payload,
)

SCRIPT_NAME = "validate_published_memory_suite"
_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "data-schema"

SUITES: dict[str, tuple[str, Path]] = {
    "ranking_quality": (
        "ranking-quality-benchmark-data.json",
        _SCHEMA_DIR / "ranking-quality-benchmark-data.schema.json",
    ),
    "write_pipeline": (
        "write-pipeline-benchmark-data.json",
        _SCHEMA_DIR / "write-pipeline-benchmark-data.schema.json",
    ),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        required=True,
        choices=sorted(SUITES),
        help="Memory quality suite to validate",
    )
    parser.add_argument("path", help="Workspace-relative path to published JSON")
    args = parser.parse_args(argv)

    data_name, schema_path = SUITES[args.suite]
    path = resolve_published_data_path(args.path, data_name=data_name, script_name=SCRIPT_NAME)
    validate_published_payload(path, schema_path, script_name=SCRIPT_NAME)


if __name__ == "__main__":
    main()
