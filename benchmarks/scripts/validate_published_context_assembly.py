#!/usr/bin/env python3
"""Validate published context-assembly stub benchmark JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

import published_suite_validate

SCRIPT_NAME = "validate_published_context_assembly"
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data-schema/context-assembly-benchmark-data.schema.json"
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Require jsonschema to be installed")
    parser.add_argument("path", help="Workspace-relative path to published JSON")
    args = parser.parse_args(argv)

    path = published_suite_validate.resolve_published_data_path(
        args.path, data_name="context-assembly-benchmark-data.json", script_name=SCRIPT_NAME,
    )
    if args.strict and published_suite_validate.jsonschema is None:
        published_suite_validate.fail(SCRIPT_NAME, "jsonschema is required in strict mode")
    published_suite_validate.validate_published_payload(path, _SCHEMA_PATH, script_name=SCRIPT_NAME)


if __name__ == "__main__":
    main()
