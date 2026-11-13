#!/usr/bin/env python3
"""The proxy latency artifact, as the reproducibility checker reads it.

This artifact is the one kind with an exact name (`benchmark-data.json`), its own
percentile spelling (`p50_ms`, and `auth_lru_p50_ms` inside `stages`), and no corpus
identity. Those are three claims about one file, so they are tested together here
rather than spread through the per-rule modules.

The harness is shared with `test_check_reproducibility`: one `CheckerCase`, one loaded
copy of the checker, and the same fixtures, so a rule that changes shape cannot be
satisfied in one module and broken in the other.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from test_check_reproducibility import (
    PUBLISHED,
    CheckerCase,
    _recorded,
    _runs_in,
    check,
)

PROXY_NAME = "benchmark-data.json"


def _proxy_run(**overrides: object) -> dict[str, object]:
    """One run of the proxy latency artifact, in the shape the artifact actually publishes."""
    run: dict[str, object] = {
        "sha": "e" * 40,
        "short_sha": "e" * 7,
        "timestamp": "2026-11-12T00:00:00+00:00",
        "branch": "main",
        "pr_number": None,
        "run_number": 7,
        "run_url": "https://example.invalid/actions/runs/7",
        "status": "pass",
        "k6": {"p50_ms": 0.5, "p95_ms": 1.0, "p99_ms": 1.5, "p999_ms": 2.5},
        "stages": {
            "auth_lru_p50_ms": 0.1,
            "auth_lru_p95_ms": 0.2,
            "auth_lru_p99_ms": 0.3,
        },
        "metric_deltas": {"k6": {"p99_ms": -0.1}},
    }
    run.update(overrides)
    return run


def _proxy(*runs: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "baseline_sha": "f" * 40, "runs": list(runs)}


# Run overrides and the problem each must produce. The proxy artifact spells its percentiles
# ``p50_ms`` (and ``auth_lru_p50_ms`` inside ``stages``), so every ordering case is stated in
# that spelling; ``p999_ms`` is optional and must not hide the triple when it is absent.
PROXY_CASES: dict[str, tuple[dict[str, object], str]] = {
    "sha is not 40 lowercase hex": (
        {"sha": "E" * 40, "short_sha": "E" * 7},
        "runs[0].sha:",
    ),
    # The provenance contract knows the hnsw and gold corpora, not the proxy source, so a
    # recorded proxy run is refused like a recorded extraction-quality run.
    "a recorded run has no corpus": ({"provenance": _recorded()}, "no corpus identity"),
    "k6 p50 above its p95": (
        {"k6": {"p50_ms": 5.0, "p95_ms": 4.0, "p99_ms": 6.0, "p999_ms": 7.0}},
        "runs[0].k6: p50 5.0 > p95 4.0",
    ),
    "a stage group keeps its name": (
        {
            "stages": {
                "auth_lru_p50_ms": 3.0,
                "auth_lru_p95_ms": 2.0,
                "auth_lru_p99_ms": 4.0,
            }
        },
        "runs[0].stages.auth_lru: p50 3.0 > p95 2.0",
    ),
    "p99 above its p999": (
        {"k6": {"p50_ms": 0.5, "p95_ms": 1.0, "p99_ms": 3.0, "p999_ms": 2.0}},
        "runs[0].k6: p99 3.0 > p999 2.0",
    ),
    "a run without a p999": (
        {"k6": {"p50_ms": 5.0, "p95_ms": 4.0, "p99_ms": 6.0}},
        "runs[0].k6: p50 5.0 > p95 4.0",
    ),
}


class TestProxyArtifact(CheckerCase):
    """The proxy latency artifact: exact name, ``p50_ms`` spelling, no corpus identity."""

    def test_the_published_artifact_is_checked_in_its_own_spelling(self) -> None:
        """The kind, its schema, and every per-run rule, stated in the ``p50_ms`` spelling.

        One test method keeps the contract in one place; each subTest names the case that fails.
        """
        kind = check._kind(Path(PROXY_NAME))
        suffixed = check._kind(Path("hnsw-benchmark-data.json"))
        self.assertEqual(kind.name, "benchmark-data")
        self.assertIsNone(kind.corpus)
        self.assertEqual(kind.percentiles, check.PROXY_PERCENTILES)
        self.assertEqual(check._schema(Path(PROXY_NAME).stem)["title"], "BenchmarkData")
        # The four suffixed kinds keep the corpus and the spelling they had.
        self.assertEqual(suffixed.corpus, "hnsw")
        self.assertEqual(suffixed.percentiles, check.SUFFIXED_PERCENTILES)

        self.assert_clean(_proxy(_proxy_run()), PROXY_NAME)
        for name, (overrides, expected) in PROXY_CASES.items():
            with self.subTest(name):
                problems = self.content_problems(
                    _proxy(_proxy_run(**overrides)), PROXY_NAME
                )
                self.assertTrue(
                    any(expected in problem for problem in problems), problems
                )

        # A renamed field would stop the ordering check silently: the layout would find no group
        # and report nothing. This pins the spelling the published artifact actually uses.
        for index, run in enumerate(_runs_in(PUBLISHED / PROXY_NAME)):
            k6 = check._percentile_prefixes(run["k6"], check.PROXY_PERCENTILES)
            stages = check._percentile_prefixes(run["stages"], check.PROXY_PERCENTILES)
            self.assertEqual(k6, [""], f"runs[{index}].k6")
            self.assertTrue(stages, f"runs[{index}].stages")


if __name__ == "__main__":
    unittest.main()
