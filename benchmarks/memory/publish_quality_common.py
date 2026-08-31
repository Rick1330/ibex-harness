"""Shared helpers for ranking-quality and write-pipeline published history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from path_guard import PathResolveOptions, resolve_workspace_path


@dataclass(frozen=True, slots=True)
class RunMeta:
    sha: str
    branch: str
    run_number: int
    run_url: str


def gate_status(gate: dict[str, Any]) -> str:
    return "pass" if gate.get("status") == "pass" else "fail"


def _resolve_existing_json_path(path: Path) -> Path:
    return resolve_workspace_path(
        path,
        options=PathResolveOptions(must_exist=True),
    )


def _resolve_output_json_path(path: Path) -> Path:
    return resolve_workspace_path(
        path,
        options=PathResolveOptions(allow_create_parent=True),
    )


def load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve_existing_json_path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def load_or_init_published(published_path: Path, *, benchmark: str) -> dict[str, Any]:
    resolved = _resolve_output_json_path(published_path)
    if not resolved.exists():
        return {"schema_version": 1, "benchmark": benchmark, "runs": []}
    data = load_json(resolved)
    data.setdefault("schema_version", 1)
    data["benchmark"] = benchmark
    data.setdefault("runs", [])
    return data


def write_published(published_path: Path, published: dict[str, Any]) -> None:
    resolved = _resolve_output_json_path(published_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(published, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True, slots=True)
class MergeRunRequest:
    published_path: Path
    benchmark: str
    entry: dict[str, Any]
    sha: str
    max_runs: int = 50


def merge_run(request: MergeRunRequest) -> dict[str, Any]:
    published = load_or_init_published(request.published_path, benchmark=request.benchmark)
    runs = [r for r in published.get("runs", []) if r.get("sha") != request.sha]
    runs.insert(0, request.entry)
    published["schema_version"] = 1
    published["benchmark"] = request.benchmark
    published["runs"] = runs[: request.max_runs]
    write_published(request.published_path, published)
    return published


def run_entry_base(meta: RunMeta, *, timestamp: str | None = None) -> dict[str, Any]:
    short = meta.sha[:7] if len(meta.sha) >= 7 else meta.sha
    return {
        "sha": meta.sha,
        "short_sha": short,
        "timestamp": timestamp or datetime.now(tz=UTC).isoformat(),
        "branch": meta.branch,
        "run_number": meta.run_number,
        "run_url": meta.run_url,
    }


def merge_ranking_quality_entry(
    latest: dict[str, Any], gate: dict[str, Any], meta: RunMeta
) -> dict[str, Any]:
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "gold_set": latest.get("gold_set", "v1"),
        "query_count": latest.get("query_count", 0),
        "memory_count": latest.get("memory_count", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
    }


def merge_write_pipeline_entry(
    latest: dict[str, Any], gate: dict[str, Any], meta: RunMeta
) -> dict[str, Any]:
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "iterations": latest.get("iterations", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
    }
