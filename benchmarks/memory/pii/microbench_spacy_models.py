#!/usr/bin/env python3
"""Compare spaCy sm vs md latency for Presidio-oriented PII microbench (m3.C.1 PR-A).

Usage (from services/memory with deps synced):

  uv run python ../../benchmarks/memory/pii/microbench_spacy_models.py

Writes JSON summary next to this script. Does not call external APIs.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

SAMPLES = [
    "Contact me at alice@example.com or +1-555-123-4567 about the invoice.",
    "SSN 123-45-6789 should never be stored in clear text next to card 4111111111111111.",
    "Please ship to 221B Baker Street; ask for Sarah Chen at the front desk.",
    ("x" * 180) + " email backup@ibex.example phone 415-555-0100 " + ("y" * 180),
    ("word " * 400) + "John Smith lives at 1 Infinite Loop Cupertino CA.",
]

MODELS = ("en_core_web_sm", "en_core_web_md")
WARMUP = 2
ITERS = 25


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def bench_model(name: str) -> dict[str, object]:
    import spacy

    nlp = spacy.load(name)
    # Disable non-NER pipes for write-path-shaped cost.
    disable = [p for p in nlp.pipe_names if p not in {"tok2vec", "ner"}]
    if disable:
        nlp.disable_pipes(*disable)

    for _ in range(WARMUP):
        for text in SAMPLES:
            _ = list(nlp(text).ents)

    times_ms: list[float] = []
    for _ in range(ITERS):
        for text in SAMPLES:
            t0 = time.perf_counter()
            _ = list(nlp(text).ents)
            times_ms.append((time.perf_counter() - t0) * 1000.0)

    times_ms.sort()
    return {
        "model": name,
        "n_samples": len(SAMPLES),
        "iters": ITERS,
        "n_measurements": len(times_ms),
        "latency_ms_p50": statistics.median(times_ms),
        "latency_ms_p95": _percentile(times_ms, 95),
        "latency_ms_mean": statistics.fmean(times_ms),
        "pipes": list(nlp.pipe_names),
    }


def main() -> None:
    results = [bench_model(m) for m in MODELS]
    out = {
        "benchmark": "pii_spacy_model_microbench",
        "write_budget_ms_p95": 200,
        "note": (
            "NER-only pipe latency for candidate models. Default remains en_core_web_md "
            "(ADR-0054). Full Presidio stage cost measured in PR-C harness."
        ),
        "results": results,
    }
    out_path = Path(__file__).with_name("microbench_spacy_models.json")
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
