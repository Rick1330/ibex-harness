"""Safe workspace path resolution for extraction-eval CLI outputs."""

from __future__ import annotations

from pathlib import Path

PUBLISHED_NAME = "extraction-quality-benchmark-data.json"
_ALLOWED_LATEST = frozenset({"latest.json"})
_ALLOWED_GATE_IN = frozenset({"gate-result.json", "gate.json"})
_ALLOWED_GATE_OUT = frozenset({"gate-result.json"})
_ALLOWED_BASELINE = frozenset({"baseline_results.json", "baseline.json"})


class UnsafePathError(ValueError):
    """Raised when a CLI path escapes the allowed workspace."""


def _cwd() -> Path:
    return Path.cwd().resolve()


def _require_text(raw: Path | str) -> str:
    text = str(raw)
    if not text or text != text.strip():
        raise UnsafePathError("path must not be empty or whitespace")
    return text


def _resolve_candidate(candidate: Path, root: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    if ".." in candidate.parts:
        raise UnsafePathError("path must not contain parent references")
    return (root / candidate).resolve()


def _ensure_under_root(resolved: Path, root: Path) -> None:
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("path escapes workspace") from exc


def _enforce_basename(resolved: Path, allowed_names: frozenset[str] | None) -> None:
    if allowed_names is None:
        return
    if resolved.name not in allowed_names:
        raise UnsafePathError(f"basename must be one of {sorted(allowed_names)}")


def _enforce_exists(resolved: Path, candidate: Path, *, must_exist: bool) -> None:
    if must_exist and not resolved.is_file():
        raise UnsafePathError(f"file not found: {candidate}")


def _enforce_parent(resolved: Path, root: Path, *, allow_create_parent: bool) -> None:
    if not allow_create_parent:
        return
    try:
        resolved.parent.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("parent path escapes workspace") from exc


def resolve_workspace_path(
    raw: Path | str,
    *,
    allowed_names: frozenset[str] | None = None,
    must_exist: bool = False,
    allow_create_parent: bool = False,
    workspace: Path | None = None,
) -> Path:
    candidate = Path(_require_text(raw))
    root = (workspace or _cwd()).resolve()
    resolved = _resolve_candidate(candidate, root)
    _ensure_under_root(resolved, root)
    _enforce_basename(resolved, allowed_names)
    _enforce_exists(resolved, candidate, must_exist=must_exist)
    _enforce_parent(resolved, root, allow_create_parent=allow_create_parent)
    return Path(*resolved.parts)


def resolve_published_extraction_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=frozenset({PUBLISHED_NAME}),
        allow_create_parent=True,
    )


def resolve_latest_path(raw: Path | str, *, must_exist: bool = True) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=_ALLOWED_LATEST,
        must_exist=must_exist,
        allow_create_parent=not must_exist,
    )


def resolve_gate_input_path(raw: Path | str) -> Path:
    return resolve_workspace_path(raw, allowed_names=_ALLOWED_GATE_IN, must_exist=True)


def resolve_gate_result_path(raw: Path | str) -> Path:
    return resolve_workspace_path(
        raw,
        allowed_names=_ALLOWED_GATE_OUT,
        allow_create_parent=True,
    )


def resolve_baseline_path(raw: Path | str) -> Path:
    return resolve_workspace_path(raw, allowed_names=_ALLOWED_BASELINE, must_exist=True)
