#!/usr/bin/env python3
"""Export the mounted API OpenAPI contract deterministically for P6."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = create_app().openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote OpenAPI snapshot to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
