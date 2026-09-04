"""Advanced eval harness tests: prompt drift, published merge, cassette integrity."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_DIR = Path(__file__).resolve().parent
_WORKER = _DIR.parent
if str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))

import build_published
import check_oracle_cassette_policy as oracle_policy
import path_guard
import run_eval
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from build_published import RunMeta


class PromptManifestTests(unittest.TestCase):
    def test_committed_manifest_matches_live_prompt(self) -> None:
        manifest = json.loads(
            (_DIR / "gold_set" / "v1" / "cassette_manifest.json").read_text(encoding="utf-8")
        )
        expected = hashlib.sha256(EXTRACTION_SYSTEM_PROMPT_BATCH.encode()).hexdigest()
        self.assertEqual(manifest["prompt_sha256"], expected)
        self.assertEqual(manifest["schema_sha256"], run_eval._schema_sha256())
        self.assertIn(
            manifest["cassette_kind"],
            {run_eval.CASSETTE_KIND_ORACLE, run_eval.CASSETTE_KIND_LIVE},
        )
        self.assertGreaterEqual(int(manifest["conversation_count"]), 100)
        for key in (
            "conversations_sha256",
            "expected_memories_sha256",
            "cassettes_sha256",
            "prompt_sha256",
            "schema_sha256",
        ):
            self.assertEqual(len(manifest[key]), 64)

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
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
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
                RunMeta(
                    sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    branch="main",
                    run_number=1,
                    run_url="https://example/runs/1",
                ),
            )
            build_published.merge_run(published, entry, entry["sha"])
            entry2 = build_published.build_entry(
                latest,
                gate,
                RunMeta(
                    sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    branch="main",
                    run_number=2,
                    run_url="https://example/runs/2",
                ),
            )
            build_published.merge_run(published, entry2, entry2["sha"])
            data = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual(data["benchmark"], "extraction_quality")
            self.assertEqual(len(data["runs"]), 1)
            self.assertEqual(data["runs"][0]["run_number"], 2)

    def test_merge_sorts_newest_first_regardless_of_input_order(self) -> None:
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            published = Path(tmp) / "extraction-quality-benchmark-data.json"
            older = {
                "sha": "a" * 40,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "run_number": 1,
            }
            newer = {
                "sha": "b" * 40,
                "timestamp": "2026-06-01T00:00:00+00:00",
                "run_number": 2,
            }
            published.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "benchmark": "extraction_quality",
                        "runs": [older],
                    }
                ),
                encoding="utf-8",
            )
            build_published.merge_run(published, newer, newer["sha"])
            # Reverse-order seed then merge should still emit newest-first.
            data = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual([r["sha"] for r in data["runs"]], ["b" * 40, "a" * 40])

            published.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "benchmark": "extraction_quality",
                        "runs": [newer, older],
                    }
                ),
                encoding="utf-8",
            )
            mid = {
                "sha": "c" * 40,
                "timestamp": "2026-03-01T00:00:00+00:00",
                "run_number": 3,
            }
            build_published.merge_run(published, mid, mid["sha"])
            data = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual(
                [r["timestamp"] for r in data["runs"]],
                [
                    "2026-06-01T00:00:00+00:00",
                    "2026-03-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ],
            )

    def test_path_guard_rejects_escape_and_wrong_basename(self) -> None:
        with self.assertRaises(path_guard.UnsafePathError):
            path_guard.resolve_published_extraction_path("../etc/passwd")
        with self.assertRaises(path_guard.UnsafePathError):
            path_guard.resolve_published_extraction_path("wrong-name.json")
        with self.assertRaises(path_guard.UnsafePathError):
            path_guard.resolve_workspace_path("  ")
        with self.assertRaises(path_guard.UnsafePathError):
            path_guard.resolve_latest_path("missing-latest.json")

    def test_main_rejects_unsafe_published_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            latest = Path(tmp) / "latest.json"
            gate = Path(tmp) / "gate-result.json"
            latest.write_text(json.dumps({"metrics": {}}), encoding="utf-8")
            gate.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            self.assertEqual(
                build_published.main(
                    [
                        "--latest",
                        str(latest),
                        "--gate",
                        str(gate),
                        "--published",
                        str(Path(tmp) / ".." / "wrong-name.json"),
                        "--sha",
                        "d" * 40,
                    ]
                ),
                1,
            )
    def test_merge_rejects_wrong_benchmark_and_main_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            bad = Path(tmp) / "extraction-quality-benchmark-data.json"
            bad.write_text(
                json.dumps({"schema_version": 1, "benchmark": "other", "runs": []}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                build_published.merge_run(bad, {"sha": "b" * 40}, "b" * 40)

            latest = Path(tmp) / "latest.json"
            gate = Path(tmp) / "gate-result.json"
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
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            out = Path(tmp)
            original_out = run_eval.OUTPUT_DIR
            original_latest = run_eval.LATEST_PATH
            self.addCleanup(setattr, run_eval, "OUTPUT_DIR", original_out)
            self.addCleanup(setattr, run_eval, "LATEST_PATH", original_latest)
            run_eval.OUTPUT_DIR = out
            run_eval.LATEST_PATH = out / "latest.json"
            report = run_eval.run_eval(mode="cassette", provider="openai")
            self.assertEqual(report["enforcement"], "ci")
            self.assertEqual(report["provider"], "openai")
            for name, value in report["metrics"].items():
                self.assertGreaterEqual(value, 0.999, msg=name)

    def test_cassette_eval_detects_corrupted_predictions_end_to_end(self) -> None:
        """Full run_eval cassette path must score an injected miss analytically.

        Mutation (documented, fixed):
          - Copy committed gold_set/v1 into a temp gold_dir.
          - Empty memories for conversation ``c001`` only (oracle cassette had
            one factual memory on turn 0; gold expected has 130 memories total,
            of which 33 are factual label occurrences).
        Expected deltas from a perfect (all-1.0) oracle baseline:
          - recall_factual = 32/33
          - category_assignment_accuracy = 129/130
          - temporal_field_accuracy = 129/130
          - recall_macro = (32/33 + 1 + 1 + 1 + 1) / 5
          - precision_* remain 1.0 (no false positives)
        """
        gold_src = _DIR / "gold_set" / "v1"
        expected_recall_factual = 32 / 33
        expected_assign = 129 / 130
        expected_temporal = 129 / 130
        expected_recall_macro = (expected_recall_factual + 4.0) / 5.0

        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            root = Path(tmp)
            gold_dir = root / "gold"
            shutil.copytree(gold_src, gold_dir)
            cas_path = gold_dir / "openai_cassettes.jsonl"
            rows: list[dict] = []
            mutated = False
            for line in cas_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["conversation_id"] == "c001":
                    payload = json.loads(row["raw_json"])
                    for turn in payload["turns"]:
                        turn["memories"] = []
                    row["raw_json"] = json.dumps(payload, separators=(",", ":"))
                    mutated = True
                rows.append(row)
            self.assertTrue(mutated, "c001 cassette row missing — fixture assumption broken")
            cas_path.write_text(
                "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
                encoding="utf-8",
            )
            manifest_path = gold_dir / "cassette_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cassettes_sha256"] = hashlib.sha256(cas_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            out = root / "out"
            out.mkdir()
            original_out = run_eval.OUTPUT_DIR
            original_latest = run_eval.LATEST_PATH
            self.addCleanup(setattr, run_eval, "OUTPUT_DIR", original_out)
            self.addCleanup(setattr, run_eval, "LATEST_PATH", original_latest)
            run_eval.OUTPUT_DIR = out
            run_eval.LATEST_PATH = out / "latest.json"

            report = run_eval.run_eval(mode="cassette", provider="openai", gold_dir=gold_dir)
            metrics = report["metrics"]
            self.assertAlmostEqual(metrics["recall_factual"], expected_recall_factual, places=9)
            self.assertAlmostEqual(metrics["category_assignment_accuracy"], expected_assign, places=9)
            self.assertAlmostEqual(metrics["temporal_field_accuracy"], expected_temporal, places=9)
            self.assertAlmostEqual(metrics["recall_macro"], expected_recall_macro, places=9)
            for cat in (
                "factual",
                "procedural",
                "preference",
                "behavioral",
                "episodic",
            ):
                self.assertAlmostEqual(metrics[f"precision_{cat}"], 1.0, places=9, msg=cat)
            for cat in ("procedural", "preference", "behavioral", "episodic"):
                self.assertAlmostEqual(metrics[f"recall_{cat}"], 1.0, places=9, msg=cat)


class OracleCassettePolicyTests(unittest.TestCase):
    def test_policy_passes_when_contract_files_unchanged(self) -> None:
        with mock.patch.object(oracle_policy, "_git_changed_paths", return_value=set()):
            code = oracle_policy.main(
                ["--base", "aaaa", "--head", "bbbb", "--pr-body", ""]
            )
        self.assertEqual(code, 0)

    def test_policy_fails_on_prompt_change_with_oracle_cassettes(self) -> None:
        touched = {"services/worker/app/extraction/prompt_v2.py"}
        with mock.patch.object(oracle_policy, "_git_changed_paths", return_value=touched):
            code = oracle_policy.main(
                ["--base", "aaaa", "--head", "bbbb", "--pr-body", "no override"]
            )
        self.assertEqual(code, 1)

    def test_policy_override_token_allows_oracle_with_schema_change(self) -> None:
        touched = {"services/worker/app/extraction/schema.py"}
        with mock.patch.object(oracle_policy, "_git_changed_paths", return_value=touched):
            code = oracle_policy.main(
                [
                    "--base",
                    "aaaa",
                    "--head",
                    "bbbb",
                    "--pr-body",
                    "Ack: EXTRACTION_EVAL_ORACLE_OK=1 for this PR",
                ]
            )
        self.assertEqual(code, 0)

    def test_policy_rejects_drift_env_in_workflow_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            fake = Path(tmp) / "extraction-eval.yml"
            fake.write_text(
                'env:\n  EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT: "1"\n',
                encoding="utf-8",
            )
            with mock.patch.object(oracle_policy, "_WORKFLOW", fake):
                with self.assertRaises(SystemExit) as ctx:
                    oracle_policy._assert_workflow_forbids_drift_env()
            self.assertIn("EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
