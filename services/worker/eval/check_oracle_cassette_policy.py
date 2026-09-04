#!/usr/bin/env python3
"""Fail closed when prompt/schema change while cassettes remain oracle-aligned.

Used by extraction-eval.yml on pull_request. Not cryptographic provenance —
forces a live re-record (cassette_kind=live_openai_recorded) or an explicit
reviewer-visible PR-body override when extraction contracts change under
oracle cassettes.

Override token (must appear verbatim in the PR body):
  EXTRACTION_EVAL_ORACLE_OK=1
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = (
    _REPO_ROOT
    / "services"
    / "worker"
    / "eval"
    / "gold_set"
    / "v1"
    / "cassette_manifest.json"
)
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "extraction-eval.yml"
_CONTRACT_PATHS = (
    "services/worker/app/extraction/prompt_v2.py",
    "services/worker/app/extraction/schema.py",
)
_ORACLE_KIND = "oracle_aligned_expected_json"
_OVERRIDE_TOKEN = "EXTRACTION_EVAL_ORACLE_OK=1"
_DRIFT_ENV = "EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT"


def _git_changed_paths(base: str, head: str) -> set[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _assert_workflow_forbids_drift_env() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _DRIFT_ENV in line:
            raise SystemExit(
                f"{_WORKFLOW.relative_to(_REPO_ROOT)}:{i}: must not set "
                f"{_DRIFT_ENV} in CI (local-only escape hatch)"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR base SHA")
    parser.add_argument("--head", required=True, help="PR head SHA")
    parser.add_argument(
        "--pr-body",
        default=os.environ.get("EXTRACTION_EVAL_PR_BODY", ""),
        help="Pull request body (override token search)",
    )
    args = parser.parse_args(argv)

    _assert_workflow_forbids_drift_env()

    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    kind = str(manifest.get("cassette_kind") or "")
    if kind != _ORACLE_KIND:
        print(f"cassette_kind={kind!r} — oracle policy check skipped")
        return 0

    changed = _git_changed_paths(args.base, args.head)
    touched = sorted(p for p in _CONTRACT_PATHS if p in changed)
    if not touched:
        print("oracle cassettes present; prompt/schema unchanged — ok")
        return 0

    if _OVERRIDE_TOKEN in (args.pr_body or ""):
        print(
            f"WARNING: {_OVERRIDE_TOKEN} present — allowing oracle cassettes with "
            f"contract changes: {', '.join(touched)}"
        )
        return 0

    print(
        "FAIL: prompt/schema changed while cassette_kind is "
        f"{_ORACLE_KIND}. Touched: {', '.join(touched)}. "
        "Re-record live (EXTRACTION_EVAL_MODE=record) so cassette_kind becomes "
        f"live_openai_recorded, or add {_OVERRIDE_TOKEN} to the PR body for an "
        "explicit reviewer-visible exception.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
