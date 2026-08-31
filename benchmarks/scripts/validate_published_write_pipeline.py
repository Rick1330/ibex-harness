#!/usr/bin/env python3
"""Validate published write-pipeline-benchmark-data.json."""

from __future__ import annotations

import sys
from pathlib import Path

from published_suite_validate import (
    fail,
    resolve_published_data_path,
    validate_published_payload,
)

SCRIPT_NAME = "validate_published_write_pipeline"
DATA_NAME = "write-pipeline-benchmark-data.json"
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data-schema"
    / "write-pipeline-benchmark-data.schema.json"
)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        fail(SCRIPT_NAME, f"usage: {SCRIPT_NAME}.py <path>")
    path = resolve_published_data_path(args[0], data_name=DATA_NAME, script_name=SCRIPT_NAME)
    validate_published_payload(path, _SCHEMA_PATH, script_name=SCRIPT_NAME)


if __name__ == "__main__":
    main()
