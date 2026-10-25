#!/usr/bin/env python3
"""Export the mounted API OpenAPI contract deterministically for P6."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from app.main import create_app

# Snapshot exports land in the services/api tree (the committed contract) or
# the system temp directory (check-openapi-snapshot.sh scratch file). Resolving
# and prefix-checking keeps a crafted CLI path from writing elsewhere (S8707).
_ALLOWED_OUTPUT_ROOTS = (
    (REPO_ROOT / "services" / "api").resolve(),
    Path(tempfile.gettempdir()).resolve(),
)


def resolve_output_path(raw: Path | str) -> Path:
    resolved = Path(raw).resolve()
    if not any(resolved == root or resolved.is_relative_to(root) for root in _ALLOWED_OUTPUT_ROOTS):
        allowed = ", ".join(str(root) for root in _ALLOWED_OUTPUT_ROOTS)
        raise SystemExit(f"output path must resolve inside one of: {allowed}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = resolve_output_path(args.output)
    document = create_app().openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote OpenAPI snapshot to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
