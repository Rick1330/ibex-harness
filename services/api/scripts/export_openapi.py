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

# Snapshot exports land in the services/api tree (the committed contract) or
# the system temp directory (check-openapi-snapshot.sh scratch file). Within
# the repo only the canonical snapshot file is writable; resolving and
# checking against those roots keeps a crafted CLI path from writing
# elsewhere (S8707).
_REPO_SNAPSHOT = (REPO_ROOT / "services" / "api" / "openapi.snapshot.json").resolve()
_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def resolve_output_path(raw: Path | str) -> Path:
    resolved = Path(raw).resolve()
    if resolved == _REPO_SNAPSHOT or resolved.is_relative_to(_TEMP_ROOT):
        return resolved
    raise SystemExit(
        f"output path must be {_REPO_SNAPSHOT} or inside the temp directory {_TEMP_ROOT}"
    )


def main() -> int:
    from app.main import create_app  # noqa: PLC0415 — heavy import only for real exports

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
