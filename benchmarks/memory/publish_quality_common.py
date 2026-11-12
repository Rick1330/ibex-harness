"""Shared helpers for ranking-quality and write-pipeline published history."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from path_guard import PathResolveOptions, resolve_workspace_path

# What a published ``provenance`` block has to carry. These are the schema's ``status ==
# "recorded"`` requirements plus the status itself, kept in one place so both publishers refuse
# the same incomplete record.
REQUIRED_PROVENANCE_FIELDS = (
    "status",
    "producer",
    "runner_cpu_model",
    "runner_cpu_count",
    "runner_ram_mib",
    "corpus_hash",
    "corpus_hash_algo",
    "corpus_manifest",
    "corpus_status",
    "dirty",
)


@dataclass(frozen=True, slots=True)
class RunMeta:
    sha: str
    branch: str
    run_number: int
    run_url: str


def gate_status(gate: dict[str, Any]) -> str:
    return "pass" if gate.get("status") == "pass" else "fail"


def _recorded_provenance_block(
    document: Mapping[str, Any], *, artifact: str, rerun: str
) -> Mapping[str, Any]:
    """The document's populated ``provenance`` mapping, or a refusal naming the fix."""
    record = document.get("provenance")
    if isinstance(record, Mapping) and record:
        return record
    raise RuntimeError(f"{artifact} has no provenance; {rerun}")


def _missing_fields(record: Mapping[str, Any]) -> list[str]:
    """The required provenance fields ``record`` does not carry a value for."""
    return [field for field in REQUIRED_PROVENANCE_FIELDS if record.get(field) is None]


def _require_complete(record: Mapping[str, Any], *, artifact: str, rerun: str) -> None:
    """Refuse a block that is missing a required field, naming every one that is absent."""
    missing = _missing_fields(record)
    if missing:
        raise RuntimeError(
            f"{artifact} provenance is incomplete (missing {', '.join(missing)}); {rerun}"
        )


def _require_recorded_status(
    record: Mapping[str, Any], *, artifact: str, rerun: str
) -> None:
    """Refuse a complete block whose status says the number cannot be reproduced."""
    status = record.get("status")
    if status != "recorded":
        raise RuntimeError(
            f"{artifact} provenance.status is {status!r}, expected 'recorded'; "
            f"a published number must be reproducible; {rerun}"
        )


def require_recorded_provenance(
    document: Mapping[str, Any], *, artifact: str, rerun: str
) -> dict[str, Any]:
    """Return ``document``'s ``provenance`` block, refusing to publish without a full one.

    The schemas keep the block optional so artifacts written before it existed stay valid; that
    is a compatibility promise to old files, not permission to write a new one without it. A
    published number nobody can reproduce is not evidence, so a missing or partial block stops
    the publish and names the command that fixes it.
    """
    record = _recorded_provenance_block(document, artifact=artifact, rerun=rerun)
    _require_complete(record, artifact=artifact, rerun=rerun)
    _require_recorded_status(record, artifact=artifact, rerun=rerun)
    return dict(record)


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
    published = load_or_init_published(
        request.published_path, benchmark=request.benchmark
    )
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
    """One published ranking-quality run: the scored metrics, plus what produced them.

    ``provenance`` is copied from the scored artifact and required. ``modes`` is deliberately
    not copied: no published shape defines it, and a mode comparison is published as its own
    artifact rather than smuggled into a single-mode history.
    """
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "gold_set": latest.get("gold_set", "v1"),
        "query_count": latest.get("query_count", 0),
        "memory_count": latest.get("memory_count", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
        "provenance": require_recorded_provenance(
            latest,
            artifact="ranking-quality artifact",
            rerun="re-run the ranking-quality bench on this checkout so the run is reproducible",
        ),
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
