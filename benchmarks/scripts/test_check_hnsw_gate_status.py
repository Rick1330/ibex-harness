#!/usr/bin/env python3
"""Tests for check_hnsw_gate_status.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "check_hnsw_gate_status",
    _SCRIPTS / "check_hnsw_gate_status.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load check_hnsw_gate_status")
check_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["check_hnsw_gate_status"] = check_mod
_SPEC.loader.exec_module(check_mod)


def _published_payload(*, status: str, recall: float = 1.0) -> dict:
    return {
        "schema_version": 1,
        "benchmark": "hnsw_recall_latency",
        "runs": [
            {
                "sha": "abc123def456",
                "short_sha": "abc123d",
                "status": status,
                "gate_summary": {
                    "recall_ok": status == "pass",
                    "recall_floor": 0.98,
                    "worst_recall_at_10": recall,
                    "has_1m": False,
                    "note": "test fixture",
                },
            }
        ],
    }


class CheckHnswGateStatusTests(unittest.TestCase):
    def test_pass_status_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hnsw-benchmark-data.json"
            path.write_text(json.dumps(_published_payload(status="pass")), encoding="utf-8")
            rc = check_mod.check_gate_status(path, sha="abc123def456")
            self.assertEqual(rc, 0)

    def test_fail_status_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hnsw-benchmark-data.json"
            path.write_text(
                json.dumps(_published_payload(status="fail", recall=0.5)),
                encoding="utf-8",
            )
            rc = check_mod.check_gate_status(path, sha="abc123def456")
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
