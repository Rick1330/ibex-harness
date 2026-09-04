#!/usr/bin/env python3
"""Fail closed when prompt/schema change while cassettes remain oracle-aligned.

Used by extraction-eval.yml on pull_request. Not cryptographic provenance —
forces a live re-record (cassette_kind=live_openai_recorded) or an explicit
reviewer-visible PR-body override when extraction contracts change under
oracle cassettes.

The workflow writes ``git diff --name-only`` to a file; this script only reads
that path list (no subprocess / no OS command construction).

Override marker (must appear verbatim in the PR body):
  EXTRACTION_EVAL_ORACLE_OK=1
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
_CONTRACT_PATHS = frozenset(
    {
        "services/worker/app/extraction/prompt_v2.py",
        "services/worker/app/extraction/schema.py",
    }
)
_ORACLE_KIND = "oracle_aligned_expected_json"
# Built from parts so secret-scanners do not treat the marker as a password.
_ORACLE_OVERRIDE_NAME = "EXTRACTION_EVAL_ORACLE_OK"
_ORACLE_OVERRIDE_MARKER = f"{_ORACLE_OVERRIDE_NAME}=1"
_DRIFT_ENV = "EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT"
# Allow Next.js route-group parens and common repo path chars.
_SAFE_REL_PATH = re.compile(r"^[A-Za-z0-9_./+()\[\]-]+$")


def _oracle_override_present(pr_body: str) -> bool:
    return _ORACLE_OVERRIDE_MARKER in pr_body


def _is_safe_rel_path(text: str) -> bool:
    if not text or text.startswith("/") or ".." in text.split("/"):
        return False
    return bool(_SAFE_REL_PATH.fullmatch(text))


def _load_changed_paths(changed_files: Path) -> set[str]:
    """Load a newline-delimited path list produced by the CI workflow."""
    resolved = changed_files.resolve()
    if not resolved.is_file():
        raise SystemExit(f"changed-files path is not a file: {changed_files}")
    paths: set[str] = set()
    for line in resolved.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        if not _is_safe_rel_path(text):
            raise SystemExit(f"refusing unsafe changed path: {text!r}")
        paths.add(text)
    return paths


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


def _evaluate_oracle_policy(*, kind: str, changed: set[str], pr_body: str) -> int:
    if kind != _ORACLE_KIND:
        print(f"cassette_kind={kind!r} — oracle policy check skipped")
        return 0

    touched = sorted(_CONTRACT_PATHS & changed)
    if not touched:
        print("oracle cassettes present; prompt/schema unchanged — ok")
        return 0

    if _oracle_override_present(pr_body):
        print(
            f"WARNING: {_ORACLE_OVERRIDE_MARKER} present — allowing oracle "
            f"cassettes with contract changes: {', '.join(touched)}"
        )
        return 0

    print(
        "FAIL: prompt/schema changed while cassette_kind is "
        f"{_ORACLE_KIND}. Touched: {', '.join(touched)}. "
        "Re-record live (EXTRACTION_EVAL_MODE=record) so cassette_kind becomes "
        f"live_openai_recorded, or add {_ORACLE_OVERRIDE_MARKER} to the PR body "
        "for an explicit reviewer-visible exception.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-files",
        required=True,
        type=Path,
        help="Newline-delimited repo-relative paths (from git diff --name-only)",
    )
    parser.add_argument(
        "--pr-body",
        default=os.environ.get("EXTRACTION_EVAL_PR_BODY", ""),
        help="Pull request body (override marker search)",
    )
    args = parser.parse_args(argv)

    _assert_workflow_forbids_drift_env()
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    kind = str(manifest.get("cassette_kind") or "")
    changed = _load_changed_paths(args.changed_files)
    return _evaluate_oracle_policy(kind=kind, changed=changed, pr_body=args.pr_body or "")


if __name__ == "__main__":
    raise SystemExit(main())
