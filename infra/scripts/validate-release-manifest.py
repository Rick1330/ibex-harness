#!/usr/bin/env python3
"""Validate a generated release manifest against the published JSON schema.

The release workflow runs this between generating ``release-manifest.json`` and
uploading it, so a manifest that does not conform fails the release instead of
being published. ``jsonschema`` is pinned by
``infra/scripts/release-manifest-test-requirements.txt``; run this script with
that requirement set:

    uv run --no-project --no-build \
      --with-requirements infra/scripts/release-manifest-test-requirements.txt \
      python3 infra/scripts/validate-release-manifest.py release-manifest.json

The manifest and schema paths must resolve inside this checkout, the same rule
``release-manifest.py`` applies to its own path arguments; a manifest staged
elsewhere has to be copied in first.

Format assertions are enabled: the schema declares ``format: date-time`` on
``generated_at``, and a validator built without a format checker treats that
keyword as an annotation, so ``"not-a-timestamp"`` would pass. The checker is a
no-op unless the optional ``rfc3339-validator`` wheel is installed, which is why
it is pinned in the requirement file alongside ``jsonschema``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "release-manifest.schema.json"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _contained_path(raw: str) -> Path:
    """Resolve a CLI path and refuse anything outside this checkout.

    The manifest is generated into the checkout by the release workflow, so the
    only legitimate inputs live there. Resolving first means a relative path, a
    symlink pointing out of the tree, and an absolute path outside it are all
    judged by where they land, not by how they are spelled.
    """
    resolved = Path(raw).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        msg = f"{raw} must resolve inside {REPO_ROOT}"
        raise ValueError(msg)
    return resolved


def _load(path: Path) -> Any:
    """Read one JSON document, reporting parse and I/O failures as ValueError."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"cannot read {path}: {exc}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc}"
        raise ValueError(msg) from exc


def _location(error: jsonschema.ValidationError) -> str:
    parts = [str(part) for part in error.absolute_path]
    return "/".join(parts) if parts else "<root>"


def _errors(schema: Any, manifest: Any) -> list[jsonschema.ValidationError]:
    # Passing the checker is what turns `format` from an annotation into an
    # assertion. Without it `generated_at: "not-a-timestamp"` validates and the
    # release publishes a manifest whose timestamp means nothing.
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    return sorted(
        validator.iter_errors(manifest),
        key=lambda error: [str(part) for part in error.absolute_path],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="path to the generated release manifest")
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    args = parser.parse_args(argv)

    try:
        schema_path = _contained_path(args.schema)
        schema = _load(schema_path)
        manifest = _load(_contained_path(args.manifest))
        errors = _errors(schema, manifest)
    except ValueError as exc:
        print(f"release-manifest: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(
                f"release-manifest: {_location(error)}: {error.message}",
                file=sys.stderr,
            )
        print(
            f"release-manifest: {args.manifest} does not conform to {schema_path.name}",
            file=sys.stderr,
        )
        return 1

    print(f"release-manifest: {args.manifest} conforms to {schema_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
