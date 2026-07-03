#!/usr/bin/env python3
"""Reject manual benchmark-data.json edits that do not match the CI artifact."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_published_data import fail, load_payload, resolve_benchmark_data_path  # noqa: E402

COMMITTED_PATH = "docs/app/public/benchmarks/benchmark-data.json"
ARTIFACT_PATH = "benchmarks/output/benchmark-data.json"
BOT_EMAILS = frozenset(
    {
        "41898282+github-actions[bot]@users.noreply.github.com",
        "github-actions[bot]@users.noreply.github.com",
    }
)


def git_diff_quiet(base_ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", f"origin/{base_ref}...HEAD", "--", path],
        check=False,
    )
    return result.returncode == 0


def last_commit_email(path: str) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ae", "--", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    base_ref = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not base_ref:
        fail("usage: verify_pr_benchmark_integrity.py <base-ref>")

    subprocess.run(["git", "fetch", "origin", base_ref], check=True)

    if git_diff_quiet(base_ref, COMMITTED_PATH):
        print("benchmark-data.json unchanged on branch; publish will apply the workflow artifact.")
        return 0

    author = last_commit_email(COMMITTED_PATH)
    if author in BOT_EMAILS:
        print("Benchmark data last updated by CI; publish may refresh it for this run.")
        return 0

    committed = load_payload(resolve_benchmark_data_path(COMMITTED_PATH))
    artifact = load_payload(resolve_benchmark_data_path(ARTIFACT_PATH))
    if committed != artifact:
        fail(
            "docs/app/public/benchmarks/benchmark-data.json was edited on this PR "
            "but does not match the workflow artifact. Remove manual edits and let "
            "publish-benchmark-data update the file."
        )

    print("Committed benchmark data matches workflow artifact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
