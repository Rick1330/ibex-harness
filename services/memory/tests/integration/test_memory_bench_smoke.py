"""Integration smoke tests for ranking-quality and write-pipeline benchmarks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MEMORY_DIR = _REPO_ROOT / "services" / "memory"
_DECAY_QUERY_IDS = frozenset(
    {
        "q_pref_theme_decay",
        "q_workflow_deploy_decay",
        "q_confidence_tie_break",
    }
)


def _run_bench(script_rel: str) -> dict:
    script = _REPO_ROOT / script_rel
    env = {**__import__("os").environ, "PYTHONPATH": str(_MEMORY_DIR)}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=_MEMORY_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"{script.name} failed (rc={proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    output_path = script.parent / "output" / "latest.json"
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_gate(script_rel: str) -> None:
    script = _REPO_ROOT / script_rel
    env = {**__import__("os").environ, "PYTHONPATH": str(_MEMORY_DIR)}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=_MEMORY_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"{script.name} gate failed (rc={proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


@pytest.mark.integration
def test_ranking_quality_bench_smoke() -> None:
    payload = _run_bench("benchmarks/memory/ranking_quality/bench_ranking_quality.py")
    assert payload["benchmark"] == "ranking_quality"
    metrics = payload["metrics"]
    assert metrics["precision_at_5"] == pytest.approx(1.0)
    assert metrics["recall_at_10"] == pytest.approx(1.0)
    assert metrics["mrr"] == pytest.approx(1.0)
    assert payload["query_count"] >= 15
    assert payload["memory_count"] >= 30

    by_id = {q["query_id"]: q for q in payload["queries"]}
    for qid in _DECAY_QUERY_IDS:
        assert qid in by_id, f"missing decay query {qid}"
        assert by_id[qid]["mrr"] == pytest.approx(1.0)
        assert by_id[qid]["recall_at_10"] == pytest.approx(1.0)

    _run_gate("benchmarks/memory/ranking_quality/regression_gate.py")


@pytest.mark.integration
def test_write_pipeline_bench_smoke() -> None:
    payload = _run_bench("benchmarks/memory/write_pipeline/bench_write_pipeline.py")
    assert payload["benchmark"] == "write_pipeline"
    metrics = payload["metrics"]
    assert metrics["latency_ms_p95"] > 0.0
    assert metrics["latency_ms_p95"] < 200.0, "write p95 must meet 200ms SLA on CI hardware"
    assert payload["iterations"] >= 30

    _run_gate("benchmarks/memory/write_pipeline/regression_gate.py")
