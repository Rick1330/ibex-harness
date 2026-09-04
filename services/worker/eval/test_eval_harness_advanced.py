"""Advanced eval harness tests: prompt drift, published merge, cassette integrity."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_WORKER = _DIR.parent
if str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))

import build_published
import run_eval
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH


class PromptManifestTests(unittest.TestCase):
    def test_committed_manifest_matches_live_prompt(self) -> None:
        manifest = json.loads(
            (_DIR / "gold_set" / "v1" / "cassette_manifest.json").read_text(encoding="utf-8")
        )
        expected = hashlib.sha256(EXTRACTION_SYSTEM_PROMPT_BATCH.encode()).hexdigest()
        self.assertEqual(manifest["prompt_sha256"], expected)
        self.assertGreaterEqual(int(manifest["conversation_count"]), 100)

    def test_cassette_count_matches_conversations(self) -> None:
        gold = _DIR / "gold_set" / "v1"
        convs = [
            ln
            for ln in gold.joinpath("conversations.jsonl").read_text().splitlines()
            if ln.strip()
        ]
        cassettes = [
            ln
            for ln in gold.joinpath("openai_cassettes.jsonl").read_text().splitlines()
            if ln.strip()
        ]
        self.assertEqual(len(convs), len(cassettes))
        ids_c = {json.loads(ln)["conversation_id"] for ln in convs}
        ids_k = {json.loads(ln)["conversation_id"] for ln in cassettes}
        self.assertEqual(ids_c, ids_k)


class BuildPublishedTests(unittest.TestCase):
    def test_merge_prepends_and_dedupes_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            published = Path(tmp) / "extraction-quality-benchmark-data.json"
            latest = {
                "gold_set": "v1",
                "conversation_count": 125,
                "provider": "openai",
                "enforcement": "ci",
                "mode": "cassette",
                "model": "gpt-4o-mini",
                "metrics": {
                    "precision_macro": 1.0,
                    "recall_macro": 1.0,
                    "category_assignment_accuracy": 1.0,
                    "temporal_field_accuracy": 1.0,
                    **{
                        f"{k}_{c}": 1.0
                        for c in (
                            "factual",
                            "preference",
                            "behavioral",
                            "episodic",
                            "procedural",
                        )
                        for k in ("precision", "recall")
                    },
                },
            }
            gate = {"status": "pass", "checks": []}
            entry = build_published.build_entry(
                latest,
                gate,
                sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                branch="main",
                run_number=1,
                run_url="https://example/runs/1",
            )
            build_published.merge_run(published, entry, entry["sha"])
            entry2 = build_published.build_entry(
                latest,
                gate,
                sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                branch="main",
                run_number=2,
                run_url="https://example/runs/2",
            )
            build_published.merge_run(published, entry2, entry2["sha"])
            data = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual(data["benchmark"], "extraction_quality")
            self.assertEqual(len(data["runs"]), 1)
            self.assertEqual(data["runs"][0]["run_number"], 2)

    def test_merge_rejects_wrong_benchmark_and_main_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "extraction-quality-benchmark-data.json"
            bad.write_text(
                json.dumps({"schema_version": 1, "benchmark": "other", "runs": []}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                build_published.merge_run(bad, {"sha": "b" * 40}, "b" * 40)

            latest = Path(tmp) / "latest.json"
            gate = Path(tmp) / "gate.json"
            published = Path(tmp) / "extraction-quality-benchmark-data.json"
            latest.write_text(
                json.dumps(
                    {
                        "metrics": {
                            "precision_macro": 1.0,
                            "recall_macro": 1.0,
                            "category_assignment_accuracy": 1.0,
                            "temporal_field_accuracy": 1.0,
                        },
                        "conversation_count": 1,
                    }
                ),
                encoding="utf-8",
            )
            gate.write_text(json.dumps({"status": "fail", "checks": []}), encoding="utf-8")
            published.unlink(missing_ok=True)
            self.assertEqual(
                build_published.main(
                    [
                        "--latest",
                        str(latest),
                        "--gate",
                        str(gate),
                        "--published",
                        str(published),
                        "--sha",
                        "c" * 40,
                        "--run-number",
                        "9",
                    ]
                ),
                0,
            )
            data = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual(data["runs"][0]["status"], "fail")
            self.assertEqual(
                build_published.main(
                    [
                        "--latest",
                        str(latest),
                        "--gate",
                        str(gate),
                        "--published",
                        str(Path(tmp) / "wrong-name.json"),
                        "--sha",
                        "c" * 40,
                    ]
                ),
                1,
            )


class RunEvalCassetteSmokeTests(unittest.TestCase):
    def test_cassette_eval_reaches_perfect_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_eval.OUTPUT_DIR = out
            run_eval.LATEST_PATH = out / "latest.json"
            report = run_eval.run_eval(mode="cassette", provider="openai")
            self.assertEqual(report["enforcement"], "ci")
            self.assertEqual(report["provider"], "openai")
            for name, value in report["metrics"].items():
                self.assertGreaterEqual(value, 0.999, msg=name)


if __name__ == "__main__":
    unittest.main()
