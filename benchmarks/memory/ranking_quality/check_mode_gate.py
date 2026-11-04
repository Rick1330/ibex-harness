#!/usr/bin/env python3
"""Enforce the multi-mode gate: the committed baseline against a measured run.

`gate_modes` decides what passes; this module is the part that reads two files, refuses to
compare runs that were not measured the same way, and writes the verdict where CI can read it.

The refusal is the point. A baseline recorded on another gold set, or with another reranker, is
not a threshold — it is a number from a different experiment, and comparing against it would
produce a pass that means nothing. Both are checked before any scoring happens.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RANK_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _RANK_DIR.parent
for _path in (_BENCH_MEMORY, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gate_modes import (
    DEFAULT_POLICY,
    GateFailure,
    ModeResult,
    evaluate_gate,
    render_report,
)
from path_guard import (
    resolve_bench_input_path,
    resolve_bench_output_path,
    write_json_atomic,
)

BASELINE_PATH = _RANK_DIR / "baseline-modes.json"
ARTIFACT_PATH = _RANK_DIR / "output" / "modes-latest.json"
REPORT_PATH = _RANK_DIR / "output" / "modes-gate.json"


class GateInputError(ValueError):
    """An input that cannot be gated: wrong shape, or measured on something else."""


@dataclass(frozen=True, slots=True)
class Artifact:
    """A scored run, plus the provenance it was measured with."""

    gold_set: str
    reranker: str
    results: Mapping[str, ModeResult]


@dataclass(frozen=True, slots=True)
class Baseline:
    """The committed scores, plus the provenance they were measured with."""

    gold_set: str
    reranker: str
    scores: Mapping[str, float]


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise GateInputError(f"{path.name}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise GateInputError(f"{path.name} is not a JSON object")
    return document


def _label(document: Mapping[str, Any], field: str, source: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise GateInputError(
            f"{source} does not name its {field}; the comparison needs it"
        )
    return value


def _score(mode: str, field: str, row: Mapping[str, Any]) -> float:
    value = row.get(field)
    # bool is an int: `true` would slide through as 1.0 and read as a perfect score.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateInputError(f"mode {mode!r} field {field!r} must be a number")
    return float(value)


def _count(mode: str, field: str, row: Mapping[str, Any]) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateInputError(f"mode {mode!r} field {field!r} must be an integer")
    return value


def _subset_counts(mode: str, row: Mapping[str, Any]) -> dict[str, int]:
    counts = row.get("per_subset_counts")
    if not isinstance(counts, Mapping):
        raise GateInputError(f"mode {mode!r} has no per_subset_counts")
    return {name: _count(mode, str(name), counts) for name in counts}


def _mode_result(mode: str, row: Any) -> ModeResult:
    if not isinstance(row, Mapping):
        raise GateInputError(f"mode {mode!r} is not an object in the artifact")
    return ModeResult(
        mode=mode,
        overall=_score(mode, "ndcg_at_10", row),
        non_graph=_score(mode, "non_graph_ndcg_at_10", row),
        graph=_score(mode, "graph_ndcg_at_10", row),
        query_count=_count(mode, "query_count", row),
        per_subset_counts=_subset_counts(mode, row),
    )


def load_artifact(path: Path) -> Artifact:
    """Read a scored run. Every field the gate consumes is checked, none coerced."""
    document = _read_json(path)
    modes = document.get("modes")
    if not isinstance(modes, Mapping) or not modes:
        raise GateInputError(f"{path.name} has no modes to gate")
    return Artifact(
        gold_set=_label(document, "gold_set", path.name),
        reranker=_label(document, "reranker", path.name),
        results={name: _mode_result(name, row) for name, row in modes.items()},
    )


def _baseline_scores(document: Mapping[str, Any], source: str) -> dict[str, float]:
    scores = document.get("baseline")
    if not isinstance(scores, Mapping) or not scores:
        raise GateInputError(f"{source} has no baseline to compare against")
    return {
        name: _score(str(name), "baseline", {"baseline": value})
        for name, value in scores.items()
    }


def load_baseline(path: Path) -> Baseline:
    document = _read_json(path)
    return Baseline(
        gold_set=_label(document, "gold_set", path.name),
        reranker=_label(document, "reranker", path.name),
        scores=_baseline_scores(document, path.name),
    )


def _provenance_problems(artifact: Artifact, baseline: Baseline) -> list[str]:
    problems: list[str] = []
    if artifact.gold_set != baseline.gold_set:
        problems.append(
            f"gold set {artifact.gold_set!r} was not the baseline's {baseline.gold_set!r}"
        )
    if artifact.reranker != baseline.reranker:
        problems.append(
            f"reranker {artifact.reranker!r} was not the baseline's {baseline.reranker!r}"
        )
    return problems


def require_same_experiment(artifact: Artifact, baseline: Baseline) -> None:
    """Refuse a comparison between runs that do not share a corpus and a reranker."""
    problems = _provenance_problems(artifact, baseline)
    if problems:
        raise GateInputError("; ".join(problems))


def _failure_row(failure: GateFailure) -> dict[str, str]:
    return {"mode": failure.mode, "check": failure.check, "detail": failure.detail}


def _modes_row(results: Mapping[str, ModeResult]) -> dict[str, Any]:
    return {
        name: {
            "overall": result.overall,
            "non_graph": result.non_graph,
            "graph": result.graph,
        }
        for name, result in sorted(results.items())
    }


def _distinguishes_graph_mode(results: Mapping[str, ModeResult]) -> bool | None:
    """Did the corpus let the graph-aware mode differ from its reference at all?

    ``None`` when either mode is missing, since the question cannot be asked. ``False`` is not a
    gate failure -- a corpus where suppression removes nothing scores identically and the gate
    still has to pass -- but it does mean the mode comparison carries no evidence about
    suppression, and a reader looking at two equal rows deserves to be told which of the two it
    is.
    """
    reference = results.get(DEFAULT_POLICY.reference_mode)
    subject = results.get(DEFAULT_POLICY.subject_mode)
    if reference is None or subject is None:
        return None
    measured = (
        (reference.overall, reference.non_graph, reference.graph),
        (
            subject.overall,
            subject.non_graph,
            subject.graph,
        ),
    )
    return measured[0] != measured[1]


def build_report(
    artifact: Artifact, baseline: Baseline, failures: Sequence[GateFailure]
) -> dict[str, Any]:
    """The machine-readable verdict, kept next to the Markdown one in the run summary."""
    return {
        "schema_version": 1,
        "benchmark": "ranking_quality",
        "gold_set": artifact.gold_set,
        "reranker": artifact.reranker,
        "status": "fail" if failures else "pass",
        "baseline": dict(sorted(baseline.scores.items())),
        "modes": _modes_row(artifact.results),
        "graph_mode_distinguished": _distinguishes_graph_mode(artifact.results),
        "failures": [_failure_row(failure) for failure in failures],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--report-out", type=Path, default=REPORT_PATH)
    return parser.parse_args(argv)


def _report_path(args: argparse.Namespace) -> Path:
    return resolve_bench_output_path(args.report_out, bench_dir=_RANK_DIR)


def _input_failure_report(detail: str) -> dict[str, Any]:
    """The verdict for a run that could not even be read.

    There are no mode rows to table, but there is still a reason, and it belongs in the file the
    job uploads rather than only in a traceback someone has to go find.
    """
    return {
        "schema_version": 1,
        "benchmark": "ranking_quality",
        "status": "fail",
        "failures": [{"mode": "-", "check": "input", "detail": detail}],
    }


def _emit(
    args: argparse.Namespace,
    artifact: Artifact,
    baseline: Baseline,
    failures: Sequence[GateFailure],
) -> int:
    print(render_report(artifact.results, failures, baseline.scores))
    # Written before the exit code, so a failing gate still leaves its verdict for the job that
    # uploads it. A gate that only fails the build is a gate nobody can read afterwards.
    write_json_atomic(_report_path(args), build_report(artifact, baseline, failures))
    return 1 if failures else 0


def _reject(args: argparse.Namespace, exc: GateInputError) -> int:
    """A run that cannot be compared exits differently from one that regressed.

    ``2`` means the gate refused the input; ``1`` means it read the input and the numbers failed.
    Conflating them would make "we did not measure this" look like "the measurement moved".
    """
    write_json_atomic(_report_path(args), _input_failure_report(str(exc)))
    print(f"gate rejected: {exc}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv[1:] if argv else None)
    try:
        artifact = load_artifact(
            resolve_bench_input_path(args.artifact, bench_dir=_RANK_DIR)
        )
        baseline = load_baseline(
            resolve_bench_input_path(args.baseline, bench_dir=_RANK_DIR)
        )
    except GateInputError as exc:
        return _reject(args, exc)
    try:
        require_same_experiment(artifact, baseline)
    except GateInputError as exc:
        # Both files parsed, so the table is worth printing: a reader can see the numbers and
        # why they were refused side by side.
        return _emit(
            args,
            artifact,
            baseline,
            [GateFailure(mode="-", check="provenance", detail=str(exc))],
        )
    return _emit(
        args, artifact, baseline, evaluate_gate(artifact.results, baseline.scores)
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
