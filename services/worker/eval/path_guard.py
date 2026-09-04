"""Safe workspace path resolution for extraction-eval CLI outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PUBLISHED_NAME = "extraction-quality-benchmark-data.json"
_LATEST_NAME = "latest.json"
_GATE_NAME = "gate-result.json"
_BASELINE_NAME = "baseline_results.json"
_GATE_INPUT_NAMES = frozenset({_GATE_NAME, "gate.json"})
_LATEST_INPUT_NAMES = frozenset({_LATEST_NAME})


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


def resolve_published_extraction_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            allow_create_parent=True,
            allowed_names=frozenset({PUBLISHED_NAME}),
        ),
    )


def resolve_latest_path(raw: Path | str, *, must_exist: bool = True) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            must_exist=must_exist,
            allow_create_parent=not must_exist,
            allowed_names=_LATEST_INPUT_NAMES,
        ),
    )


def resolve_gate_input_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(must_exist=True, allowed_names=_GATE_INPUT_NAMES),
    )


def resolve_gate_result_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            allow_create_parent=True,
            allowed_names=frozenset({_GATE_NAME}),
        ),
    )


def resolve_baseline_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        options=PathResolveOptions(
            must_exist=True,
            allowed_names=frozenset({_BASELINE_NAME, "baseline.json"}),
        ),
    )
