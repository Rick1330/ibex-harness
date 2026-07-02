#!/usr/bin/env python3
import json
import shutil
import sys
from pathlib import Path

RUNS_JSON = "runs.json"
BASELINE_JSON = "baseline.json"
METADATA_JSON = "metadata.json"
BRAND_SRC = Path("docs/app/public/brand")
BRAND_MARKS = ("ibex-mark-light.png", "ibex-mark-dark.png")


def sync_brand_assets(site_out: Path) -> None:
    brand_out = site_out / "brand"
    brand_out.mkdir(parents=True, exist_ok=True)
    for name in BRAND_MARKS:
        src = BRAND_SRC / name
        if not src.exists():
            bundled = Path("benchmarks/site/brand") / name
            if bundled.exists():
                shutil.copy2(bundled, brand_out / name)
            continue
        shutil.copy2(src, brand_out / name)


def copy_tree(src: Path, dest: Path) -> None:
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main():
    out = Path("benchmarks/output")
    site_src = Path("benchmarks/site")
    site_out = out / "site"
    data_out = site_out / "data"
    site_out.mkdir(parents=True, exist_ok=True)
    data_out.mkdir(parents=True, exist_ok=True)

    copy_tree(site_src, site_out)
    sync_brand_assets(site_out)
    (site_out / ".nojekyll").touch()

    shutil.copy2(out / RUNS_JSON, data_out / RUNS_JSON)
    shutil.copy2(Path("benchmarks/data-schema/baseline.json"), data_out / BASELINE_JSON)
    metadata = {
        "schema_version": 2,
        "description": "IBEX benchmark dashboard metadata",
        "theme": "matte-graphite",
    }
    (data_out / METADATA_JSON).write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    required = [
        site_out / "index.html",
        site_out / ".nojekyll",
        site_out / "trends.html",
        site_out / "waterfall.html",
        site_out / "load.html",
        site_out / "commits.html",
        site_out / "brand/ibex-mark-light.png",
        site_out / "brand/ibex-mark-dark.png",
        site_out / "bench-common.js",
        site_out / "bench-pages.js",
        site_out / "theme.js",
        site_out / "shell.js",
        data_out / RUNS_JSON,
        data_out / BASELINE_JSON,
        data_out / METADATA_JSON,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"missing required files: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
