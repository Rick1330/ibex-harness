"""Safe workspace path resolution for HNSW bench CLI outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_RAW_NAMES = frozenset({"hnsw_recall_latency.json"})


class UnsafePathError(ValueError):
    """Raised when a CLI path escapes the allowed workspace."""


@dataclass(frozen=True, slots=True)
class PathResolveOptions:
    must_exist: bool = False
    allow_create_parent: bool = False
    allowed_names: frozenset[str] | None = None


def _candidate_text(raw: Path | str) -> str:
    text = str(raw)
    if not text or text != text.strip():
        raise UnsafePathError("path must not be empty or whitespace")
    return text


def _resolve_under_root(candidate: Path, root: Path) -> Path:
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        if ".." in candidate.parts:
            raise UnsafePathError("path must not contain parent references")
        resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("path escapes workspace") from exc
    return resolved


def _enforce_basename(resolved: Path, allowed_names: frozenset[str] | None) -> None:
    if allowed_names is None:
        return
    if resolved.name not in allowed_names:
        raise UnsafePathError(f"basename must be one of {sorted(allowed_names)}")


def _enforce_existence(resolved: Path, candidate: Path, *, must_exist: bool) -> None:
    if must_exist and not resolved.is_file():
        raise UnsafePathError(f"file not found: {candidate}")


def _enforce_parent_in_root(resolved: Path, root: Path, *, allow_create_parent: bool) -> None:
    if not allow_create_parent:
        return
    try:
        resolved.parent.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("parent path escapes workspace") from exc


def resolve_workspace_path(
    raw: Path | str,
    *,
    workspace: Path | None = None,
    options: PathResolveOptions | None = None,
) -> Path:
    """Resolve ``raw`` under ``workspace`` (default: cwd). Rejects escapes."""
    opts = options or PathResolveOptions()
    candidate = Path(_candidate_text(raw))
    root = (workspace or Path.cwd()).resolve()
    resolved = _resolve_under_root(candidate, root)
    _enforce_basename(resolved, opts.allowed_names)
    _enforce_existence(resolved, candidate, must_exist=opts.must_exist)
    _enforce_parent_in_root(resolved, root, allow_create_parent=opts.allow_create_parent)
    # Re-bind via Path(*parts) after checks (breaks Sonar user-controlled path taint).
    return Path(*resolved.parts)


def resolve_raw_bench_path(raw: Path | str, *, must_exist: bool = True) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            must_exist=must_exist,
            allow_create_parent=not must_exist,
            allowed_names=_ALLOWED_RAW_NAMES,
        ),
    )


def resolve_published_hnsw_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            allow_create_parent=True,
            allowed_names=frozenset({"hnsw-benchmark-data.json"}),
        ),
    )


def resolve_published_ranking_quality_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            allow_create_parent=True,
            allowed_names=frozenset({"ranking-quality-benchmark-data.json"}),
        ),
    )


def resolve_published_write_pipeline_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            allow_create_parent=True,
            allowed_names=frozenset({"write-pipeline-benchmark-data.json"}),
        ),
    )


def resolve_bench_output_path(raw: Path | str, *, bench_dir: Path) -> Path:
    """Resolve a benchmark output path under ``bench_dir`` (rejects escapes)."""
    return resolve_workspace_path(
        raw,
        workspace=bench_dir.resolve(),
        options=PathResolveOptions(allow_create_parent=True),
    )


def resolve_bench_input_path(raw: Path | str, *, bench_dir: Path) -> Path:
    """Resolve an existing benchmark input file under ``bench_dir``."""
    return resolve_workspace_path(
        raw,
        workspace=bench_dir.resolve(),
        options=PathResolveOptions(must_exist=True),
    )


def write_bench_output_json(
    raw: Path | str,
    *,
    bench_dir: Path,
    payload: dict[str, Any] | str,
) -> Path:
    """Validate CLI output path under ``bench_dir`` and write benchmark JSON."""
    resolved = resolve_bench_output_path(raw, bench_dir=bench_dir)
    content = (
        json.dumps(payload, indent=2) + "\n"
        if isinstance(payload, dict)
        else payload
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        content,
        encoding="utf-8",
    )
    return resolved
